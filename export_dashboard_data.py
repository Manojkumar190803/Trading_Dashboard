#!/usr/bin/env python3
"""
Export real OpenAlgo account data for React dashboard.
Run this as a daemon or cron job to continuously update dashboard_data.json and wallet_data.json
"""

import logging
import json
import os
import sys
import threading
import time
from pathlib import Path

import websocket

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from core.dashboard_data import DashboardDataProvider

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent / 'logs' / 'dashboard_export.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("dashboard_export")
SNAPSHOT_PATH = Path(__file__).parent / "logs" / "dashboard_data.json"


def _active_position_subscriptions() -> dict[tuple[str, str], None]:
    try:
        data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    subscriptions = {}
    for position in data.get("positions") or []:
        if not isinstance(position, dict):
            continue
        symbol = str(position.get("symbol") or "").strip()
        exchange = str(position.get("exchange") or "").strip().upper()
        quantity = 0.0
        for key in ("netqty", "net_qty", "quantity", "qty"):
            try:
                quantity = float(position.get(key) or 0)
            except (TypeError, ValueError):
                continue
            if quantity != 0:
                break
        if symbol and exchange and quantity != 0:
            subscriptions[(symbol, exchange)] = None
    return subscriptions


def _websocket_tick_worker(
    provider: DashboardDataProvider,
    ws_url: str,
    api_key: str,
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        connection = None
        try:
            connection = websocket.create_connection(ws_url, timeout=5)
            connection.send(json.dumps({"action": "authenticate", "apikey": api_key}))
            auth_response = json.loads(connection.recv())
            if auth_response.get("type") != "auth" or auth_response.get("status") != "success":
                raise RuntimeError("OpenAlgo websocket authentication failed")
            connection.send(json.dumps({"action": "subscribe_orders"}))
            logger.info("Connected to OpenAlgo websocket for active-position ticks")
            connection.settimeout(1)
            subscribed: set[tuple[str, str]] = set()
            next_reconcile = 0.0
            last_order_refresh = 0.0

            while not stop_event.is_set():
                now = time.monotonic()
                if now >= next_reconcile:
                    wanted = set(_active_position_subscriptions())
                    added = wanted - subscribed
                    removed = subscribed - wanted
                    if added:
                        connection.send(json.dumps({
                            "action": "subscribe",
                            "mode": "LTP",
                            "symbols": [{"symbol": symbol, "exchange": exchange} for symbol, exchange in added],
                        }))
                    if removed:
                        connection.send(json.dumps({
                            "action": "unsubscribe",
                            "mode": "LTP",
                            "symbols": [{"symbol": symbol, "exchange": exchange} for symbol, exchange in removed],
                        }))
                    subscribed = wanted
                    next_reconcile = now + 5

                try:
                    message = json.loads(connection.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                if message.get("type") == "order_update":
                    try:
                        filled_quantity = float(message.get("filled_quantity") or 0)
                    except (TypeError, ValueError):
                        filled_quantity = 0
                    if filled_quantity > 0 and now - last_order_refresh >= 2:
                        try:
                            provider.write_dashboard_json()
                            last_order_refresh = now
                            next_reconcile = 0
                        except Exception:
                            logger.exception("Could not refresh dashboard after an order fill")
                    continue
                if message.get("type") != "market_data":
                    continue
                tick = message.get("data") or {}
                try:
                    ltp = float(tick["ltp"])
                except (KeyError, TypeError, ValueError):
                    continue
                provider.write_position_tick(
                    str(message.get("symbol") or ""),
                    ltp,
                    exchange=str(message.get("exchange") or ""),
                )
        except Exception:
            if not stop_event.is_set():
                logger.exception("OpenAlgo websocket disconnected; reconnecting")
        finally:
            if connection is not None:
                connection.close()
        stop_event.wait(5)


def main(mode: str = "analyzer", interval: int = 120):
    """
    Continuously export dashboard data.
    
    Args:
        mode: Retained for compatibility; account data always comes from configured OpenAlgo.
        interval: Snapshot interval in seconds while no position is active
    """
    active_interval = max(5, int(os.getenv("ACTIVE_EXPORT_INTERVAL", "30")))
    ws_url = os.getenv("OPENALGO_WS_URL", "").strip()
    api_key = os.getenv("OPENALGO_API_KEY", "").strip()
    logger.info(
        "Starting dashboard export daemon - flat_interval=%ss active_interval=%ss",
        interval,
        active_interval,
    )
    
    dashboard_provider = DashboardDataProvider(
        api_key=os.getenv("OPENALGO_API_KEY", ""),
        host=os.getenv("OPENALGO_HOST", "http://127.0.0.1:5002"),
    )

    stop_event = threading.Event()
    if ws_url and api_key:
        threading.Thread(
            target=_websocket_tick_worker,
            args=(dashboard_provider, ws_url, api_key, stop_event),
            daemon=True,
        ).start()
    else:
        logger.warning("OpenAlgo websocket URL or API key is missing; live tick updates are disabled")

    try:
        while True:
            try:
                dashboard_provider.write_dashboard_json()
            except Exception:
                logger.exception("Could not export OpenAlgo dashboard data")
            active = bool(_active_position_subscriptions())
            time.sleep(active_interval if active else interval)
    except KeyboardInterrupt:
        logger.info("Dashboard export daemon stopped")
        stop_event.set()
    except Exception as e:
        logger.error(f"Dashboard export daemon error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else os.getenv("STRATEGY_MODE", "analyzer")
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.getenv("EXPORT_INTERVAL", "120"))
    
    main(mode, interval)
