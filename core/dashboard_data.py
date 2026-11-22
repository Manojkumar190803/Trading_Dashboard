"""Fetch account data from the broker connected to OpenAlgo for dashboard display."""

import json
import logging
import os
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from core import db_sync

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
    completed_entries_today = 0
    for order in orders:
        if not isinstance(order, dict):
            continue
        order_status = str(order.get("order_status") or order.get("status") or "").lower()
        action = str(order.get("action") or order.get("side") or "").upper()
        if order_status not in {"complete", "filled", "executed"} or action != "BUY":
            continue
        timestamp = order.get("timestamp") or order.get("created_at") or order.get("order_timestamp")
        if not timestamp:
            continue
        try:
            if isinstance(timestamp, datetime):
                order_time = timestamp
            else:
                timestamp_text = str(timestamp).strip()
                try:
                    order_time = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
                except ValueError:
                    order_time = datetime.strptime(timestamp_text, "%d-%b-%Y %H:%M:%S")
            if order_time.tzinfo is not None:
                local_timezone = datetime.now().astimezone().tzinfo
                order_time = order_time.astimezone(local_timezone)
        except (TypeError, ValueError):
            continue
        if order_time.date() == trading_date:
            completed_entries_today += 1

    return pnl, completed_entries_today, has_pnl_data or completed_entries_today > 0


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
        if not api_key or not api_key.strip() or "YOUR_" in api_key.upper():
            raise RuntimeError("OPENALGO_API_KEY is missing or is still a placeholder.")
        if not host or not host.strip():
            raise RuntimeError("OPENALGO_HOST is missing.")

        try:
            from openalgo import api  # type: ignore
            self.api_key = api_key.strip()
            self.host = host.strip().rstrip("/")
            self.client = api(api_key=self.api_key, host=self.host)
            self.strategy_tag = strategy_tag
            self._snapshot_lock = threading.Lock()
        except ImportError as exc:
            raise RuntimeError(
                "openalgo package not installed. Install it with `pip install openalgo`."
            ) from exc

    def get_account_summary(self) -> dict:
        """Fetch account summary with balance, P&L, positions, and mode."""
        try:
            positions = self._fetch_positions()
            data = {
                "timestamp": datetime.now().isoformat(),
                "mode": self._detect_mode(positions),  # Get current OpenAlgo mode
                "positions": positions,
                "orders": self._fetch_orders(),
                "account": self._fetch_account_info(),
            }
            data["account"]["broker_name"] = self._fetch_broker_name()
            return data
        except Exception as e:
            logger.exception("Error fetching OpenAlgo account data")
            raise RuntimeError("Could not fetch account data from OpenAlgo.") from e

    def _fetch_broker_name(self) -> Optional[str]:
        """Get the active broker identifier from OpenAlgo's authenticated ping."""
        try:
            response = requests.post(
                f"{self.host}/api/v1/ping",
                json={"apikey": self.api_key},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            broker = payload.get("data", {}).get("broker") if isinstance(payload, dict) else None
            if payload.get("status") != "success" or not isinstance(broker, str) or not broker.strip():
                raise ValueError("OpenAlgo ping response did not include a broker name.")
            return broker.strip()
        except (requests.RequestException, ValueError, AttributeError) as exc:
            logger.error("Could not determine the broker connected to OpenAlgo: %s", exc)
            return None

    def _fetch_positions(self) -> list[dict]:
        """Fetch open positions from OpenAlgo."""
        try:
            resp = self.client.positionbook()
            if not isinstance(resp, dict) or "data" not in resp:
                raise RuntimeError("OpenAlgo returned an invalid position-book response.")
            return resp["data"]
        except Exception as e:
            logger.exception("Error fetching positions from OpenAlgo")
            raise RuntimeError("Could not fetch positions from OpenAlgo.") from e

    def _fetch_orders(self) -> list[dict]:
        """Fetch order book from OpenAlgo."""
        try:
            resp = self.client.orderbook()
            if not isinstance(resp, dict) or "data" not in resp:
                raise RuntimeError("OpenAlgo returned an invalid order-book response.")
            return resp["data"]
        except Exception as e:
            logger.exception("Error fetching orders from OpenAlgo")
            raise RuntimeError("Could not fetch orders from OpenAlgo.") from e

    def _fetch_account_info(self) -> dict:
        """Fetch account balance and margin info from OpenAlgo and normalize field names."""
        try:
            resp = self.client.funds()
            if not isinstance(resp, dict) or "data" not in resp:
                raise RuntimeError("OpenAlgo returned an invalid funds response.")
            data = resp["data"]
            if isinstance(data, list):
                if not data:
                    raise RuntimeError("OpenAlgo returned an empty funds response.")
                data = data[0]
            if not isinstance(data, dict):
                raise RuntimeError("OpenAlgo returned invalid funds data.")

            available_cash = self._first_value(
                data,
                "availableMargin",
                "available_margin",
                "availablecash",
                "availableCash",
                "available_cash",
                "margin",
                "cash",
            )
            if available_cash is None:
                raise RuntimeError("OpenAlgo funds response contains no available balance.")
            cash = self._safe_float(available_cash)
            unrealized_pnl = self._safe_float(
                self._first_value(data, "m2munrealized", "m2mUnrealized", "mtm", "pnl")
            )
            realized_pnl = self._safe_float(
                self._first_value(data, "m2mrealized", "m2mRealized", "realized_pnl")
            )
            used_margin = self._safe_float(
                self._first_value(data, "utiliseddebits", "utilisedDebits", "used_margin")
            )

            normalized = dict(data)
            normalized.update({
                "available_balance": cash,
                "availableMargin": cash,
                "margin": cash,
                "available_margin": cash,
                "mtm": unrealized_pnl,
                "pnl": unrealized_pnl,
                "realized_pnl": realized_pnl,
                "m2mrealized": realized_pnl,
                "used_margin": used_margin,
                "utiliseddebits": used_margin,
                "source": "openalgo",
            })
            return normalized
        except Exception as e:
            logger.exception("Error fetching funds from OpenAlgo")
            raise RuntimeError("Could not fetch funds from OpenAlgo.") from e

    def _detect_mode(self, positions: Optional[list[dict]] = None) -> str:
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
            positions = positions if positions is not None else self._fetch_positions()
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

    @staticmethod
    def _first_value(data: dict, *keys: str) -> object:
        return next(
            (data[key] for key in keys if data.get(key) is not None and data[key] != ""),
            None,
        )

    def write_dashboard_json(self, output_path: Optional[str] = None) -> str:
        """Write account data to JSON file for React dashboard to read."""
        if output_path is None:
            output_path = Path(__file__).parent.parent / "logs" / "dashboard_data.json"
        else:
            output_path = Path(output_path)

        data = self.get_account_summary()

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with self._snapshot_lock:
            temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
            with temporary_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temporary_path, output_path)
            _write_daily_pnl_snapshot(data, output_path.parent / "daily_pnl.json")

        db_sync.sync_dashboard_snapshot(data)

        logger.info(f"Dashboard data written to {output_path}")
        return str(output_path)

    def write_position_tick(
        self,
        symbol: str,
        ltp: float,
        output_path: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> bool:
        """Apply a websocket price update to an already-known open position."""
        path = Path(output_path) if output_path else Path(__file__).parent.parent / "logs" / "dashboard_data.json"
        changed = False
        with self._snapshot_lock:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, json.JSONDecodeError):
                return False

            positions = data.get("positions") or []
            for position in positions:
                if not isinstance(position, dict) or str(position.get("symbol") or "") != symbol:
                    continue
                if exchange and str(position.get("exchange") or "").upper() != exchange.upper():
                    continue
                quantity = self._safe_float(
                    self._first_value(position, "quantity", "qty", "netqty", "net_qty")
                )
                if quantity == 0:
                    continue
                previous_ltp = self._safe_float(position.get("ltp"))
                if previous_ltp > 0:
                    pnl_delta = (float(ltp) - previous_ltp) * quantity
                    position["pnl"] = self._safe_float(position.get("pnl")) + pnl_delta
                    account = data.setdefault("account", {})
                    for key in ("mtm", "m2munrealized", "pnl"):
                        if account.get(key) is not None:
                            account[key] = self._safe_float(account[key]) + pnl_delta
                position["ltp"] = float(ltp)
                changed = True

            if not changed:
                return False

            captured_at = datetime.now()
            data["timestamp"] = captured_at.isoformat()
            temporary_path = path.with_suffix(path.suffix + ".tmp")
            temporary_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(temporary_path, path)
            _write_daily_pnl_snapshot(data, path.parent / "daily_pnl.json", captured_at)

        return True


def export_dashboard_data(mode: str = "analyzer") -> dict:
    """
    Export dashboard data based on mode.
    
    Args:
        mode: Retained for compatibility; all dashboard account data now comes from OpenAlgo.
    
    Returns:
        Dictionary with exported file paths
    """
    result = {}

    load_dotenv(Path(__file__).parent.parent / ".env")
    logger.debug("Export requested with compatibility mode %s; using OpenAlgo.", mode)
    api_key = os.getenv("OPENALGO_API_KEY", "")
    host = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5002")
    dashboard_provider = DashboardDataProvider(api_key, host)
    dashboard_path = dashboard_provider.write_dashboard_json()
    result["dashboard_data"] = dashboard_path

    return result


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "analyzer"
    result = export_dashboard_data(mode)
    print(json.dumps(result, indent=2))
