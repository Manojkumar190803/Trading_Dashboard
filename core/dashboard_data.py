"""Fetch real account data from OpenAlgo and Fyers for dashboard display."""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("core.dashboard_data")


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

        logger.info(f"Dashboard data written to {output_path}")
        return str(output_path)


class FyersWalletProvider:
    """Fetch wallet and balance data from Fyers broker."""

    def __init__(self, fyers_api_key: Optional[str] = None, fyers_access_token: Optional[str] = None):
        """Initialize with Fyers credentials."""
        self.fyers_api_key = fyers_api_key or os.getenv("FYERS_API_KEY")
        self.fyers_access_token = fyers_access_token or os.getenv("FYERS_ACCESS_TOKEN")
        self.available = bool(self.fyers_api_key and self.fyers_access_token)

    def get_wallet_data(self) -> dict:
        """Fetch wallet balance from Fyers."""
        if not self.available:
            return self._mock_wallet_data()

        try:
            from fyers_apiv3 import fyersModel  # type: ignore

            fyers = fyersModel.FyersModel(
                client_id=self.fyers_api_key,
                token=self.fyers_access_token,
                log_path=Path(__file__).parent.parent / "logs",
            )

            response = fyers.funds()
            if response and "data" in response:
                return response["data"]
            return self._mock_wallet_data()
        except Exception as e:
            logger.error(f"Error fetching Fyers wallet: {e}")
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
