"""Fetch real account data from OpenAlgo and Fyers for dashboard display."""

import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("core.dashboard_data")


def _extract_daily_pnl_snapshot_data(
    dashboard_data: dict,
    trading_date: date,
) -> tuple[float, int, bool]:
    positions = dashboard_data.get("positions") or []
    account = dashboard_data.get("account") or {}
    position_values = []
    for position in positions:
        if not isinstance(position, dict):
            continue
        value = next(
            (
                position[key]
                for key in ("pnl", "total_pnl_today", "today_realized_pnl")
                if position.get(key) is not None
            ),
            None,
        )
        if value is not None:
            position_values.append(float(value))

    if position_values:
        pnl = sum(position_values)
        has_pnl_data = True
    else:
        account_pnl = next(
            (
                account[key]
                for key in ("today_realized_pnl", "realized_pnl", "m2mrealized")
                if account.get(key) is not None
            ),
            None,
        )
        has_pnl_data = account_pnl is not None
        pnl = float(account_pnl or 0)

    orders_data = dashboard_data.get("orders") or {}
    orders = orders_data.get("orders", []) if isinstance(orders_data, dict) else orders_data
    completed_orders_today = 0
    for order in orders:
        if not isinstance(order, dict) or str(order.get("order_status", "")).lower() != "complete":
            continue
        timestamp = order.get("timestamp") or order.get("created_at") or order.get("order_timestamp")
        if not timestamp:
            continue
        try:
            order_time = timestamp if isinstance(timestamp, datetime) else datetime.fromisoformat(
                str(timestamp).replace("Z", "+00:00")
            )
            if order_time.tzinfo is not None:
                local_timezone = datetime.now().astimezone().tzinfo
                order_time = order_time.astimezone(local_timezone)
        except (TypeError, ValueError):
            continue
        if order_time.date() == trading_date:
            completed_orders_today += 1

    return pnl, completed_orders_today, has_pnl_data or completed_orders_today > 0


def _write_daily_pnl_snapshot(
    dashboard_data: dict,
    archive_path: Path,
    snapshot_time: Optional[datetime] = None,
) -> bool:
    """Persist the latest daily dashboard P&L without accumulating poll snapshots."""
    captured_at = snapshot_time or datetime.now()
    position_pnl, trade_count, has_daily_data = _extract_daily_pnl_snapshot_data(
        dashboard_data,
        captured_at.date(),
    )
    if not has_daily_data:
        return False

    month_key = captured_at.strftime("%Y-%m")
    day_key = str(captured_at.day)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with archive_path.open("r", encoding="utf-8") as handle:
            archive = json.load(handle)
    except (OSError, json.JSONDecodeError):
        archive = {}

    month_data = archive.setdefault(month_key, {})
    month_data[day_key] = {
        "pnl": round(position_pnl, 2),
        "trades": trade_count,
        "updated_at": captured_at.isoformat(),
    }
    temporary_path = archive_path.with_suffix(archive_path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(archive, indent=2), encoding="utf-8")
    os.replace(temporary_path, archive_path)
    return True


class DashboardDataProvider:
    """Fetches and caches real account data for React dashboard."""

    def __init__(self, api_key: str, host: str, strategy_tag: str = "HD_Strategy"):
        """Initialize with OpenAlgo credentials."""
        try:
            from openalgo import api  # type: ignore
            self.client = api(api_key=api_key, host=host)
            self.strategy_tag = strategy_tag
            self.available = True
        except ImportError:
            logger.warning("openalgo package not installed")
            self.available = False
            self.client = None

    def get_account_summary(self) -> dict:
        """Fetch account summary with balance, P&L, positions, and mode."""
        if not self.available or not self.client:
            return self._mock_account_summary()

        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "mode": self._detect_mode(),  # Get current OpenAlgo mode
                "positions": self._fetch_positions(),
                "orders": self._fetch_orders(),
                "account": self._fetch_account_info(),
            }
            return data
        except Exception as e:
            logger.error(f"Error fetching account data: {e}")
            return self._mock_account_summary()

    def _fetch_positions(self) -> list[dict]:
        """Fetch open positions from OpenAlgo."""
        try:
            resp = self.client.positionbook()
            if resp and "data" in resp:
                return resp["data"]
            return []
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    def _fetch_orders(self) -> list[dict]:
        """Fetch order book from OpenAlgo."""
        try:
            resp = self.client.orderbook()
            if resp and "data" in resp:
                return resp["data"]
            return []
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return []

    def _fetch_account_info(self) -> dict:
        """Fetch account balance and margin info from OpenAlgo and normalize field names."""
        try:
            resp = self.client.funds()
            if resp and "data" in resp:
                data = resp["data"]
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]
                
                # Transform OpenAlgo field names to standard format
                # OpenAlgo returns: availablecash, m2munrealized, m2mrealized, utiliseddebits
                normalized = {
                    # Available margin = available cash
                    "availableMargin": self._safe_float(data.get("availablecash")),
                    "margin": self._safe_float(data.get("availablecash")),
                    "available_margin": self._safe_float(data.get("availablecash")),
                    
                    # MTM = unrealized M2M
                    "mtm": self._safe_float(data.get("m2munrealized")),
                    "pnl": self._safe_float(data.get("m2munrealized")),
                    
                    # Realized P&L
                    "realized_pnl": self._safe_float(data.get("m2mrealized")),
                    "m2mrealized": self._safe_float(data.get("m2mrealized")),
                    
                    # Used margin
                    "used_margin": self._safe_float(data.get("utiliseddebits")),
                    "utiliseddebits": self._safe_float(data.get("utiliseddebits")),
                    
                    # Pass through raw data for debugging
                    **data
                }
                return normalized
            return {}
        except Exception as e:
            logger.error(f"Error fetching account info: {e}")
            return {}

    def _detect_mode(self) -> str:
        """Detect OpenAlgo current mode (live or analyzer).
        
        Returns 'live' if real account/trades are being used, 'analyzer' if in analysis mode.
        Checks environment variables and account state to determine mode.
        """
        import os
        
        # Check environment variable first (highest priority)
        mode_env = os.getenv("OPENALGO_MODE", "").lower().strip()
        if mode_env in ("live", "analyzer"):
            return mode_env
        
        # Check for strategy mode (run_strategy.py --mode)
        strategy_mode = os.getenv("STRATEGY_MODE", "").lower().strip()
        if strategy_mode in ("live", "paper", "backtest", "smoke"):
            # Map strategy modes to analyzer/live
            if strategy_mode == "live":
                return "live"
            else:
                return "analyzer"
        
        # Check for dry_run flag
        dry_run = os.getenv("DRY_RUN", "").lower().strip()
        if dry_run in ("true", "1", "yes"):
            return "analyzer"
        
        # Try to infer from account data (check if positions/trades exist)
        try:
            positions = self._fetch_positions()
            if positions and len(positions) > 0:
                # Has active positions, likely live mode
                return "live"
        except Exception:
            pass
        
        # Default to analyzer mode (safe default)
        return "analyzer"

    def _safe_float(self, value) -> float:
        """Safely convert value to float, handling strings and None."""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _mock_account_summary(self) -> dict:
        """Return mock data when API is unavailable."""
        return {
            "timestamp": datetime.now().isoformat(),
            "mode": self._detect_mode(),  # Include mode in mock data too
            "positions": [],
            "orders": [],
            "account": {
                "cash": 1000000,
                "margin": 500000,
                "used_margin": 0,
                "pnl": 0,
                "mtm": 0,
            },
        }

    def write_dashboard_json(self, output_path: Optional[str] = None) -> str:
        """Write account data to JSON file for React dashboard to read."""
        if output_path is None:
            output_path = Path(__file__).parent.parent / "logs" / "dashboard_data.json"
        else:
            output_path = Path(output_path)

        data = self.get_account_summary()

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        _write_daily_pnl_snapshot(data, output_path.parent / "daily_pnl.json")

        logger.info(f"Dashboard data written to {output_path}")
        return str(output_path)


class FyersWalletProvider:
    """Fetch wallet and balance data from Fyers broker, with OpenAlgo fallback."""

    def __init__(self, fyers_api_key: Optional[str] = None, fyers_access_token: Optional[str] = None, openalgo_client=None):
        """Initialize with Fyers credentials and optional OpenAlgo fallback."""
        self.fyers_api_key = fyers_api_key or os.getenv("FYERS_API_KEY")
        self.fyers_access_token = fyers_access_token or os.getenv("FYERS_ACCESS_TOKEN")
        self.fyers_available = bool(self.fyers_api_key and self.fyers_access_token and "YOUR_" not in str(self.fyers_api_key))
        self.openalgo_client = openalgo_client

    def get_wallet_data(self) -> dict:
        """Fetch wallet balance from Fyers, with OpenAlgo fallback."""
        # Priority 1: Try Fyers API (live mode)
        if self.fyers_available:
            try:
                from fyers_apiv3 import fyersModel  # type: ignore

                fyers = fyersModel.FyersModel(
                    client_id=self.fyers_api_key,
                    token=self.fyers_access_token,
                    log_path=Path(__file__).parent.parent / "logs",
                )

                response = fyers.funds()
                if response and "data" in response:
                    logger.debug(f"✓ Fetched wallet data from Fyers")
                    return response["data"]
            except Exception as e:
                logger.warning(f"Could not fetch from Fyers, falling back to OpenAlgo: {e}")
        
        # Priority 2: Try OpenAlgo API (analyzer mode)
        if self.openalgo_client:
            try:
                resp = self.openalgo_client.funds()
                if resp and "data" in resp:
                    data = resp["data"]
                    if isinstance(data, list) and len(data) > 0:
                        data = data[0]
                    logger.debug(f"✓ Fetched wallet data from OpenAlgo (fallback)")
                    return {
                        "available_balance": float(data.get("availablecash", 0)),
                        "utilisedMargin": float(data.get("utiliseddebits", 0)),
                        "availableMargin": float(data.get("availablecash", 0)),
                        "pnl": float(data.get("m2munrealized", 0)),
                    }
            except Exception as e:
                logger.warning(f"Could not fetch from OpenAlgo: {e}")
        
        # Priority 3: Return mock data
        logger.debug(f"Using mock wallet data (no live data available)")
        return self._mock_wallet_data()

    def _mock_wallet_data(self) -> dict:
        """Return mock wallet data when API is unavailable."""
        return {
            "available_balance": 1000000,
            "utilisedMargin": 0,
            "availableMargin": 1000000,
            "pnl": 0,
            "timestamp": datetime.now().isoformat(),
        }

    def write_wallet_json(self, output_path: Optional[str] = None) -> str:
        """Write wallet data to JSON file for React dashboard to read."""
        if output_path is None:
            output_path = Path(__file__).parent.parent / "logs" / "wallet_data.json"
        else:
            output_path = Path(output_path)

        data = self.get_wallet_data()
        data["timestamp"] = datetime.now().isoformat()

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Wallet data written to {output_path}")
        return str(output_path)


def export_dashboard_data(mode: str = "analyzer") -> dict:
    """
    Export dashboard data based on mode.
    
    Args:
        mode: "analyzer" (OpenAlgo data) or "live" (Fyers data)
    
    Returns:
        Dictionary with exported file paths
    """
    result = {}

    # Get OpenAlgo data (always needed for analyzer mode)
    api_key = os.getenv("OPENALGO_API_KEY", "demo")
    host = os.getenv("OPENALGO_HOST", "http://localhost:5010")
    dashboard_provider = DashboardDataProvider(api_key, host)
    dashboard_path = dashboard_provider.write_dashboard_json()
    result["dashboard_data"] = dashboard_path

    # Get Fyers wallet data (for live mode)
    if mode.lower() == "live":
        wallet_provider = FyersWalletProvider()
        wallet_path = wallet_provider.write_wallet_json()
        result["wallet_data"] = wallet_path

    return result


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "analyzer"
    result = export_dashboard_data(mode)
    print(json.dumps(result, indent=2))
