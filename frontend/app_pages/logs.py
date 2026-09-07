"""Logs page — live strategy status, structured log table, and metrics."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from html import escape
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from _shared import (
    DISPLAY_TZ,
    LOGS_DIR,
    inject_theme,
    refresh_live_account_metrics,
    render_section_heading,
    render_sidebar,
)
from core.engine import BaseStrategyEngine

inject_theme()
source_params = render_sidebar()

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


def _load_openalgo_container_logs(source_params: dict[str, object]) -> tuple[list[str], str | None]:
    try:
        import docker  # type: ignore
    except Exception as exc:
        return [], f"Docker SDK unavailable: {exc}"

    try:
        client = docker.from_env()
        configured_name = os.getenv("OPENALGO_LOG_CONTAINER", "").strip()
        base_url = str(source_params.get("openalgo_base_url") or os.getenv("OPENALGO_BASE_URL", "http://host.docker.internal:5002"))
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

        raw = container.logs(tail=120).decode("utf-8", errors="replace")
        lines = [line for line in raw.splitlines() if line.strip()]
        return lines[-60:], None
    except Exception as exc:
        return [], f"Unable to load OpenAlgo container logs: {exc}"


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
    for path in sorted(LOGS_DIR.glob("monitoring_*.csv")):
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
    # Session rows may be timezone-aware while older CSV rows can be naive.
    # Parse everything as UTC first so concatenated history has one dtype.
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["Timestamp"])
    if df.empty:
        return df
    local_ts = df["Timestamp"].dt.tz_convert(DISPLAY_TZ)
    df["Date"] = local_ts.dt.date
    df["Time"] = local_ts.dt.strftime("%H:%M:%S")
    df = df.drop_duplicates(subset=["Timestamp", "Category", "Symbol", "Message"], keep="last")
    return df[[
        "Date", "Time", "Timestamp", "Category", "Status", "Symbol",
        "Entry Price", "Exit Price", "Trade P&L", "Message",
    ]].sort_values("Timestamp", ascending=False)


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

    if not market_data_df.empty:
        market_data_copy = market_data_df.copy()
        market_data_copy["Timestamp"] = pd.to_datetime(market_data_copy["Timestamp"], errors="coerce")
        market_data_copy = market_data_copy.dropna(subset=["Timestamp"]).sort_values("Timestamp", ascending=False)
        for _, row in market_data_copy.head(120).iterrows():
            ts = pd.to_datetime(row["Timestamp"], errors="coerce")
            if pd.isna(ts):
                continue
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.tz_localize(DISPLAY_TZ)
            else:
                ts = ts.tz_convert(DISPLAY_TZ)
            rows.append(
                {
                    "Time": ts.strftime("%H:%M:%S"),
                    "Level": str(row.get("Status") or "INFO").upper(),
                    "Strategy": strategy_name,
                    "Instrument": str(row.get("Symbol") or "-"),
                    "Message": str(row.get("Message") or ""),
                }
            )

    console_df = pd.DataFrame(rows)
    if console_df.empty:
        return console_df
    return console_df.drop_duplicates(subset=["Time", "Strategy", "Instrument", "Message"]).reset_index(drop=True)


def _extract_alert_price(message: str) -> float | None:
    for pattern in (
        r"trigger=([0-9]+(?:\.[0-9]+)?)",
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


def _sync_triggered_alert_rows(engine: BaseStrategyEngine | None) -> pd.DataFrame:
    if "triggered_alert_rows" not in st.session_state:
        st.session_state.triggered_alert_rows = []
    if "triggered_alert_seen" not in st.session_state:
        st.session_state.triggered_alert_seen = set()

    rows: list[dict[str, object]] = st.session_state.triggered_alert_rows
    seen: set[str] = st.session_state.triggered_alert_seen

    if engine is None or not getattr(engine, "alerts", None):
        if not rows:
            return pd.DataFrame()
        out = pd.DataFrame(rows)
        out["Timestamp"] = pd.to_datetime(out["Timestamp"], errors="coerce")
        return out.sort_values("Timestamp", ascending=False).reset_index(drop=True)

    track_categories = {
        "SIGNAL", "PENDING_ENTRY", "ENTRY", "EXIT", "TARGET", "SL",
        "ORDER", "RISK", "REJECT", "FAILED", "ERROR",
    }

    for alert in engine.alerts:
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
                "Symbol": _extract_symbol(message),
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
last_candle_processed_at = st.session_state.get("last_candle_processed_at")
refresh_minutes = 1

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
instrument_symbol_labels: list[str] = []
for instrument in selected_instruments:
    state = instrument_states.get(instrument) or {}
    state_runtime = state.get("runtime")
    state_engine = None
    if state_runtime is not None and state_runtime.active_keys:
        state_engine = state_runtime.engines.get(state_runtime.active_keys[0])
    state_snapshot = state_engine.get_status_snapshot() if state_engine is not None else {}
    spot = str(
        dict(instrument_configs.get(instrument) or {}).get("symbol")
        or (state.get("source_params") or {}).get("openalgo_symbol")
        or instrument
    )
    ce_symbol = state_snapshot.get("ce_symbol")
    pe_symbol = state_snapshot.get("pe_symbol")
    if ce_symbol or pe_symbol:
        instrument_symbol_labels.append(
            f"{instrument}: {ce_symbol or '-'} CE | {pe_symbol or '-'} PE"
        )
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
    st.caption(f"Auto-refresh ({refresh_minutes} min)")
    st.caption(f"Last refresh: {last_refresh}")

with st.container(border=True):
    render_section_heading(
        "OpenAlgo feed logs",
        "Raw container log tail",
        "Shows the latest lines from the OpenAlgo container that the dashboard is connected to.",
    )
    if openalgo_log_error:
        st.warning(openalgo_log_error, icon="⚠️")
    elif not openalgo_log_lines:
        st.info("No OpenAlgo container logs available yet.", icon="📝")
    else:
        st.code("\n".join(openalgo_log_lines[-25:]), language="text")

with st.container(border=True):
    render_section_heading(
        "Console logs",
        "One consolidated row per minute",
        "Shows OHLC, EMA21, option values, trade status, and the next candle time.",
    )

    console_source_df = _build_console_logs_df(
        source_params,
        snapshot,
        _market_data_logs_df(),
        openalgo_log_lines,
    )

    if console_source_df.empty:
        st.info("No console logs available yet.", icon="📝")
    else:
        st.caption(f"{len(console_source_df)} log entries")
        console_view = console_source_df.copy()
        console_view = console_view[["Time", "Level", "Strategy", "Instrument", "Message"]].fillna("-")
        row_html = "".join(
            (
                "<tr>"
                f"<td>{escape(str(row['Time']))}</td>"
                f"<td>{escape(str(row['Level']))}</td>"
                f"<td>{escape(str(row['Strategy']))}</td>"
                f"<td>{escape(str(row['Instrument']))}</td>"
                f"<td>{escape(str(row['Message']))}</td>"
                "</tr>"
            )
            for _, row in console_view.iterrows()
        )
        st.markdown(
            f"""
            <div style="overflow-x:auto; overflow-y:auto; max-height:430px; border:1px solid rgba(86,184,222,0.28); border-radius:12px;">
                <table style="min-width:1700px; width:max-content; border-collapse:collapse; font-size:0.86rem; white-space:nowrap;">
                    <thead style="position:sticky; top:0; background:rgba(19,28,46,0.98); z-index:1;">
                        <tr>
                            <th style="text-align:left; padding:0.55rem 0.6rem; border-bottom:1px solid rgba(86,184,222,0.22);">Time</th>
                            <th style="text-align:left; padding:0.55rem 0.6rem; border-bottom:1px solid rgba(86,184,222,0.22);">Level</th>
                            <th style="text-align:left; padding:0.55rem 0.6rem; border-bottom:1px solid rgba(86,184,222,0.22);">Strategy</th>
                            <th style="text-align:left; padding:0.55rem 0.6rem; border-bottom:1px solid rgba(86,184,222,0.22);">Instrument</th>
                            <th style="text-align:left; padding:0.55rem 0.6rem; border-bottom:1px solid rgba(86,184,222,0.22);">Message</th>
                        </tr>
                    </thead>
                    <tbody>
                        {row_html}
                    </tbody>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

with st.container(border=True):
    render_section_heading(
        "Triggered alerts",
        "Saved alert events",
        "Captures actionable triggered alerts with date, time, symbol, category, status, and price.",
    )
    triggered_df = _sync_triggered_alert_rows(engine)
    if triggered_df.empty:
        st.info("No triggered alerts yet.", icon="🚨")
    else:
        st.caption(f"{len(triggered_df)} saved alerts")
        view_df = triggered_df[["Date", "Time", "Symbol", "Category", "Status", "Price", "Message"]].copy()
        view_df["Price"] = view_df["Price"].apply(lambda v: f"₹{v:,.2f}" if pd.notna(v) else "—")
        view_df["Status"] = view_df["Status"].map(lambda s: f"{_STATUS_BADGE.get(str(s), '⚪')} {s}")
        st.dataframe(
            view_df,
            hide_index=True,
            use_container_width=True,
            height=300,
            column_config={
                "Date": st.column_config.TextColumn("Date", width="small"),
                "Time": st.column_config.TextColumn("Time", width="small"),
                "Symbol": st.column_config.TextColumn("Symbol", width="medium"),
                "Category": st.column_config.TextColumn("Category", width="small"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Price": st.column_config.TextColumn("Price", width="small"),
                "Message": st.column_config.TextColumn("Message", width="large"),
            },
        )

