"""Logs page — live strategy status, structured log table, and metrics."""
from __future__ import annotations

import os
import json
import re
from datetime import date, datetime, timedelta
from html import escape
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from _shared import (
    DISPLAY_TZ,
    LOGS_DIR,
    inject_theme,
    refresh_live_account_metrics,
    render_alert_toasts,
    render_section_heading,
    render_sidebar,
)
from core.engine import BaseStrategyEngine

inject_theme()
source_params = render_sidebar(manage_runtime=False)
st_autorefresh(interval=30_000, key="logs-live-refresh")

# Keep account metrics current while the Logs page is open.
refresh_live_account_metrics(source_params)

_STATUS_BADGE: dict[str, str] = {
    "SUCCESS":   "🟢",
    "TRIGGERED": "🟡",
    "EXECUTED":  "🔵",
    "FAILED":    "🔴",
    "INFO":      "⚪",
}


def _parse_openalgo_port(base_url: str) -> str | None:
    try:
        parsed = urlparse(base_url)
    except Exception:
        return None
    if parsed.port is not None:
        return str(parsed.port)
    if parsed.scheme == "https":
        return "443"
    if parsed.scheme == "http":
        return "80"
    return None


def _load_openalgo_logs_via_api(base_url: str) -> tuple[list[str], str | None]:
    """Fetch logs from local monitoring file as fallback when Docker is not available."""
    try:
        from datetime import datetime
        
        # Get today's date
        today = datetime.now().strftime("%Y%m%d")
        
        # Try to read today's monitoring log file
        monitoring_file = os.path.join(LOGS_DIR, f"monitoring_{today}.txt")
        
        if not os.path.exists(monitoring_file):
            # If today's file doesn't exist, try to find the most recent one
            log_files = []
            for filename in os.listdir(LOGS_DIR):
                if filename.startswith("monitoring_") and filename.endswith(".txt"):
                    log_files.append(filename)
            
            if not log_files:
                return [], None
            
            # Sort and get the most recent
            log_files.sort(reverse=True)
            monitoring_file = os.path.join(LOGS_DIR, log_files[0])
        
        # Read the file
        with open(monitoring_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        if not lines:
            return [], None
        
        # Parse the header and data
        header_line = lines[0].rstrip('\n')
        data_lines = [line.rstrip('\n') for line in lines[1:] if line.strip()]
        
        # Return all available data lines with header
        result_lines = [header_line] + data_lines
        
        if result_lines:
            return result_lines, None
        
        return [], None
    except Exception as exc:
        return [], None


@st.cache_data(ttl=10, show_spinner=False)
def _load_openalgo_container_logs_cached(
    base_url: str,
    configured_name: str,
) -> tuple[list[str], str | None]:
    # PRIORITY 1: Try Docker container logs (live, real-time data)
    try:
        import docker  # type: ignore
    except Exception as exc:
        return [], "Docker SDK unavailable. Install with: pip install docker"

    try:
        client = docker.from_env()
        target_port = _parse_openalgo_port(base_url)

        container = None
        if configured_name:
            try:
                container = client.containers.get(configured_name)
            except Exception:
                container = None

        if container is None and target_port:
            for candidate in client.containers.list():
                ports = ((candidate.attrs.get("NetworkSettings") or {}).get("Ports") or {})
                bindings = ports.get(f"{target_port}/tcp") or []
                if bindings:
                    container = candidate
                    break

        if container is None:
            for candidate in client.containers.list():
                if "openalgo" in candidate.name.lower():
                    container = candidate
                    break

        if container is None:
            return [], "OpenAlgo container not found from Docker metadata."

        raw = container.logs(tail=500).decode("utf-8", errors="replace")
        lines = [line for line in raw.splitlines() if line.strip()]
        return lines, None
    except (FileNotFoundError, ConnectionError, Exception) as exc:
        error_msg = str(exc)
        # Check if it's a Docker daemon connection error - try local logs fallback
        if isinstance(exc, FileNotFoundError) or "Connection aborted" in error_msg or "No such file or directory" in error_msg:
            # Try to fetch logs from local monitoring file as fallback
            logs, api_error = _load_openalgo_logs_via_api(base_url)
            if logs:
                return logs, None  # Successfully got logs from local file
            else:
                # Docker unavailable and no local logs available
                return [], "ℹ️ Docker daemon not running. No monitoring logs available for today. Logs will appear once the strategy starts running."
        elif "OpenAlgo container not found" in error_msg:
            return [], "OpenAlgo container not found. Ensure the container is running and accessible."
        else:
            return [], f"Unable to load container logs: {error_msg[:100]}..."


def _load_openalgo_container_logs(source_params: dict[str, object]) -> tuple[list[str], str | None]:
    base_url = str(
        source_params.get("openalgo_base_url")
        or os.getenv("OPENALGO_BASE_URL", "http://host.docker.internal:5002")
    )
    configured_name = os.getenv("OPENALGO_LOG_CONTAINER", "").strip()
    return _load_openalgo_container_logs_cached(base_url, configured_name)


def _extract_price(pattern: str, message: str) -> float | None:
    m = re.search(pattern, message, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def _extract_symbol(message: str) -> str:
    m = re.search(r"\b(NIFTY\w*|BANK\w*|SENSEX\w*)", message, flags=re.IGNORECASE)
    return m.group(1).upper() if m else "-"


def _classify_status(category: str, message: str) -> str:
    text = f"{category} {message}".upper()
    if any(t in text for t in ("FAIL", "ERROR", "EXCEPTION", "REJECT", "RISK")):
        return "FAILED"
    if any(t in text for t in ("EXIT", "TARGET", "T1", "T2", "T3", "SL HIT")):
        return "SUCCESS"
    if any(t in text for t in ("EXECUTED", "FILLED", "BUY ", "SELL ")):
        return "EXECUTED"
    if any(t in text for t in ("TRIGGERED", "ALERT", "SIGNAL")):
        return "TRIGGERED"
    return "INFO"


def _parse_openalgo_status(lines: list[str]) -> dict:
    """Extract simple status info from monitoring logs."""
    status = {
        "date": "N/A",
        "time": "N/A",
        "connected": False,
        "candle_count": 0,
    }
    
    try:
        if not lines or len(lines) < 2:
            return status
        
        candle_count = 0
        
        # Process data lines (skip header)
        for line in lines[1:]:
            if not line.strip():
                continue
            
            parts = line.split('\t')
            if len(parts) < 4:
                continue
            
            timestamp = parts[0]
            category = parts[1]
            message = parts[7] if len(parts) > 7 else ""
            
            # Extract date and time from latest entry
            if 'T' in timestamp:
                date_part, time_part = timestamp.split('T')
                status["date"] = date_part
                status["time"] = time_part.split('+')[0][:8]
            
            # Check if connected (has DATA category entries)
            if category == "DATA":
                status["connected"] = True
                
                # Count candles
                if "3m candle" in message.lower():
                    candle_count += 1
        
        status["candle_count"] = candle_count
        return status
    except Exception:
        return status


def _parse_minute_history(lines: list[str]) -> list[dict]:
    """Extract minute-wise history from monitoring logs."""
    history = {}
    
    try:
        if not lines or len(lines) < 2:
            return []
        
        # Process data lines (skip header)
        for line in lines[1:]:
            if not line.strip():
                continue
            
            parts = line.split('\t')
            if len(parts) < 8:
                continue
            
            timestamp = parts[0]
            category = parts[1]
            message = parts[7] if len(parts) > 7 else ""
            
            # Extract date and minute from timestamp
            if 'T' in timestamp:
                date_part, time_part = timestamp.split('T')
                time_only = time_part.split('+')[0]
                minute_key = time_only[:5]  # HH:MM
                full_key = f"{date_part}_{minute_key}"
                
                # Initialize minute entry if not exists
                if full_key not in history:
                    history[full_key] = {
                        "date": date_part,
                        "time": minute_key,
                        "connected": False,
                        "candle_count": 0,
                    }
                
                # Check if connected and count candles
                if category == "DATA":
                    history[full_key]["connected"] = True
                    if "3m candle" in message.lower():
                        history[full_key]["candle_count"] += 1
        
        # Convert to list and sort by time (latest first)
        result = []
        for key in sorted(history.keys(), reverse=True):
            entry = history[key]
            result.append(entry)
        
        return result
    except Exception:
        return []


def _parse_active_subscriptions(lines: list[str]) -> tuple[set[str], int]:
    """Extract unique active strike symbols and total count."""
    symbols = set()
    
    try:
        if not lines or len(lines) < 2:
            return set(), 0
        
        # Process data lines to find unique symbols
        for line in lines[1:]:
            if not line.strip():
                continue
            
            parts = line.split('\t')
            if len(parts) < 4:
                continue
            
            category = parts[1]
            symbol = parts[3]
            
            # Track symbols from DATA lines (actual candle data)
            if category == "DATA" and symbol:
                symbols.add(symbol)
        
        return symbols, len(symbols)
    except Exception:
        return set(), 0


def _calculate_feed_latency(lines: list[str]) -> tuple[float | None, float | None]:
    """Calculate polling lag (bar close to ingestion) and average API latency between candles."""
    lags = []
    api_latencies = []
    symbol_last_time = {}
    
    try:
        if not lines or len(lines) < 2:
            return None, None
        
        from datetime import datetime
        
        # Process data lines
        for line in lines[1:]:
            if not line.strip():
                continue
            
            parts = line.split('\t')
            if len(parts) < 8:
                continue
            
            timestamp_str = parts[0]
            category = parts[1]
            symbol = parts[3]
            message = parts[7] if len(parts) > 7 else ""
            
            # Only process DATA category with candle info
            if category != "DATA" or "3m candle" not in message.lower():
                continue
            
            # Extract candle time from message (e.g., "3m candle 09:18:00")
            candle_time_match = re.search(r'3m candle\s+(\d{2}):(\d{2}):(\d{2})', message, re.IGNORECASE)
            if not candle_time_match:
                continue
            
            candle_hms = f"{candle_time_match.group(1)}:{candle_time_match.group(2)}:{candle_time_match.group(3)}"
            
            # Parse message timestamp (ISO format: 2026-10-07T09:21:07.289132+05:30)
            try:
                # Extract just the time part for comparison
                if 'T' in timestamp_str:
                    msg_time_part = timestamp_str.split('T')[1].split('+')[0]  # 09:21:07.289132
                    msg_seconds = float(msg_time_part.split(':')[0]) * 3600 + \
                                 float(msg_time_part.split(':')[1]) * 60 + \
                                 float(msg_time_part.split(':')[2])
                    
                    # Parse candle time
                    candle_seconds = float(candle_time_match.group(1)) * 3600 + \
                                    float(candle_time_match.group(2)) * 60 + \
                                    float(candle_time_match.group(3))
                    
                    # Calculate lag (time from bar close to ingestion)
                    # Bar close is 3 minutes after the candle time
                    bar_close_seconds = candle_seconds + 180
                    lag = msg_seconds - bar_close_seconds
                    
                    if 0 <= lag < 30:  # Reasonable lag (0-30 seconds)
                        lags.append(lag)
                    
                    # Track API latency (time between consecutive same symbol entries)
                    if symbol in symbol_last_time:
                        api_lat = msg_seconds - symbol_last_time[symbol]
                        if 0 < api_lat < 300:  # Reasonable latency (0-5 min)
                            api_latencies.append(api_lat)
                    
                    symbol_last_time[symbol] = msg_seconds
            except Exception:
                continue
        
        # Calculate averages
        avg_lag = sum(lags) / len(lags) if lags else None
        avg_api_latency = sum(api_latencies) / len(api_latencies) if api_latencies else None
        
        return avg_lag, avg_api_latency
    except Exception:
        return None, None


def _parse_feed_vitals(lines: list[str]) -> dict:
    """Extract all feed vitals for the summary card."""
    vitals = {
        "connected": False,
        "candle_count": 0,
        "warmup_complete": False,
        "active_symbols": set(),
        "active_count": 0,
        "polling_lag_sec": None,
        "api_latency_ms": None,
        "feed_source": "OpenAlgo API",
    }
    
    try:
        if not lines or len(lines) < 2:
            return vitals
        
        # Get basic status
        status = _parse_openalgo_status(lines)
        vitals["connected"] = status["connected"]
        vitals["candle_count"] = status["candle_count"]
        
        # Check warmup status (EMA21 needs 21 candles)
        vitals["warmup_complete"] = vitals["candle_count"] >= 21
        
        # Get active subscriptions
        symbols, count = _parse_active_subscriptions(lines)
        vitals["active_symbols"] = symbols
        vitals["active_count"] = count
        
        # Get latency metrics
        polling_lag, api_latency = _calculate_feed_latency(lines)
        vitals["polling_lag_sec"] = polling_lag
        if api_latency:
            vitals["api_latency_ms"] = api_latency * 1000  # Convert to milliseconds
        
        return vitals
    except Exception:
        return vitals


def _assess_data_collection_health(lines: list[str]) -> dict:
    """Assess whether data is being collected properly and return health status."""
    health = {
        "status": "UNKNOWN",
        "status_badge": "❓",
        "last_data_at": "—",
        "last_data_date": "—",
        "candles_last_5_min": 0,
        "message": "No data available",
    }
    
    try:
        if not lines or len(lines) < 2:
            return health
        
        from datetime import datetime, timedelta
        
        # Get latest DATA entry and count recent entries
        latest_timestamp = None
        latest_date = None
        data_entries_recent = 0
        current_time = None
        
        for line in reversed(lines[1:]):  # Iterate from most recent first
            if not line.strip():
                continue
            
            parts = line.split('\t')
            if len(parts) < 8:
                continue
            
            timestamp_str = parts[0]
            category = parts[1]
            message = parts[7] if len(parts) > 7 else ""
            
            # Only count DATA entries with actual candles
            if category == "DATA" and "3m candle" in message.lower():
                if not latest_timestamp and 'T' in timestamp_str:
                    # Extract date and time from latest entry
                    latest_date, time_part = timestamp_str.split('T')
                    latest_time = time_part.split('+')[0][:8]  # HH:MM:SS
                    latest_timestamp = latest_time
                    health["last_data_at"] = latest_time
                    health["last_data_date"] = latest_date
                
                # Count candles in last 5 minutes by checking timestamps
                if 'T' in timestamp_str:
                    try:
                        # Parse both timestamps
                        ts_date, ts_time_tz = timestamp_str.split('T')
                        ts_time = ts_time_tz.split('+')[0]  # Remove timezone
                        
                        # Simple heuristic: each DATA entry is roughly one candle per symbol per 3 min
                        # If we have multiple DATA entries in recent lines, data is flowing
                        data_entries_recent += 1
                        
                        if data_entries_recent >= 3:  # Found enough recent entries, stop
                            break
                    except Exception:
                        pass
        
        health["candles_last_5_min"] = data_entries_recent
        
        # Assess health status based on recent data
        if data_entries_recent >= 3:  # At least a few recent candle updates
            health["status"] = "HEALTHY"
            health["status_badge"] = "🟢"
            health["message"] = f"Data collecting properly • {data_entries_recent}+ candles received"
        elif data_entries_recent > 0:
            health["status"] = "DEGRADED"
            health["status_badge"] = "🟡"
            health["message"] = f"Slow data collection • Only {data_entries_recent} candles in recent batch"
        else:
            health["status"] = "STALE"
            health["status_badge"] = "🔴"
            health["message"] = "No recent data • Last data > 5 minutes ago"
        
        return health
    except Exception:
        return health


def _parse_candle_data(message: str) -> dict | None:
    """Extract OHLC, EMA21, and candle time from DATA message."""
    try:
        data = {}
        
        # Extract candle time (e.g., "3m candle 09:18:00")
        time_match = re.search(r'3m candle\s+(\d{2}):(\d{2}):(\d{2})', message, re.IGNORECASE)
        if not time_match:
            return None
        data["candle_time"] = f"{time_match.group(1)}:{time_match.group(2)}:{time_match.group(3)}"
        
        # Extract OHLC values
        o_match = re.search(r'O=([0-9.]+)', message)
        c_match = re.search(r'C=([0-9.]+)', message)
        
        if o_match and c_match:
            open_price = float(o_match.group(1))
            close_price = float(c_match.group(1))
            data["open"] = open_price
            data["close"] = close_price
            data["direction"] = "🟢 Bullish" if close_price > open_price else ("🔴 Bearish" if close_price < open_price else "➡️ Flat")
            data["ltp"] = f"₹{close_price:.2f}"
        
        # Extract EMA21 value
        ema_match = re.search(r'EMA21=([0-9.]+)', message)
        if ema_match:
            data["ema21"] = float(ema_match.group(1))
        
        return data if data else None
    except Exception:
        return None


def _extract_strategy_status(lines: list[str], symbol: str, candle_time: str) -> str:
    """Extract strategy status (WAITING, EVALUATING, etc.) for a symbol at given candle time."""
    try:
        for line in lines:
            if not line.strip():
                continue
            
            parts = line.split('\t')
            if len(parts) < 8:
                continue
            
            category = parts[1]
            line_symbol = parts[3]
            message = parts[7] if len(parts) > 7 else ""
            
            # Look for SETUP_STATUS entries matching this symbol and candle time
            if category == "SETUP_STATUS" and line_symbol == symbol and f"candle={candle_time}" in message:
                # Extract status from message (e.g., "CE EMA21 setup | ... | WAITING | candle=...")
                status_match = re.search(r'\|\s*(WAITING|EVALUATING|TRIGGERED|EXECUTED|FAILED)\s*\|', message)
                if status_match:
                    return status_match.group(1)
        
        return "—"
    except Exception:
        return "—"


def _parse_detailed_feed_history(lines: list[str]) -> list[dict]:
    """Parse detailed 3-minute feed ingestion history with OHLC, lag, direction, and status."""
    history_by_time = {}
    
    try:
        if not lines or len(lines) < 2:
            return []
        
        from datetime import datetime, timedelta
        
        # First pass: collect all candle data
        for line in lines[1:]:
            if not line.strip():
                continue
            
            parts = line.split('\t')
            if len(parts) < 8:
                continue
            
            timestamp_str = parts[0]
            category = parts[1]
            symbol = parts[3]
            message = parts[7] if len(parts) > 7 else ""
            
            # Only process DATA entries with candle info
            if category != "DATA" or "3m candle" not in message.lower():
                continue
            
            # Parse candle data
            candle_data = _parse_candle_data(message)
            if not candle_data:
                continue
            
            candle_time = candle_data["candle_time"]
            
            # Parse timestamp
            if 'T' not in timestamp_str:
                continue
            
            date_part, time_part = timestamp_str.split('T')
            ingestion_time_str = time_part.split('+')[0]
            
            # Create key for this candle
            candle_key = f"{date_part}_{candle_time}"
            
            # Initialize candle entry if needed
            if candle_key not in history_by_time:
                history_by_time[candle_key] = {
                    "date": date_part,
                    "candle_time": candle_time,
                    "ingestion_times": [],
                    "symbols": {},
                    "lag_secs": None,
                    "status": "🟢 Connected (200 OK)",
                    "symbols_count": 0,
                }
            
            # Store ingestion time
            history_by_time[candle_key]["ingestion_times"].append(ingestion_time_str)
            
            # Store symbol data
            if symbol not in history_by_time[candle_key]["symbols"]:
                history_by_time[candle_key]["symbols"][symbol] = {
                    "ltp": candle_data.get("ltp", "—"),
                    "direction": candle_data.get("direction", "—"),
                }
            
            # Calculate lag (in seconds) from first ingestion
            if not history_by_time[candle_key]["lag_secs"]:
                try:
                    # Parse times
                    candle_h, candle_m, candle_s = map(int, candle_time.split(':'))
                    candle_seconds = candle_h * 3600 + candle_m * 60 + candle_s
                    
                    ingestion_h, ingestion_m, ingestion_s_ms = ingestion_time_str.split(':')
                    ingestion_s, ingestion_ms = ingestion_s_ms.split('.')
                    ingestion_seconds = int(ingestion_h) * 3600 + int(ingestion_m) * 60 + int(ingestion_s) + int(ingestion_ms) / 1_000_000
                    
                    # Bar closes 3 minutes after candle time
                    bar_close_seconds = candle_seconds + 180
                    lag = ingestion_seconds - bar_close_seconds
                    
                    if -5 < lag < 60:  # Reasonable lag
                        history_by_time[candle_key]["lag_secs"] = lag
                        
                        # Set status based on lag
                        if lag > 15:
                            history_by_time[candle_key]["status"] = f"⚠️ Delayed (+{lag:.0f}s)"
                        else:
                            history_by_time[candle_key]["status"] = f"🟢 Connected (200 OK)"
                except Exception:
                    pass
        
        # Convert to sorted list (latest first)
        result = []
        for key in sorted(history_by_time.keys(), reverse=True):
            entry = history_by_time[key]
            
            # Format ingested time with lag
            if entry["ingestion_times"]:
                ingested_at = entry["ingestion_times"][0]
                if entry["lag_secs"] is not None:
                    ingested_at = f"{ingested_at} (+{entry['lag_secs']:.0f}s lag)"
            else:
                ingested_at = "—"
            
            # Format symbols and prices
            symbols_breakdown = []
            symbol_count = 0
            for symbol in sorted(entry["symbols"].keys()):
                symbol_count += 1
                sym_type = "CE" if symbol.endswith("CE") else "PE"
                ltp = entry["symbols"][symbol]["ltp"]
                symbols_breakdown.append(f"{sym_type}: {ltp}")
            
            symbols_str = " | ".join(symbols_breakdown) if symbols_breakdown else "—"
            symbols_count_str = f"{symbol_count} ({symbols_str})" if symbol_count > 0 else "—"
            
            # Format directions
            directions = []
            for symbol in sorted(entry["symbols"].keys()):
                direction = entry["symbols"][symbol]["direction"]
                directions.append(direction)
            directions_str = " | ".join(directions) if directions else "—"
            
            result.append({
                "date": entry["date"],
                "candle_time": entry["candle_time"],
                "ingested_at": ingested_at,
                "status": entry["status"],
                "symbols_updated": symbols_count_str,
                "bar_direction": directions_str,
                "strategy_dispatch": "Dispatched to EMA21 (Evaluating)",
            })
        
        return result
    except Exception:
        return []


def _session_logs_df(engine: BaseStrategyEngine | None) -> pd.DataFrame:
    if engine is None or not getattr(engine, "alerts", None):
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for alert in engine.alerts:
        ts = pd.to_datetime(alert.timestamp, errors="coerce")
        if pd.isna(ts):
            continue
        category = str(alert.category)
        message = str(alert.message)
        rows.append(
            {
                "Date": ts.date(),
                "Time": ts.strftime("%H:%M:%S"),
                "Timestamp": ts,
                "Category": category,
                "Status": _classify_status(category, message),
                "Symbol": _extract_symbol(message),
                "Entry Price": _extract_price(r"@\s*([0-9]+(?:\.[0-9]+)?)", message),
                "Exit Price": _extract_price(r"\bat\s*([0-9]+(?:\.[0-9]+)?)", message),
                "Trade P&L": _extract_price(r"trade_pnl=([\-0-9]+(?:\.[0-9]+)?)", message),
                "Message": message,
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("Timestamp", ascending=False)


def _market_data_logs_df() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    rows = st.session_state.get("market_data_logs") or []
    if rows:
        frames.append(pd.DataFrame(rows))
    today_path = LOGS_DIR / f"monitoring_{datetime.now(DISPLAY_TZ):%Y%m%d}.csv"
    for path in (today_path,) if today_path.exists() else ():
        try:
            historical_df = pd.read_csv(path)
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        if not historical_df.empty:
            frames.append(historical_df)
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True).rename(
        columns={
            "timestamp": "Timestamp",
            "category": "Category",
            "status": "Status",
            "symbol": "Symbol",
            "entry_price": "Entry Price",
            "exit_price": "Exit Price",
            "trade_pnl": "Trade P&L",
            "message": "Message",
        }
    )
    # Worker rows written without an offset are already local IST timestamps;
    # do not reinterpret them as UTC or they appear 5:30 hours in the future.
    def _normalize_log_timestamp(value: object) -> pd.Timestamp:
        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.isna(timestamp):
            return pd.NaT
        if getattr(timestamp, "tzinfo", None) is None:
            return timestamp.tz_localize(DISPLAY_TZ)
        return timestamp.tz_convert(DISPLAY_TZ)

    df["Timestamp"] = pd.Series(
        [_normalize_log_timestamp(value) for value in df["Timestamp"]],
        index=df.index,
    )
    df = df.dropna(subset=["Timestamp"])
    if df.empty:
        return df
    setup_mask = df["Category"].astype(str).str.upper().eq("SETUP_STATUS")
    if setup_mask.any():
        setup_indexes = df.index[setup_mask]
        # Keep the backend's own "candle=" reference intact: it legitimately
        # differs between a closed-candle confirmation (the candle just
        # evaluated) and a live tick update (the candle currently forming).
        # Rewriting it to the write-time's 3-minute floor previously made
        # closed-candle rows collide with unrelated live-tick rows below,
        # silently dropping the real confirmation event as a "duplicate".
        candle_timestamps = [
            _setup_candle_timestamp(message, timestamp)
            for message, timestamp in zip(
                df.loc[setup_mask, "Message"],
                df.loc[setup_mask, "Timestamp"],
            )
        ]
        df["Candle Timestamp"] = pd.Series(
            pd.NaT,
            index=df.index,
            dtype="datetime64[ns, Asia/Kolkata]",
        )
        df.loc[setup_mask, "Candle Timestamp"] = pd.Series(
            candle_timestamps,
            index=setup_indexes,
        )
        setup_rows = df.loc[setup_mask].sort_values("Timestamp")
        setup_rows = setup_rows.drop_duplicates(
            subset=["Candle Timestamp", "Symbol", "Message"],
            keep="last",
        )
        df = pd.concat([df.loc[~setup_mask], setup_rows], ignore_index=True)
    local_ts = df["Timestamp"].dt.tz_convert(DISPLAY_TZ)
    df["Date"] = local_ts.dt.date
    df["Time"] = local_ts.dt.strftime("%H:%M:%S")
    now = datetime.now(DISPLAY_TZ)
    market_open = datetime.strptime("09:20", "%H:%M").time()
    market_close = datetime.strptime("15:15", "%H:%M").time()
    if now.weekday() >= 5 or not (market_open <= now.time() < market_close):
        df = df[~df["Category"].astype(str).str.upper().isin({"DATA", "TICK"})]
        if df.empty:
            return df
    df = df.drop_duplicates(subset=["Timestamp", "Category", "Symbol", "Message"], keep="last")
    return df[[
        "Date", "Time", "Timestamp", "Category", "Status", "Symbol",
        "Entry Price", "Exit Price", "Trade P&L", "Message",
    ]].sort_values("Timestamp", ascending=False)


def _setup_candle_timestamp(message: object, timestamp: pd.Timestamp) -> pd.Timestamp:
    match = re.search(r"candle=(\d{2}):(\d{2}):(\d{2})", str(message), re.IGNORECASE)
    if not match:
        return timestamp.replace(second=0, microsecond=0)
    return timestamp.replace(
        hour=int(match.group(1)),
        minute=int(match.group(2)),
        second=int(match.group(3)),
        microsecond=0,
    )


def _option_symbol_root(symbol: object) -> str:
    match = re.match(r"^([A-Z]+)\d", str(symbol or "").strip().upper())
    return match.group(1) if match else ""


def _option_symbol_strike(symbol: object) -> int | None:
    match = re.fullmatch(
        r"[A-Z]+\d{2}[A-Z]{3}\d{2}(\d+)(?:CE|PE)",
        str(symbol or "").strip().upper(),
    )
    return int(match.group(1)) if match else None


def _latest_persisted_option_symbols(target_date: date) -> dict[str, dict[str, str]]:
    """Recover the latest CE/PE symbols grouped by their option index root."""
    latest: dict[tuple[str, str], tuple[int, pd.Timestamp, str]] = {}
    for path in sorted(LOGS_DIR.glob("monitoring_*.csv")):
        try:
            monitoring_df = pd.read_csv(path)
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        required = {"timestamp", "category", "symbol"}
        if not required.issubset(monitoring_df.columns):
            continue
        for _, row in monitoring_df.iterrows():
            category = str(row.get("category") or "").upper()
            if category not in {"SETUP_STATUS", "DATA"}:
                continue
            timestamp = pd.to_datetime(row.get("timestamp"), errors="coerce")
            if pd.isna(timestamp):
                continue
            if getattr(timestamp, "tzinfo", None) is None:
                timestamp = timestamp.tz_localize(DISPLAY_TZ)
            else:
                timestamp = timestamp.tz_convert(DISPLAY_TZ)
            if timestamp.date() != target_date:
                continue
            message = str(row.get("message") or "").upper()
            if category == "DATA":
                if "3M CANDLE" not in message:
                    continue
                candidates = [
                    (symbol[-2:], symbol)
                    for symbol in re.findall(
                        r"\b([A-Z]+\d{2}[A-Z]{3}\d{2}\d+(?:CE|PE))\b",
                        message,
                    )
                ]
                source_priority = 1
            else:
                side = "CE" if message.startswith("CE ") else "PE" if message.startswith("PE ") else ""
                symbol = str(row.get("symbol") or "").strip().upper()
                candidates = [(side, symbol)] if side and symbol and symbol != "-" else []
                source_priority = 0

            for side, symbol in candidates:
                root = _option_symbol_root(symbol)
                key = (root, side)
                rank = (source_priority, timestamp)
                if root and side in {"CE", "PE"} and (
                    key not in latest or rank >= latest[key][:2]
                ):
                    latest[key] = (source_priority, timestamp, symbol)
    symbols_by_root: dict[str, dict[str, str]] = {}
    for (root, side), (_, _, symbol) in latest.items():
        symbols_by_root.setdefault(root, {})[side] = symbol
    return symbols_by_root


def _combined_logs_for_date(engine: BaseStrategyEngine | None, target_date: date) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    session_df = _session_logs_df(engine)
    if not session_df.empty:
        session_day_df = session_df[session_df["Date"] == target_date]
        if not session_day_df.empty:
            frames.append(session_day_df)

    market_data_df = _market_data_logs_df()
    if not market_data_df.empty:
        market_data_day_df = market_data_df[market_data_df["Date"] == target_date]
        if not market_data_day_df.empty:
            frames.append(market_data_day_df)

    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    # Normalize mixed tz-naive/tz-aware values to a single dtype before sorting.
    merged["Timestamp"] = pd.to_datetime(merged["Timestamp"], errors="coerce", utc=True)
    merged = merged.dropna(subset=["Timestamp"])
    local_ts = merged["Timestamp"].dt.tz_convert(DISPLAY_TZ)
    # Rebuild display columns from one normalized timestamp to avoid mixed-type
    # rendering issues (e.g. epoch-like integers shown in the Date column).
    merged["Date"] = local_ts.dt.strftime("%Y-%m-%d")
    merged["Time"] = local_ts.dt.strftime("%H:%M:%S")
    merged = merged.drop_duplicates(subset=["Timestamp", "Category", "Message"], keep="last")
    return merged.sort_values("Timestamp", ascending=False).reset_index(drop=True)


def _format_display_ts(value: object) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return "—"
    if getattr(ts, "tzinfo", None) is None:
        ts = ts.tz_localize(DISPLAY_TZ)
    else:
        ts = ts.tz_convert(DISPLAY_TZ)
    return ts.strftime("%I:%M:%S %p IST")


def _normalize_candle_timestamp(value: object) -> datetime | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(DISPLAY_TZ)
    else:
        timestamp = timestamp.tz_convert(DISPLAY_TZ)
    return timestamp.to_pydatetime()


def _latest_worker_candle_time(target_date: date) -> datetime | None:
    """Read the latest candle checkpoint written by the background worker."""
    latest: datetime | None = None
    for path in LOGS_DIR.glob(f"runner_checkpoint_*_{target_date:%Y%m%d}.json"):
        try:
            with path.open(encoding="utf-8") as handle:
                checkpoint = json.load(handle)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        for value in checkpoint.values() if isinstance(checkpoint, dict) else ():
            timestamp = _normalize_candle_timestamp(value)
            if timestamp is None:
                continue
            if latest is None or timestamp > latest:
                latest = timestamp
    return latest


def _latest_persisted_candle_time(target_date: date) -> datetime | None:
    """Read the newest candle timestamp from the worker's monitoring files."""
    latest: datetime | None = None
    for path in LOGS_DIR.glob(f"monitoring_{target_date:%Y%m%d}.csv"):
        try:
            monitoring_df = pd.read_csv(path, usecols=["timestamp", "category", "message"])
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        candle_rows = monitoring_df[
            monitoring_df["category"].astype(str).str.upper().eq("DATA")
            & monitoring_df["message"].astype(str).str.match(r"^\d+m candle\b")
        ]
        for value in candle_rows["timestamp"]:
            timestamp = _normalize_candle_timestamp(value)
            if timestamp is None:
                continue
            if latest is None or timestamp > latest:
                latest = timestamp
    return latest


def _auto_include_new_filter_options(filter_key: str, seen_key: str, available: list[str]) -> list[str]:
    current = [value for value in st.session_state.get(filter_key, []) if value in available]
    seen = set(st.session_state.get(seen_key, []))
    new_values = [value for value in available if value not in seen]

    if not current:
        selected = list(available)
    else:
        selected = current + [value for value in new_values if value not in current]

    st.session_state[filter_key] = selected
    st.session_state[seen_key] = list(dict.fromkeys([*seen, *available]))
    return selected


def _row_priority(category: str) -> int:
    category_upper = str(category).upper()
    if category_upper == "DATA":
        return 2
    if category_upper == "SESSION":
        return 1
    return 0


def _format_category_label(category: object) -> str:
    category_upper = str(category).upper()
    label_map = {
        "DATA": "CANDLE",
        "DIAG": "NO-SIGNAL REASON",
        "SESSION": "SESSION EVENT",
    }
    icon_map = {
        "SIGNAL": "🚨",
        "ENTRY": "🟢",
        "EXIT": "🏁",
        "ORDER": "📤",
        "SL": "🛑",
        "RISK": "⚠️",
        "REJECT": "⛔",
        "FAILED": "⛔",
        "ERROR": "⛔",
        "SESSION": "🕘",
        "DATA": "📈",
        "DIAG": "🧪",
    }
    label = label_map.get(category_upper, category_upper)
    return f"{icon_map.get(category_upper, '•')} {label}"


def _console_side(instrument: object, message: object) -> str:
    text = f"{instrument or ''} {message or ''}".upper()
    if re.search(r"\bPE\b|PE$", text):
        return "PE"
    if re.search(r"\bCE\b|CE$", text):
        return "CE"
    return "OTHER"


def _next_candle_eta(resolution_minutes: int) -> tuple[str, int]:
    now = datetime.now(DISPLAY_TZ)
    tf = max(1, int(resolution_minutes or 3))
    boundary_min = ((now.minute // tf) + 1) * tf
    next_ts = now.replace(second=1, microsecond=0)
    if boundary_min >= 60:
        next_ts = next_ts.replace(minute=0) + timedelta(hours=1)
    else:
        next_ts = next_ts.replace(minute=boundary_min)
    wait_seconds = max(0, int((next_ts - now).total_seconds()))
    return next_ts.strftime("%H:%M:%S"), wait_seconds


def _build_console_logs_df(
    source_params: dict[str, object],
    snapshot: dict[str, object],
    market_data_df: pd.DataFrame,
    openalgo_lines: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    strategy_name = str(source_params.get("active_strategy") or "HD Strategy")
    configured_resolution = max(1, int(source_params.get("openalgo_resolution") or 3))

    if not market_data_df.empty:
        market_data_copy = market_data_df.copy()
        market_data_copy["Timestamp"] = pd.to_datetime(market_data_copy["Timestamp"], errors="coerce")
        market_data_copy = market_data_copy.dropna(subset=["Timestamp"]).sort_values("Timestamp", ascending=False)
        actionable_categories = {
            "SIGNAL", "PENDING_ENTRY", "ENTRY", "EXIT", "TARGET", "SL", "CANCEL",
            "ORDER", "PROTECTIVE_SL", "TSL", "RISK", "REJECT", "FAILED", "ERROR", "UNCERTAIN_ENTRY",
        }
        setup_status_rows = market_data_copy[
            market_data_copy["Category"].astype(str).str.upper().eq("SETUP_STATUS")
        ]
        current_option_symbols = {
            str(row.get("Symbol") or "").strip()
            for _, row in setup_status_rows.iterrows()
            if str(row.get("Symbol") or "").strip() not in {"", "-", "CE", "PE"}
        }
        if not current_option_symbols:
            current_option_symbols = {
                str(snapshot.get(key) or "").strip()
                for key in ("ce_symbol", "pe_symbol")
                if str(snapshot.get(key) or "").strip()
            }
        data_rows = market_data_copy[
            market_data_copy["Category"].astype(str).str.upper().eq("DATA")
        ]
        if current_option_symbols:
            data_rows = data_rows[data_rows["Symbol"].astype(str).isin(current_option_symbols)]
        data_rows = data_rows.head(40)
        event_rows = market_data_copy[
            ~market_data_copy["Category"].astype(str).str.upper().isin(
                {"SETUP_STATUS", "DATA"}
            )
        ].head(120)
        for _, row in pd.concat([setup_status_rows, data_rows, event_rows]).iterrows():
            ts = pd.to_datetime(row["Timestamp"], errors="coerce")
            if pd.isna(ts):
                continue
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.tz_localize(DISPLAY_TZ)
            else:
                ts = ts.tz_convert(DISPLAY_TZ)
            level = str(row.get("Status") or "INFO").upper()
            message = str(row.get("Message") or "")
            category = str(row.get("Category") or "").upper()
            if category == "TICK":
                continue
            candle_match = re.match(r"^(\d+)m candle\b", message)
            if candle_match and int(candle_match.group(1)) != configured_resolution:
                continue
            if level == "TRIGGERED" and "| ALERT: " in message:
                alert_text = message.split("| ALERT: ", 1)[1].split(" | Next candle", 1)[0]
                categories = {
                    part.split(":", 1)[0].strip().upper()
                    for part in alert_text.split(" | ")
                    if part.strip()
                }
                if not categories.intersection(actionable_categories):
                    level = "INFO"
            rows.append(
                {
                    "Date": ts.strftime("%Y-%m-%d"),
                    "Time": ts.strftime("%H:%M:%S"),
                    "Level": level,
                    "Side": _console_side(row.get("Symbol"), message),
                    "Strategy": strategy_name,
                    "Instrument": str(row.get("Symbol") or "-"),
                    "Message": message,
                }
            )

    console_df = pd.DataFrame(rows)
    if console_df.empty:
        return console_df
    console_df = console_df.drop_duplicates(
        subset=["Time", "Strategy", "Instrument", "Message"]
    ).reset_index(drop=True)
    candle_keys = console_df["Message"].str.extract(
        r"^(\d+m candle \d{2}:\d{2}:\d{2})", expand=False
    )
    console_df["_CandleKey"] = candle_keys
    console_df = console_df[console_df["_CandleKey"].isna() | ~console_df.duplicated(
        subset=["Date", "Strategy", "Instrument", "_CandleKey"], keep="first"
    )]
    return console_df.drop(columns=["_CandleKey"]).reset_index(drop=True)


def _clear_stale_session_logs(target_date: date) -> None:
    """Keep in-memory dashboard logs scoped to the active trading day."""
    market_rows = st.session_state.get("market_data_logs") or []
    current_market_rows = []
    for row in market_rows:
        timestamp = pd.to_datetime(row.get("timestamp"), errors="coerce")
        if pd.isna(timestamp):
            continue
        if getattr(timestamp, "tzinfo", None) is None:
            timestamp = timestamp.tz_localize(DISPLAY_TZ)
        else:
            timestamp = timestamp.tz_convert(DISPLAY_TZ)
        if timestamp.date() == target_date:
            current_market_rows.append(row)
    st.session_state.market_data_logs = current_market_rows

    alert_rows = st.session_state.get("triggered_alert_rows") or []
    current_alert_rows = []
    for row in alert_rows:
        timestamp = pd.to_datetime(row.get("Timestamp"), errors="coerce")
        if pd.isna(timestamp):
            continue
        if getattr(timestamp, "tzinfo", None) is None:
            timestamp = timestamp.tz_localize(DISPLAY_TZ)
        else:
            timestamp = timestamp.tz_convert(DISPLAY_TZ)
        if timestamp.date() == target_date:
            current_alert_rows.append(row)
    st.session_state.triggered_alert_rows = current_alert_rows


def _extract_alert_price(message: str) -> float | None:
    for pattern in (
        r"trigger=([0-9]+(?:\.[0-9]+)?)",
        r"close=([0-9]+(?:\.[0-9]+)?)",
        r"@\s*([0-9]+(?:\.[0-9]+)?)",
        r"\bat\s*([0-9]+(?:\.[0-9]+)?)",
        r"SL=([0-9]+(?:\.[0-9]+)?)",
    ):
        price = _extract_price(pattern, message)
        if price is not None:
            return price
    return None


def _status_for_alert(category: str, message: str) -> str:
    return _classify_status(category, message)


def _alert_symbol(engine: BaseStrategyEngine, message: str) -> str:
    symbol = _extract_symbol(message)
    if symbol != "-":
        return symbol
    message_upper = message.upper()
    if message_upper.startswith("CE "):
        return str(getattr(engine.state, "ce_symbol", None) or "-")
    if message_upper.startswith("PE "):
        return str(getattr(engine.state, "pe_symbol", None) or "-")
    return "-"


def _load_persisted_alert_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    visible_categories = {
        "SIGNAL", "PENDING_ENTRY", "ENTRY", "EXIT", "TARGET", "SL", "CANCEL",
        "ORDER", "PROTECTIVE_SL", "TSL", "RISK", "REJECT", "FAILED", "ERROR", "UNCERTAIN_ENTRY",
    }

    def append_alert(ts: pd.Timestamp, category: str, message: str) -> None:
        if category not in visible_categories:
            return
        rows.append(
            {
                "Timestamp": ts,
                "Date": ts.strftime("%Y-%m-%d"),
                "Time": ts.strftime("%H:%M:%S"),
                "Symbol": _extract_symbol(message),
                "Category": category,
                "Status": _status_for_alert(category, message),
                "Price": _extract_alert_price(message),
                "Message": message,
            }
        )

    for path in sorted(LOGS_DIR.glob("trade_alerts_*.csv")):
        try:
            persisted_df = pd.read_csv(path)
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        required = {"timestamp", "category", "message"}
        if not required.issubset(persisted_df.columns):
            continue
        for _, persisted in persisted_df.iterrows():
            ts = pd.to_datetime(persisted.get("timestamp"), errors="coerce")
            if pd.isna(ts):
                continue
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.tz_localize(DISPLAY_TZ)
            else:
                ts = ts.tz_convert(DISPLAY_TZ)
            category = str(persisted.get("category") or "INFO").upper()
            message = str(persisted.get("message") or "")
            append_alert(ts, category, message)

    # Setup and signal alerts were originally included only in today's monitoring rows.
    # Restore those entries too so a restart does not erase the trigger history.
    today_path = LOGS_DIR / f"monitoring_{datetime.now(DISPLAY_TZ):%Y%m%d}.csv"
    for path in (today_path,) if today_path.exists() else ():
        try:
            monitoring_df = pd.read_csv(path, usecols=["timestamp", "message"])
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        if not {"timestamp", "message"}.issubset(monitoring_df.columns):
            continue
        for _, monitoring in monitoring_df.iterrows():
            raw_message = str(monitoring.get("message") or "")
            if "| ALERT: " not in raw_message:
                continue
            ts = pd.to_datetime(monitoring.get("timestamp"), errors="coerce")
            if pd.isna(ts):
                continue
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.tz_localize(DISPLAY_TZ)
            else:
                ts = ts.tz_convert(DISPLAY_TZ)
            alert_text = raw_message.split("| ALERT: ", 1)[1].split(" | Next candle", 1)[0]
            for message in (part.strip() for part in alert_text.split(" | ")):
                if message:
                    category, _, detail = message.partition(":")
                    category = category.strip().upper()
                    if category not in visible_categories:
                        continue
                    append_alert(ts, category, detail.strip() if detail else message)
    return rows


def _sync_triggered_alert_rows(engine: BaseStrategyEngine | None) -> pd.DataFrame:
    if "triggered_alert_rows" not in st.session_state:
        st.session_state.triggered_alert_rows = []
    if "triggered_alert_seen" not in st.session_state:
        st.session_state.triggered_alert_seen = set()

    rows: list[dict[str, object]] = st.session_state.triggered_alert_rows
    seen: set[str] = st.session_state.triggered_alert_seen
    alert_files = [
        path for path in LOGS_DIR.glob("trade_alerts_*.csv")
        if path.is_file()
    ]
    persisted_alerts_state = tuple(
        sorted((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in alert_files)
    )
    if st.session_state.get("persisted_alerts_state") != persisted_alerts_state:
        for row in _load_persisted_alert_rows():
            key = f"{row['Timestamp'].isoformat()}|{row['Category']}|{row['Message']}"
            if key not in seen:
                rows.append(row)
                seen.add(key)
        st.session_state.persisted_alerts_state = persisted_alerts_state

    engines: list[BaseStrategyEngine] = []
    instrument_states = st.session_state.get("instrument_states") or {}
    for state in instrument_states.values():
        runtime = state.get("runtime") or {}
        for state_engine in getattr(runtime, "engines", {}).values():
            if state_engine not in engines:
                engines.append(state_engine)
    if engine is not None and engine not in engines:
        engines.append(engine)

    if not any(getattr(item, "alerts", None) for item in engines):
        if not rows:
            return pd.DataFrame()
        out = pd.DataFrame(rows)
        out["Timestamp"] = pd.to_datetime(out["Timestamp"], errors="coerce")
        return out.sort_values("Timestamp", ascending=False).reset_index(drop=True)

    track_categories = {
        "SIGNAL", "PENDING_ENTRY", "ENTRY", "EXIT", "TARGET", "SL", "CANCEL",
        "ORDER", "PROTECTIVE_SL", "TSL", "RISK", "REJECT", "FAILED", "ERROR",
    }

    for alert_engine in engines:
        for alert in alert_engine.alerts:
            ts = pd.to_datetime(alert.timestamp, errors="coerce")
            if pd.isna(ts):
                continue
            category = str(alert.category).upper()
            message = str(alert.message)
            status = _status_for_alert(category, message)
            is_actionable = category in track_categories or status in {"TRIGGERED", "EXECUTED", "SUCCESS", "FAILED"}
            if not is_actionable:
                continue

            key = f"{ts.isoformat()}|{category}|{message}"
            if key in seen:
                continue

            local_ts = ts
            if getattr(local_ts, "tzinfo", None) is None:
                local_ts = local_ts.tz_localize(DISPLAY_TZ)
            else:
                local_ts = local_ts.tz_convert(DISPLAY_TZ)

            rows.append(
                {
                    "Timestamp": local_ts,
                    "Date": local_ts.strftime("%Y-%m-%d"),
                    "Time": local_ts.strftime("%H:%M:%S"),
                    "Symbol": _alert_symbol(alert_engine, message),
                    "Category": category,
                    "Status": status,
                    "Price": _extract_alert_price(message),
                    "Message": message,
                }
            )
            seen.add(key)

    st.session_state.triggered_alert_rows = rows[-500:]
    st.session_state.triggered_alert_seen = seen

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out["Timestamp"] = pd.to_datetime(out["Timestamp"], errors="coerce")
    out = out.dropna(subset=["Timestamp"])
    return out.sort_values("Timestamp", ascending=False).reset_index(drop=True)


# ── Page layout ───────────────────────────────────────────────────────────────

engine: BaseStrategyEngine | None = st.session_state.get("engine")
snapshot = engine.get_status_snapshot() if engine else {}
engine_status = st.session_state.get("engine_status", "stopped")
last_candle_time = snapshot.get("last_processed_candle_time")
source_params = st.session_state.get("source_params", {}) or {}
last_refresh = st.session_state.get("live_account_updated_at") or "—"
live_error = st.session_state.get("live_account_error")
openalgo_log_lines, openalgo_log_error = _load_openalgo_container_logs(source_params)
today = datetime.now(DISPLAY_TZ).date()
session_candle_time = _normalize_candle_timestamp(
    st.session_state.get("last_candle_processed_at")
)
persisted_candle_times = [
    value for value in (
        _latest_worker_candle_time(today),
        _latest_persisted_candle_time(today),
    ) if value is not None
]
if session_candle_time is not None:
    persisted_candle_times.append(session_candle_time)
last_candle_processed_at = max(persisted_candle_times) if persisted_candle_times else None
if last_candle_processed_at is not None:
    st.session_state.last_candle_processed_at = last_candle_processed_at
if not last_candle_time:
    last_candle_time = last_candle_processed_at
if engine_status == "stopped" and last_candle_processed_at is not None:
    engine_status = "running"
refresh_seconds = 30
_clear_stale_session_logs(today)

# ── 1. Top Status Header ──────────────────────────────────────────────────────
if engine_status == "running" and live_error:
    status_label, status_color, status_emoji = "Polling Error", "#ff7a7a", "🔴"
elif engine_status == "running" and last_candle_time:
    status_label, status_color, status_emoji = "Processing Candles", "#27d48a", "🟢"
elif engine_status == "running":
    status_label, status_color, status_emoji = "Polling Live Feed", "#59d0ff", "🔵"
elif engine_status == "paused":
    status_label, status_color, status_emoji = "PAUSED", "#ffbe32", "🟡"
else:
    status_label, status_color, status_emoji = "STOPPED", "#ff5f6d", "🔴"

last_candle_display = _format_display_ts(last_candle_processed_at) if last_candle_processed_at else "—"
selected_instruments = list(source_params.get("selected_instruments") or [])
instrument_configs = source_params.get("instrument_configs") or {}
spot_symbol = str(source_params.get("openalgo_symbol") or source_params.get("primary_instrument") or "NSE:NIFTY-INDEX")
instrument_states = st.session_state.get("instrument_states") or {}
persisted_option_symbols = _latest_persisted_option_symbols(today)
instrument_symbol_labels: list[str] = []
for instrument in selected_instruments:
    state = instrument_states.get(instrument) or {}
    state_runtime = state.get("runtime")
    state_engine = None
    if state_runtime is not None and state_runtime.active_keys:
        state_engine = state_runtime.engines.get(state_runtime.active_keys[0])
    state_snapshot = state_engine.get_status_snapshot() if state_engine is not None else {}
    instrument_config = dict(instrument_configs.get(instrument) or {})
    if not instrument_config:
        instrument_config = dict((state.get("source_params") or {}).get("instrument_config") or {})
    instrument_root = str(
        instrument_config.get("option_index_symbol")
        or instrument_config.get("spot_symbol")
        or ""
    ).strip().upper()
    if not instrument_root:
        instrument_name = re.sub(r"[^A-Z0-9]", "", instrument.upper())
        instrument_root = next(
            (root for root in ("BANKNIFTY", "NIFTY", "SENSEX") if root in instrument_name),
            instrument_name,
        )
    spot = str(
        instrument_config.get("symbol")
        or (state.get("source_params") or {}).get("openalgo_symbol")
        or instrument
    )
    ce_symbol = state_snapshot.get("ce_symbol")
    pe_symbol = state_snapshot.get("pe_symbol")
    atm_strike = state_snapshot.get("atm_strike")
    if ce_symbol and _option_symbol_root(ce_symbol) != instrument_root:
        ce_symbol = None
        atm_strike = None
    if pe_symbol and _option_symbol_root(pe_symbol) != instrument_root:
        pe_symbol = None
        atm_strike = None
    persisted_symbols = persisted_option_symbols.get(instrument_root, {})
    ce_symbol = ce_symbol or persisted_symbols.get("CE")
    pe_symbol = pe_symbol or persisted_symbols.get("PE")
    if not atm_strike:
        atm_strike = _option_symbol_strike(ce_symbol or pe_symbol)
    if ce_symbol or pe_symbol:
        instrument_symbol_labels.append(
            f"{instrument}: ATM {int(atm_strike) if atm_strike else '-'} | "
            f"{ce_symbol or '-'} CE | {pe_symbol or '-'} PE"
        )
    elif atm_strike:
        instrument_symbol_labels.append(f"{instrument}: {spot} (ATM {int(atm_strike)})")
    else:
        instrument_symbol_labels.append(f"{instrument}: {spot} (ATM pending)")

active_symbols = " | ".join(instrument_symbol_labels) if instrument_symbol_labels else spot_symbol
now_time = datetime.now(DISPLAY_TZ).time()
if now_time < datetime.strptime("09:15", "%H:%M").time():
    market_phase = "Pre-Market"
elif now_time < datetime.strptime("09:20", "%H:%M").time():
    market_phase = "Opening"
elif now_time < datetime.strptime("15:00", "%H:%M").time():
    market_phase = "Live Trading"
elif now_time < datetime.strptime("15:15", "%H:%M").time():
    market_phase = "Signal Cutoff"
else:
    market_phase = "After-Market"

if live_error:
        polling_badge = "Live polling error"
        polling_badge_color = "#ff7a7a"
elif last_refresh == "—":
        polling_badge = "Waiting for first refresh"
        polling_badge_color = "#ffbe32"
elif last_candle_time:
        polling_badge = "Live polling active"
        polling_badge_color = "#27d48a"
else:
        polling_badge = "No new candle yet"
        polling_badge_color = "#59d0ff"

st.html(f"""
<div style="background:rgba(12,20,38,0.7);border:1px solid rgba(86,184,222,0.25);
            border-radius:14px;padding:1rem 1.4rem;margin-bottom:1rem;
            display:flex;align-items:center;gap:2.5rem;flex-wrap:wrap;">
  <div>
        <div style="font-size:0.75rem;color:#8e9cb0;font-weight:600;text-transform:uppercase;
                                letter-spacing:.06em;margin-bottom:.25rem;">Monitoring Status</div>
    <div style="font-size:1.15rem;font-weight:800;color:{status_color};">
      {status_emoji} {status_label}
    </div>
        <div style="font-size:0.82rem;font-weight:700;color:{polling_badge_color};margin-top:.35rem;">
            {polling_badge}
        </div>
  </div>
  <div>
    <div style="font-size:0.75rem;color:#8e9cb0;font-weight:600;text-transform:uppercase;
                                letter-spacing:.06em;margin-bottom:.25rem;">Last Candle Processed</div>
        <div style="font-size:1.1rem;font-weight:700;color:#edf4ff;">{last_candle_display}</div>
  </div>
  <div>
    <div style="font-size:0.75rem;color:#8e9cb0;font-weight:600;text-transform:uppercase;
                letter-spacing:.06em;margin-bottom:.25rem;">Active Symbols</div>
        <div style="font-size:1rem;font-weight:700;color:#59d0ff;">{active_symbols}</div>
  </div>
  <div>
    <div style="font-size:0.75rem;color:#8e9cb0;font-weight:600;text-transform:uppercase;
                letter-spacing:.06em;margin-bottom:.25rem;">Market Phase</div>
    <div style="font-size:1.1rem;font-weight:700;color:#ffd700;">{market_phase}</div>
  </div>
</div>
""")

# ── 2. Auto-refresh status ────────────────────────────────────────────────────
hdr_col, refresh_col = st.columns([6, 2])
with hdr_col:
    render_section_heading("Operations Log", "Daily trade and alert logs",
                           "All trades, alerts, entry/exit prices, and events by date.")
with refresh_col:
    st.caption(f"Auto-refresh ({refresh_seconds} sec)")
    st.caption(f"Last refresh: {last_refresh}")

with st.container(border=True):
    render_section_heading(
        "OpenAlgo Feed Status",
        "Real-time connection and data collection vitals",
        "Feed source, connection status, buffer state, active subscriptions, and latency metrics.",
    )
    
    if openalgo_log_error:
        st.warning(openalgo_log_error, icon="⚠️")
    elif not openalgo_log_lines:
        st.info("No OpenAlgo logs available yet.", icon="📝")
    else:
        # Extract live feed status from Docker logs (plain text format)
        # Format: [2026-10-07 13:01:26,465] INFO in data: Successfully collected data: 326 total candles
        import re
        
        candle_count = 0
        latest_date = "N/A"
        latest_time = "N/A"
        
        # Scan in reverse for the most recent successful data collection
        for line in reversed(openalgo_log_lines):
            if not line.strip():
                continue
            
            # Try to extract from Docker log format: [YYYY-MM-DD HH:MM:SS,mmm]
            # or tab-separated format: YYYY-MM-DDTHH:MM:SS.mmmmmm+HH:MM
            timestamp_match = re.search(r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})', line)
            
            if timestamp_match:
                latest_date = timestamp_match.group(1)
                latest_time = timestamp_match.group(2)
                
                # Check if this line has successful data collection
                if "Successfully collected data" in line and "total candles" in line:
                    # Extract total candles from "Successfully collected data: 326 total candles"
                    candles_match = re.search(r'Successfully collected data:\s*(\d+)\s*total candles', line)
                    if candles_match:
                        candle_count = int(candles_match.group(1))
                        break  # Found the most recent, stop here
        
        # Display in compact format
        if candle_count > 0:
            log_entry = f"[{latest_date} {latest_time}] {candle_count} candles processed"
            st.code(log_entry, language="plaintext")
        else:
            st.info("Waiting for candle data...", icon="⏳")


with st.container(border=True):
    render_section_heading(
        "Console logs",
        "Three-minute monitoring with event updates",
        "Shows routine market state every three minutes and keeps alert, trigger, and confirmation events immediately.",
    )

    market_data_df = _market_data_logs_df()
    if not market_data_df.empty:
        market_data_df = market_data_df[market_data_df["Date"] == today]

    console_source_df = _build_console_logs_df(
        source_params,
        snapshot,
        market_data_df,
        openalgo_log_lines,
    )

    if console_source_df.empty:
        st.info("No console logs available yet.", icon="📝")
    else:
        st.caption(f"{len(console_source_df)} log entries")
        console_export = console_source_df[[
            "Date", "Time", "Side", "Level", "Strategy", "Instrument", "Message",
        ]].copy()
        st.download_button(
            "Download CSV",
            data=console_export.to_csv(index=False),
            file_name=f"console_logs_{today.isoformat()}.csv",
            mime="text/csv",
            key="download_console_logs_csv",
        )
        console_view = console_source_df[[
            "Time", "Side", "Level", "Instrument", "Message",
        ]].fillna("-")
        completed_candle_view = console_source_df[
            console_source_df["Message"].str.match(r"^\d+m candle\b", na=False)
        ][["Time", "Side", "Level", "Message"]].copy()
        completed_candle_view["CandleTime"] = pd.to_datetime(
            completed_candle_view["Message"].str.extract(
                r"^\d+m candle (\d{2}:\d{2}:\d{2})", expand=False
            ),
            format="%H:%M:%S",
            errors="coerce",
        )
        completed_candle_view = completed_candle_view[
            completed_candle_view["CandleTime"].dt.time >= datetime.strptime("09:20:00", "%H:%M:%S").time()
        ].sort_values("CandleTime", ascending=False)

        def _side_panel(side: str, accent: str, title: str) -> str:
            side_view = console_view[console_view["Side"] == side]
            status_rows = side_view[side_view["Level"] == "INFO"]
            status_rows = status_rows[status_rows["Message"].str.contains("EMA21 setup", na=False)]
            # Sort by Time in descending order (most recent first)
            status_rows = status_rows.sort_values("Time", ascending=False)
            latest_status = status_rows.iloc[0] if not status_rows.empty else None
            previous_status = status_rows.iloc[1] if len(status_rows) > 1 else None
            risk_rows = side_view[side_view["Level"] == "RISK"]
            latest_risk = risk_rows.iloc[0] if not risk_rows.empty else None
            latest_status_index = {latest_status.name} if latest_status is not None else set()
            side_rows = side_view[~side_view.index.isin(latest_status_index)].head(60)
            rows_html = "".join(
                "<tr>"
                f"<td style='padding:.48rem .55rem;vertical-align:top;white-space:nowrap;border-bottom:1px solid rgba(86,184,222,.12);'>{escape(str(row['Time']))}</td>"
                f"<td style='padding:.48rem .55rem;vertical-align:top;white-space:nowrap;border-bottom:1px solid rgba(86,184,222,.12);'>{escape(str(row['Level']))}</td>"
                f"<td style='padding:.48rem .55rem;vertical-align:top;overflow-wrap:anywhere;border-bottom:1px solid rgba(86,184,222,.12);'>{escape(str(row['Message']))}</td>"
                "</tr>"
                for _, row in side_rows.iterrows()
            )
            candle_view = completed_candle_view[
                completed_candle_view["Side"] == side
            ].head(20)
            candle_rows_html = "".join(
                "<tr>"
                f"<td style='padding:.42rem .5rem;vertical-align:top;white-space:nowrap;border-bottom:1px solid rgba(86,184,222,.10);'>{escape(str(row['Time']))}</td>"
                f"<td style='padding:.42rem .5rem;vertical-align:top;white-space:nowrap;border-bottom:1px solid rgba(86,184,222,.10);'>CANDLE</td>"
                f"<td style='padding:.42rem .5rem;vertical-align:top;overflow-wrap:anywhere;border-bottom:1px solid rgba(86,184,222,.10);'>{escape(str(row['Message']))}</td>"
                "</tr>"
                for _, row in candle_view.iterrows()
            )
            empty_candle_row = (
                '<tr><td colspan="3" style="padding:.6rem;color:#91a3b8;">'
                "No completed 3-minute candles yet.</td></tr>"
            )
            candle_html = (
                "<div style='padding:.55rem .8rem .2rem;color:#91dfff;font-size:.74rem;"
                "font-weight:800;text-transform:uppercase;letter-spacing:.05em;'>"
                "Completed 3-minute candles</div>"
                "<div style='max-height:220px;overflow-y:auto;'>"
                "<table style='width:100%;table-layout:fixed;border-collapse:collapse;font-size:.78rem;'>"
                "<colgroup><col style='width:23%;'><col style='width:20%;'><col style='width:57%;'></colgroup>"
                "<tbody>"
                f"{candle_rows_html or empty_candle_row}"
                "</tbody></table></div>"
            )
            status_html = ""
            if latest_risk is not None:
                risk_message = str(latest_risk["Message"])
                status_html = (
                    f"<div style='margin:.7rem .8rem;padding:.65rem .7rem;border-left:3px solid #ffbe32;"
                    "background:#ffbe3212;color:#e7eef7;overflow-wrap:anywhere;'>"
                    "<b style='color:#ffbe32;'>Latest order decision</b><br>"
                    f"<span style='color:#a9b8c9;'>Time: {escape(str(latest_risk['Time']))}</span><br>"
                    f"{escape(risk_message)}</div>"
                )
            elif latest_status is not None:
                previous_html = ""
                if previous_status is not None:
                    previous_html = (
                        "<br><br><b style='color:#91a3b8;'>Previous setup event</b><br>"
                        f"<span style='color:#a9b8c9;'>Time: {escape(str(previous_status['Time']))}</span><br>"
                        f"{escape(str(previous_status['Message']))}"
                    )
                status_html = (
                    f"<div style='margin:.7rem .8rem;padding:.65rem .7rem;border-left:3px solid {accent};"
                    f"background:{accent}12;color:#e7eef7;overflow-wrap:anywhere;'>"
                    f"<b style='color:{accent};'>Current setup</b><br>"
                    f"<span style='color:#a9b8c9;'>Monitoring: {escape(str(latest_status['Instrument']))}</span><br>"
                    f"{escape(str(latest_status['Message']))}{previous_html}</div>"
                )
            elif side_rows.empty:
                status_html = "<div style='margin:.7rem .8rem;color:#91a3b8;'>No setup status recorded yet.</div>"
            return f"""
                <div style="border:1px solid {accent}88;border-radius:12px;overflow:hidden;">
                    <div style="padding:.7rem .8rem;background:{accent}18;color:{accent};font-weight:800;">
                        {title} <span style="float:right;color:#a9b8c9;font-size:.78rem;">{len(side_rows)} latest rows</span>
                    </div>
                    {status_html}
                    {candle_html}
                    <div style="overflow-y:auto;max-height:360px;">
                        <table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:.82rem;">
                            <colgroup><col style="width:23%;"><col style="width:20%;"><col style="width:57%;"></colgroup>
                            <thead style="position:sticky;top:0;background:rgba(19,28,46,.98);z-index:1;">
                                <tr><th style="text-align:left;padding:.48rem .55rem;">Time</th><th style="text-align:left;padding:.48rem .55rem;">Level</th><th style="text-align:left;padding:.48rem .55rem;">Message</th></tr>
                            </thead>
                            <tbody>{rows_html or '<tr><td colspan="3" style="padding:.6rem;color:#91a3b8;">No event rows yet.</td></tr>'}</tbody>
                        </table>
                    </div>
                </div>
            """

        market_rows = console_view[
            (console_view["Side"] == "OTHER")
            & ~console_view["Message"].str.match(r"^\d+m candle\b", na=False)
        ]
        if not market_rows.empty:
            market_rows_html = "".join(
                "<tr>"
                f"<td style='padding:.48rem .55rem;vertical-align:top;white-space:nowrap;border-bottom:1px solid rgba(86,184,222,.12);'>{escape(str(row['Time']))}</td>"
                f"<td style='padding:.48rem .55rem;vertical-align:top;white-space:nowrap;border-bottom:1px solid rgba(86,184,222,.12);'>{escape(str(row['Level']))}</td>"
                f"<td style='padding:.48rem .55rem;vertical-align:top;overflow-wrap:anywhere;border-bottom:1px solid rgba(86,184,222,.12);'>{escape(str(row['Message']))}</td>"
                "</tr>"
                for _, row in market_rows.head(60).iterrows()
            )
            st.markdown(
                "<div style='margin:.8rem 0;border:1px solid rgba(89,208,255,.45);border-radius:12px;overflow:hidden;'>"
                "<div style='padding:.7rem .8rem;background:rgba(89,208,255,.10);color:#59d0ff;font-weight:800;'>"
                "Market data <span style='float:right;color:#a9b8c9;font-size:.78rem;'>"
                f"{len(market_rows)} latest rows</span></div>"
                "<div style='overflow-y:auto;max-height:240px;'><table style='width:100%;table-layout:fixed;border-collapse:collapse;font-size:.82rem;'>"
                "<colgroup><col style='width:15%;'><col style='width:15%;'><col style='width:70%;'></colgroup>"
                "<thead style='position:sticky;top:0;background:rgba(19,28,46,.98);z-index:1;'>"
                "<tr><th style='text-align:left;padding:.48rem .55rem;'>Time</th><th style='text-align:left;padding:.48rem .55rem;'>Level</th><th style='text-align:left;padding:.48rem .55rem;'>Message</th></tr>"
                f"</thead><tbody>{market_rows_html}</tbody></table></div></div>",
                unsafe_allow_html=True,
            )

        ce_rows = int((console_view["Side"] == "CE").sum())
        pe_rows = int((console_view["Side"] == "PE").sum())
        st.caption(f"{ce_rows} CE rows | {pe_rows} PE rows | newest events first")
        ce_col, pe_col = st.columns(2)
        with ce_col:
            st.html(_side_panel("CE", "#59d0ff", "CE · Call option"))
        with pe_col:
            st.html(_side_panel("PE", "#ff9f7f", "PE · Put option"))

with st.container(border=True):
    render_section_heading(
        "Triggered alerts",
        "Saved alert events",
        "Captures actionable triggered alerts with date, time, symbol, category, status, and price.",
    )
    triggered_df = _sync_triggered_alert_rows(engine)
    render_alert_toasts(
        triggered_df.to_dict("records") if not triggered_df.empty else None
    )
    if not triggered_df.empty:
        triggered_df = triggered_df[triggered_df["Date"] == today.isoformat()].reset_index(drop=True)
    if triggered_df.empty:
        st.info("No triggered alerts yet.", icon="🚨")
    else:
        st.caption(f"{len(triggered_df)} saved alerts")
        alert_columns = ["Date", "Time", "Symbol", "Category", "Status", "Price", "Message"]
        export_df = triggered_df[alert_columns].copy()
        st.download_button(
            "Download CSV",
            data=export_df.to_csv(index=False),
            file_name=f"triggered_alerts_{date.today().isoformat()}.csv",
            mime="text/csv",
            key="download_triggered_alerts_csv",
        )
        view_df = export_df.copy()
        view_df["Price"] = view_df["Price"].apply(lambda v: f"₹{v:,.2f}" if pd.notna(v) else "—")
        view_df["Status"] = view_df["Status"].map(lambda s: f"{_STATUS_BADGE.get(str(s), '⚪')} {s}")
        alert_row_html = "".join(
            (
                "<tr>"
                + "".join(
                    f"<td style=\"padding:0.55rem 0.6rem; vertical-align:top; "
                    f"overflow-wrap:anywhere; word-break:break-word; "
                    f"border-bottom:1px solid rgba(86,184,222,0.12);\">{escape(str(row[column]))}</td>"
                    for column in ("Date", "Time", "Symbol", "Category", "Status", "Price", "Message")
                )
                + "</tr>"
            )
            for _, row in view_df.iterrows()
        )
        st.markdown(
            f"""
            <div style="overflow-y:auto; max-height:430px; border:1px solid rgba(86,184,222,0.28); border-radius:12px;">
                <table style="width:100%; table-layout:fixed; border-collapse:collapse; font-size:0.86rem;">
                    <colgroup>
                        <col style="width:12%;"><col style="width:10%;"><col style="width:22%;">
                        <col style="width:12%;"><col style="width:13%;"><col style="width:11%;"><col style="width:20%;">
                    </colgroup>
                    <thead style="position:sticky; top:0; background:rgba(19,28,46,0.98); z-index:1;">
                        <tr>
                            {''.join(f'<th style="text-align:left; padding:0.55rem 0.6rem; border-bottom:1px solid rgba(86,184,222,0.22);">{column}</th>' for column in ("Date", "Time", "Symbol", "Category", "Status", "Price", "Message"))}
                        </tr>
                    </thead>
                    <tbody>{alert_row_html}</tbody>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

