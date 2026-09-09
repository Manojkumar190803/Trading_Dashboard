"""Shared utilities, theme injection, broker helpers, and sidebar renderer.

Every app_page imports from this module so that layout, credentials, and
engine wiring are consistent across all pages.
"""
from __future__ import annotations

import os
import json
import re
import sys
from datetime import date, datetime, time, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

FRONTEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FRONTEND_DIR.parent
LOGS_DIR = PROJECT_ROOT / "logs"
PREFERENCES_PATH = LOGS_DIR / "dashboard_preferences.json"
for import_path in (FRONTEND_DIR, PROJECT_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

# Optional: auto-load .env from the app directory so secrets like
# OPENALGO_API_KEY never have to be typed into the UI.
try:
    from dotenv import load_dotenv  # type: ignore

    _ENV_PATH = PROJECT_ROOT / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH, override=False)
except ImportError:
    pass

from core.broker import BrokerInterface, OpenAlgoBroker
from core.indicators import add_indicators
from core.models import OrderSide, RiskConfig, StrategyConfig
from core.multi_strategy import MultiStrategyRuntime, STRATEGY_DEFINITIONS

try:
    from openalgo import api as _openalgo_api
except ImportError:
    _openalgo_api = None


class OpenAlgoError(RuntimeError):
    pass


class OpenAlgoConfig:
    def __init__(self, base_url: str, api_key: str, product_type: str = "INTRADAY") -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.product_type = product_type


class OpenAlgoDataClient:
    def __init__(self, config: OpenAlgoConfig) -> None:
        if _openalgo_api is None:
            raise OpenAlgoError("openalgo package is not installed")
        self.client = _openalgo_api(api_key=config.api_key, host=config.base_url)

    def fetch_history(self, symbol: str, resolution_minutes: int, days: int) -> pd.DataFrame:
        end = datetime.now(DISPLAY_TZ).date()
        start = end - timedelta(days=max(1, int(days)))
        exchange_by_prefix = {
            "NSE": "NSE_INDEX",
            "BSE": "BSE_INDEX",
        }
        symbol_prefix = symbol.split(":", 1)[0].upper() if ":" in symbol else ""
        exchange = exchange_by_prefix.get(symbol_prefix, "NFO")
        clean_symbol = symbol.split(":", 1)[-1]
        if "-INDEX" in clean_symbol:
            clean_symbol = clean_symbol.replace("-INDEX", "")
        try:
            raw = self.client.history(
                symbol=clean_symbol,
                exchange=exchange,
                interval=f"{resolution_minutes}m",
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
        except Exception as exc:
            raise OpenAlgoError(f"OpenAlgo history request failed: {exc}") from exc
        if isinstance(raw, dict) or raw is None:
            raise OpenAlgoError(f"history returned no data for {symbol}: {raw}")
        data = raw.copy()
        data = _normalize_ohlcv_datetime(data)
        if data.empty:
            return data
        # OpenAlgo can return multiple updates for the same candle timestamp.
        # Keep only the latest update so the live cursor cannot replay a candle.
        return (
            data.sort_values("datetime")
            .drop_duplicates(subset=["datetime"], keep="last")
            .reset_index(drop=True)
        )


class OpenAlgoAccountClient:
    def __init__(self, config: OpenAlgoConfig) -> None:
        if _openalgo_api is None:
            raise OpenAlgoError("openalgo package is not installed")
        self.client = _openalgo_api(api_key=config.api_key, host=config.base_url)

    def get_funds(self) -> dict[str, Any]:
        response = self.client.funds()
        return response.get("data", response) if isinstance(response, dict) else {}

    def get_positionbook(self) -> list[dict[str, Any]]:
        response = self.client.positionbook()
        data = response.get("data", []) if isinstance(response, dict) else []
        return data if isinstance(data, list) else []

    def get_orderbook(self) -> list[dict[str, Any]]:
        response = self.client.orderbook()
        data = response.get("data", []) if isinstance(response, dict) else []
        if isinstance(data, dict):
            data = data.get("orders", data.get("orderbook", []))
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a live broker order and return only on OpenAlgo success."""
        try:
            response = self.client.cancelorder(order_id=order_id)
        except Exception as exc:
            raise OpenAlgoError(f"OpenAlgo cancel request failed: {exc}") from exc
        return isinstance(response, dict) and response.get("status") == "success"


def _log_status_from_text(category: str, message: str) -> str:
    text = f"{category} {message}".upper()
    if any(value in text for value in ("FAIL", "ERROR", "EXCEPTION", "REJECT", "RISK")):
        return "FAILED"
    if any(value in text for value in ("EXIT", "TARGET", "T1", "T2", "T3", "SL HIT")):
        return "SUCCESS"
    if any(value in text for value in ("EXECUTED", "FILLED", "BUY ", "SELL ")):
        return "EXECUTED"
    if any(value in text for value in ("TRIGGERED", "ALERT", "SIGNAL")):
        return "TRIGGERED"
    return "INFO"


def _log_symbol_from_text(message: str) -> str:
    match = re.search(r"\b(NIFTY\w*|BANK\w*|SENSEX\w*|NSE:[A-Z0-9\-]+)\b", message, flags=re.IGNORECASE)
    return match.group(1).upper() if match else "-"


# ── Constants ──────────────────────────────────────────────────────────────────
STRATEGY_OPTIONS: list[str] = [
    "HD Strategy",
    "CD Strategy",
    "TC Strategy",
    "21EMA Strategy",
    "2BC Strategy",
    "BO Strategy",
]

STRATEGY_ENGINE_MAP: dict[str, tuple[str, str]] = {
    definition.label: ("core.multi_strategy", definition.key)
    for definition in STRATEGY_DEFINITIONS
}

DEFAULT_CSV = PROJECT_ROOT / "data" / "spot_3m.csv"
DISPLAY_TZ = ZoneInfo("Asia/Kolkata")


def _load_dashboard_preferences() -> dict[str, Any]:
    try:
        payload = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_lots_preference() -> None:
    try:
        lots = max(1, min(1000, int(st.session_state.get("lots", 1))))
    except (TypeError, ValueError):
        lots = 1
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        preferences = _load_dashboard_preferences()
        preferences["lots"] = lots
        temporary_path = PREFERENCES_PATH.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(preferences, indent=2) + "\n", encoding="utf-8"
        )
        temporary_path.replace(PREFERENCES_PATH)
    except OSError:
        # The dashboard can continue using session state if persistence is unavailable.
        pass


def load_spot_ohlcv_csv(csv_path: Path) -> pd.DataFrame:
    data = pd.read_csv(csv_path)
    return _normalize_ohlcv_datetime(data)


def _normalize_ohlcv_datetime(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    data.columns = [str(column).lower() for column in data.columns]
    if "datetime" not in data.columns and "timestamp" in data.columns:
        data = data.rename(columns={"timestamp": "datetime"})
    if "datetime" not in data.columns:
        if isinstance(data.index, pd.DatetimeIndex) or data.index.name in {"datetime", "timestamp"}:
            data = data.reset_index().rename(columns={data.index.name or "index": "datetime"})
        else:
            raise OpenAlgoError("OHLCV data does not contain a datetime column or index")
    data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")
    return data.dropna(subset=["datetime"]).reset_index(drop=True)

# ── Theme ──────────────────────────────────────────────────────────────────────

def inject_theme() -> None:
    """Inject the full dark trading-dashboard CSS into the Streamlit page."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

        :root {
            --hd-bg-start: #07111a;
            --hd-bg-end: #0f2430;
            --hd-card: rgba(10, 28, 38, 0.74);
            --hd-border: rgba(86, 184, 222, 0.34);
            --hd-accent: #59d0ff;
            --hd-green: #27d48a;
            --hd-red: #ff5f6d;
            --hd-text: #ecf8ff;
            --hd-muted: #afccd8;
        }

        .stApp {
            font-family: 'Space Grotesk', sans-serif;
            color: var(--hd-text);
            background:
                radial-gradient(1200px 600px at 8% -10%, rgba(89, 208, 255, 0.18), transparent 60%),
                radial-gradient(900px 500px at 92% 0%, rgba(39, 212, 138, 0.16), transparent 60%),
                linear-gradient(160deg, var(--hd-bg-start) 0%, var(--hd-bg-end) 100%);
        }

        /* ── Native top-navigation dark theme ─────────────────────────────── */
        header[data-testid="stHeader"] {
            background: rgba(9, 12, 22, 0.97) !important;
            border-bottom: 1px solid rgba(120, 130, 255, 0.22) !important;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3) !important;
        }

        /* Brand / logo area */
        [data-testid="stDecoration"] {
            background: rgba(9, 12, 22, 0.97) !important;
        }

        /* The nav list container */
        [data-testid="stTopNavigation"] {
            gap: 0.15rem !important;
        }

        /* Each page link */
        [data-testid="stTopNavigation"] a {
            padding: 0.45rem 0.8rem !important;
            border-radius: 8px !important;
            color: #a8abc0 !important;
            font-family: 'Space Grotesk', sans-serif !important;
            font-size: 0.82rem !important;
            font-weight: 600 !important;
            text-decoration: none !important;
            transition: background 0.18s ease, color 0.18s ease !important;
            white-space: nowrap !important;
        }

        [data-testid="stTopNavigation"] a:hover {
            background: rgba(140, 124, 246, 0.18) !important;
            color: #c8c4ff !important;
        }

        /* Active / selected page link */
        [data-testid="stTopNavigation"] a[aria-current="page"] {
            background: linear-gradient(135deg, #8c7cf6, #7869e8) !important;
            color: #ffffff !important;
            box-shadow: 0 4px 14px rgba(120, 105, 232, 0.35) !important;
        }

        /* Sidebar */
        section[data-testid='stSidebar'] {
            overflow-y: auto !important;
            overscroll-behavior: contain;
            background: rgba(7, 14, 24, 0.98) !important;
            border-right: 1px solid rgba(86, 184, 222, 0.15) !important;
        }

        section[data-testid='stSidebar'] > div,
        section[data-testid='stSidebar'] > div > div,
        section[data-testid='stSidebar'] > div > div > div {
            overflow: visible !important;
            max-height: none !important;
        }

        /* ── Selectbox / dropdown dark theme ─────────────────── */
        div[data-baseweb='select'] > div:first-child {
            background: rgba(8, 22, 34, 0.92) !important;
            border: 1px solid rgba(89, 208, 255, 0.38) !important;
            border-radius: 9px !important;
            color: #ecf8ff !important;
            font-family: 'Space Grotesk', sans-serif !important;
            font-size: 0.88rem !important;
            transition: border-color 0.2s ease;
        }
        div[data-baseweb='select'] > div:first-child:hover {
            border-color: rgba(89, 208, 255, 0.7) !important;
        }
        div[data-baseweb='select'] span { color: #c7f1ff !important; }
        div[data-baseweb='select'] svg { fill: rgba(89, 208, 255, 0.7) !important; }

        div[data-baseweb='popover'] { z-index: 1000000 !important; }
        ul[data-baseweb='menu'], div[data-baseweb='menu'] {
            background: rgba(7, 17, 28, 0.98) !important;
            border: 1px solid rgba(89, 208, 255, 0.28) !important;
            border-radius: 10px !important;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55) !important;
            padding: 0.25rem 0 !important;
            overflow-y: auto !important;
            max-height: 260px !important;
        }
        li[role='option'], div[data-baseweb='option'] {
            background: transparent !important;
            color: #d6f0ff !important;
            font-family: 'Space Grotesk', sans-serif !important;
            font-size: 0.88rem !important;
            padding: 0.5rem 0.85rem !important;
            cursor: pointer;
            transition: background 0.15s ease, color 0.15s ease;
        }
        li[role='option']:hover, div[data-baseweb='option']:hover {
            background: rgba(89, 208, 255, 0.14) !important;
            color: #59d0ff !important;
        }
        li[aria-selected='true'], div[aria-selected='true'] {
            background: rgba(89, 208, 255, 0.18) !important;
            color: #59d0ff !important;
            font-weight: 600 !important;
        }

        .block-container,
        [data-testid='stMainBlockContainer'] {
            max-width: 1080px;
            margin-left: auto;
            margin-right: auto;
            padding-top: 7rem !important;
            padding-bottom: 1.8rem;
        }

        /* ── Section heading ──────────────────────────────────── */
        .hd-section-heading {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 1rem;
            margin: .05rem 0 .8rem;
        }
        .hd-section-kicker {
            margin: 0 0 .18rem;
            color: #8f8aa8;
            font-size: .67rem;
            font-weight: 800;
            letter-spacing: .11em;
            text-transform: uppercase;
        }
        .hd-section-title {
            margin: 0;
            color: #f4f5fb;
            font-size: 1.02rem;
            font-weight: 750;
            letter-spacing: -.2px;
        }
        .hd-section-description {
            margin: .2rem 0 0;
            color: #9296aa;
            font-size: .8rem;
            line-height: 1.4;
        }

        /* ── Stat cards ───────────────────────────────────────── */
        .hd-stat {
            border: 1px solid var(--hd-border);
            border-radius: 14px;
            background: var(--hd-card);
            padding: 0.75rem 0.9rem;
            margin-bottom: 0.8rem;
            min-height: 78px;
        }
        .hd-stat-label {
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.75px;
            color: var(--hd-muted);
        }
        .hd-stat-value {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 1.12rem;
            color: #f2fbff;
            margin-top: 0.3rem;
            font-weight: 500;
        }

        /* ── Dashboard header + metric grid ───────────────────── */
        .hd-dashboard-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-top: 1rem;
            margin-bottom: 1.8rem;
            padding: 0 0.2rem;
        }
        .hd-header-left { flex: 1; }
        .hd-dashboard-title {
            font-size: 1.95rem;
            font-weight: 800;
            color: #ecf8ff;
            margin: 0 0 0.3rem 0;
            letter-spacing: -0.5px;
        }
        .hd-dashboard-subtitle {
            font-size: 0.92rem;
            color: #9db5cc;
            margin: 0;
            font-weight: 400;
            letter-spacing: 0.2px;
        }
        .hd-header-right {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        .hd-status-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: rgba(89, 208, 255, 0.08);
            border: 1px solid rgba(89, 208, 255, 0.25);
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            color: #59d0ff;
            white-space: nowrap;
        }
        .hd-status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50%       { opacity: 0.6; }
        }
        .hd-status-text { letter-spacing: 0.3px; }

        .hd-metrics-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 1.35rem;
            margin-bottom: 2.5rem;
            padding: 0 0.2rem;
        }
        .hd-metric-card-v2 {
            padding: 1.2rem 1rem;
            border-radius: 12px;
            background: linear-gradient(135deg, rgba(20, 35, 50, 0.8), rgba(15, 30, 45, 0.8));
            border: 1px solid rgba(89, 208, 255, 0.2);
            text-align: center;
            transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
            cursor: default;
        }
        .hd-metric-card-v2:hover {
            border-color: rgba(89, 208, 255, 0.4);
            background: linear-gradient(135deg, rgba(30, 50, 70, 0.95), rgba(25, 40, 60, 0.95));
            box-shadow: 0 4px 16px rgba(89, 208, 255, 0.15);
            transform: translateY(-3px);
        }
        .hd-metric-label-v2 {
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.6px;
            color: #7a9aaa;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            text-align: center;
        }
        .hd-metric-value-v2 {
            font-size: 1.65rem;
            font-weight: 800;
            font-family: 'IBM Plex Mono', -apple-system, monospace;
            letter-spacing: 0.1px;
            line-height: 1.1;
            margin-bottom: 0.4rem;
        }
        .hd-metric-sublabel {
            font-size: 0.7rem;
            font-weight: 500;
            letter-spacing: 0.4px;
            color: #6b8899;
            text-transform: capitalize;
        }

        @media (max-width: 1200px) {
            .hd-metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
        }
        @media (max-width: 900px) {
            .hd-metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.9rem; }
            .hd-metric-card-v2 { padding: 1rem 0.8rem; }
        }
        @media (max-width: 600px) {
            .hd-metrics-grid { grid-template-columns: 1fr; gap: 0.8rem; }
            .hd-dashboard-header { flex-direction: column; gap: 1rem; margin-bottom: 1.5rem; }
            .hd-header-right { width: 100%; justify-content: flex-start; }
            .hd-dashboard-title { font-size: 1.5rem; }
        }

        /* ── PnL chart ────────────────────────────────────────── */
        .hd-pnl-chart-container { margin-top: 1.5rem; margin-bottom: 0.8rem; padding: 0.8rem 0; }
        .hd-pnl-header {
            font-size: 0.75rem; font-weight: 800; letter-spacing: 0.8px;
            color: #9db5cc; text-transform: uppercase; margin-bottom: 0.6rem; opacity: 0.95;
        }
        div[data-testid='stChart'] {
            border-radius: 12px;
            background: linear-gradient(135deg, rgba(15, 35, 55, 0.5), rgba(20, 45, 65, 0.5)) !important;
            border: 1px solid rgba(89, 208, 255, 0.15) !important;
            padding: 1rem !important;
            box-shadow: 0 2px 12px rgba(39, 212, 138, 0.04) !important;
        }

        /* ── Mode / trading toggles ───────────────────────────── */
        .hd-important-section {
            margin: 0.65rem 0 0.85rem 0;
            padding: 0.8rem 0.8rem 0.75rem 0.8rem;
            border-radius: 14px;
            border: 1px solid rgba(255, 95, 109, 0.45);
            background: linear-gradient(135deg, rgba(55, 15, 22, 0.96), rgba(26, 20, 30, 0.92));
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
        }
        .hd-important-section.paper {
            border-color: rgba(39, 212, 138, 0.55);
            background: linear-gradient(135deg, rgba(12, 58, 41, 0.96), rgba(18, 39, 32, 0.92));
        }
        .hd-important-section.real {
            border-color: rgba(255, 95, 109, 0.58);
            background: linear-gradient(135deg, rgba(65, 16, 27, 0.96), rgba(32, 20, 26, 0.92));
        }
        .hd-important-title {
            font-size: 0.88rem; font-weight: 800; letter-spacing: 0.9px;
            color: #ffe7ea; text-transform: uppercase;
        }
        .hd-important-subtitle { margin-top: 0.25rem; font-size: 0.74rem; color: #ffbbc3; }
        .hd-mode-description {
            margin: 0.55rem 0 0.85rem 0;
            padding: 0.6rem 0.7rem;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #f4e7ea; font-size: 0.78rem; line-height: 1.35;
        }

        /* ── Engine control buttons ───────────────────────────── */
        div:has(.hd-ec-start) + div button {
            background: rgba(39, 212, 138, 0.45) !important;
            border: 2px solid #27d48a !important;
            color: #ffffff !important;
            font-size: 0.95rem !important; font-weight: 700 !important;
            letter-spacing: 0.4px !important; padding: 0.68rem 0.5rem !important;
            box-shadow: 0 0 20px rgba(39, 212, 138, 0.35) !important;
            transition: all 0.2s ease !important;
        }
        div:has(.hd-ec-start) + div button:hover {
            background: rgba(39, 212, 138, 0.65) !important;
            box-shadow: 0 0 30px rgba(39, 212, 138, 0.55) !important;
        }
        div:has(.hd-ec-pause) + div button {
            background: rgba(255, 190, 50, 0.45) !important;
            border: 2px solid rgba(255, 190, 50, 0.9) !important;
            color: #1a1200 !important; font-size: 0.9rem !important;
            font-weight: 700 !important; padding: 0.6rem 0.5rem !important;
            box-shadow: 0 0 16px rgba(255, 190, 50, 0.3) !important;
            transition: all 0.2s ease !important;
        }
        div:has(.hd-ec-pause) + div button:hover {
            background: rgba(255, 190, 50, 0.65) !important;
            box-shadow: 0 0 26px rgba(255, 190, 50, 0.5) !important;
        }
        div:has(.hd-ec-panic) + div button {
            background: rgba(220, 38, 55, 0.55) !important;
            border: 2px solid rgba(255, 60, 80, 0.95) !important;
            color: #ffffff !important; font-size: 0.95rem !important;
            font-weight: 700 !important; letter-spacing: 0.4px !important;
            padding: 0.68rem 0.5rem !important;
            box-shadow: 0 0 20px rgba(220, 38, 55, 0.4) !important;
            transition: all 0.2s ease !important;
        }
        div:has(.hd-ec-panic) + div button:hover {
            background: rgba(220, 38, 55, 0.75) !important;
            box-shadow: 0 0 30px rgba(220, 38, 55, 0.6) !important;
        }

        /* ── Sidebar typography ───────────────────────────────── */
        section[data-testid='stSidebar'] h3 {
            font-size: 1.05rem !important; font-weight: 700 !important;
            letter-spacing: 0.3px !important; color: #f0f9ff !important;
            margin-top: 0.65rem !important; margin-bottom: 0.25rem !important;
            padding-bottom: 0.25rem !important;
            border-bottom: 1px solid rgba(89, 208, 255, 0.22) !important;
        }
        section[data-testid='stSidebar'] [data-testid='stVerticalBlockBorderWrapper'],
        section[data-testid='stSidebar'] [data-testid='element-container'] {
            margin-bottom: 0 !important;
        }
        section[data-testid='stSidebar'] label,
        section[data-testid='stSidebar'] .stToggle label,
        section[data-testid='stSidebar'] .stSelectbox label {
            font-size: 0.82rem !important; font-weight: 500 !important;
            color: #afccd8 !important;
        }

        /* ── Misc widget styling ──────────────────────────────── */
        div[data-testid='stTabs'] button { font-weight: 600; color: #d7effa; }
        div[data-testid='stMetric'] {
            border: 1px solid var(--hd-border);
            border-radius: 14px; padding: 0.25rem 0.45rem; background: var(--hd-card);
        }
        div[data-testid='stDataFrame'] {
            border: 1px solid var(--hd-border);
            border-radius: 14px; overflow: hidden; background: rgba(10, 30, 43, 0.78);
        }
        div[data-testid='stJson'] {
            border: 1px solid var(--hd-border);
            border-radius: 14px; background: rgba(10, 30, 43, 0.78); padding: 0.2rem;
        }
        div[data-testid='stVerticalBlockBorderWrapper'] {
            border-color: rgba(116, 117, 151, 0.24) !important;
            border-radius: 16px !important;
            background: rgba(12, 18, 30, 0.5) !important;
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.12) !important;
        }

        @media (max-width: 768px) {
            .block-container,
            [data-testid='stMainBlockContainer'] {
                padding-top: 5.5rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def format_money(value: float) -> str:
    return f"{value:,.2f}"


def render_section_heading(kicker: str, title: str, description: str) -> None:
    st.html(
        f"""
        <div class='hd-section-heading'>
            <div>
                <p class='hd-section-kicker'>{kicker}</p>
                <h2 class='hd-section-title'>{title}</h2>
                <p class='hd-section-description'>{description}</p>
            </div>
        </div>
        """
    )


# ── Broker / data helpers ──────────────────────────────────────────────────────

@dataclass
class DashboardBroker:
    base_time_value_ratio: float = 0.02
    intrinsic_multiplier: float = 0.85
    min_option_price: float = 2.0

    def __post_init__(self) -> None:
        self.current_spot: float = 0.0

    def set_spot(self, spot: float) -> None:
        self.current_spot = spot

    def _parse_option(self, symbol: str) -> tuple[int | None, str | None]:
        match = re.search(r"(\d+)(CE|PE)$", symbol)
        if not match:
            return None, None
        strike, option_type = match.groups()
        return int(strike), option_type

    def get_ltp(self, symbol: str) -> float:
        strike, option_type = self._parse_option(symbol)
        if strike is None or option_type is None:
            return max(self.min_option_price, self.current_spot * self.base_time_value_ratio)
        intrinsic = (
            max(self.current_spot - strike, 0.0)
            if option_type == "CE"
            else max(strike - self.current_spot, 0.0)
        )
        time_value = max(self.min_option_price, self.current_spot * self.base_time_value_ratio)
        return round((intrinsic * self.intrinsic_multiplier) + time_value, 2)

    def place_stop_limit_order(
        self, symbol: str, side: OrderSide, quantity: int,
        trigger_price: float, limit_price: float,
    ) -> str:
        return f"SIM-SL-{symbol}-{side.value}-{quantity}"

    def place_market_order(self, symbol: str, side: OrderSide, quantity: int) -> str:
        return f"SIM-MKT-{symbol}-{side.value}-{quantity}"

    def get_position_book(self) -> list[dict[str, object]]:
        return []

    def get_order_status(self, order_id: str) -> dict[str, object]:
        return {"order_status": "complete", "orderid": order_id}

    def get_open_orders(self) -> list[dict[str, object]]:
        return []

    def cancel_order(self, order_id: str) -> bool:
        return True

    def modify_stop_limit_order(
        self, order_id: str, symbol: str, side: OrderSide, quantity: int,
        trigger_price: float, limit_price: float,
    ) -> bool:
        return True


def load_data(source: str, source_params: dict[str, Any], cfg: StrategyConfig) -> pd.DataFrame:
    if source == "CSV":
        return add_indicators(load_spot_ohlcv_csv(Path(source_params["csv_path"])), cfg)
    
    # Default to OPENALGO
    if source == "OPENALGO" or source not in ("CSV",):
        return _load_openalgo_symbol_data(
            source_params,
            cfg,
            str(source_params.get("openalgo_symbol", "NSE:NIFTY-INDEX")),
        )


def _load_openalgo_symbol_data(
    source_params: dict[str, Any],
    cfg: StrategyConfig,
    symbol: str,
) -> pd.DataFrame:
    config = OpenAlgoConfig(
        base_url=source_params.get("openalgo_base_url", "http://host.docker.internal:5002"),
        api_key=source_params.get("openalgo_api_key", ""),
        product_type=source_params.get("product_type", "INTRADAY"),
    )
    raw = OpenAlgoDataClient(config).fetch_history(
        symbol=symbol,
        resolution_minutes=int(source_params.get("openalgo_resolution", 3)),
        days=int(source_params.get("openalgo_days", 5)),
    )
    return add_indicators(raw, cfg)


def build_broker(source: str, source_params: dict[str, Any]) -> BrokerInterface:
    # Orders are always routed through OpenAlgo when it is the data source.
    # OpenAlgo's own Analyze/Live toggle decides whether they are simulated
    # or sent to the market, so the Streamlit app no longer needs a mode switch.
    if source == "OPENALGO":
        return OpenAlgoBroker(
            api_key=str(source_params.get("openalgo_api_key", "")),
            host=str(source_params.get("openalgo_base_url", "http://host.docker.internal:5002")),
            strategy_tag="Streamlit_MultiStrategy",
            product=str(source_params.get("product_type", "INTRADAY")),
            dry_run=str(os.getenv("OPENALGO_DRY_RUN", "true")).lower() != "false",
        )

    # CSV replay uses the in-process simulator.
    return DashboardBroker()


def _build_instrument_state(
    data: pd.DataFrame,
    source: str,
    source_params: dict[str, Any],
) -> dict[str, Any]:
    cfg = StrategyConfig()
    instrument_config = source_params.get("instrument_config") or {}
    for config_name in (
        "spot_symbol",
        "option_index_symbol",
        "exchange_spot",
        "exchange_options",
        "strike_step",
        "weekly_expiry_weekday",
        "timeframe_minutes",
    ):
        config_value = instrument_config.get(config_name)
        if config_name == "timeframe_minutes" and config_value is None:
            config_value = source_params.get("openalgo_resolution")
        if config_value is not None and hasattr(cfg, config_name):
            setattr(cfg, config_name, config_value)
    # Override lot size from sidebar selection so per-instrument NSE contract
    # sizes or user overrides are respected.
    lot_override = source_params.get("option_lot_size")
    if lot_override:
        try:
            cfg.option_lot_size = int(lot_override)
        except (TypeError, ValueError):
            pass
    # Scale the strategy's full/half lot counts to match the user's chosen
    # number of lots so quantity = lots × contract_size dynamically.
    lots_override = source_params.get("lots")
    if lots_override:
        try:
            lots_val = max(1, int(lots_override))
            cfg.full_size_lots = lots_val
            cfg.half_size_lots = max(1, lots_val // 2)
        except (TypeError, ValueError):
            pass
    risk = RiskConfig()
    broker = build_broker(source, source_params)
    enabled_labels = list(source_params.get("selected_strategy") or ["21EMA Strategy"])
    enabled_keys = [
        definition.key
        for definition in STRATEGY_DEFINITIONS
        if definition.label in enabled_labels
    ]
    runtime = MultiStrategyRuntime(cfg, risk, broker, enabled_keys=enabled_keys or ["ema21"])
    for engine in runtime.engines.values():
        engine.persist_alerts = True

    return {
        "cfg": cfg,
        "risk": risk,
        "broker": broker,
        "runtime": runtime,
        "engines": runtime.engines,
        "engine": runtime.engines.get(enabled_keys[0] if enabled_keys else "ema21"),
        "data": data,
        "source_params": source_params,
        "index": max(len(data) - 1, 0),
        "running": False,
        "engine_status": "stopped",
        "equity_curve": [],
        "option_data": {},
    }


def _set_primary_instrument_aliases(state: dict[str, Any]) -> None:
    """Expose the first selected instrument through legacy page state keys."""
    for key in (
        "cfg", "risk", "broker", "runtime", "engines", "engine", "data",
        "source_params", "index", "running", "engine_status", "equity_curve",
        "option_data",
    ):
        st.session_state[key] = state[key]


def init_engine_state(data: pd.DataFrame, source: str, source_params: dict[str, Any]) -> None:
    selected_instruments = list(source_params.get("selected_instruments") or [
        source_params.get("primary_instrument", "Nifty50")
    ])
    instrument_configs = source_params.get("instrument_configs") or {}
    instrument_states: dict[str, dict[str, Any]] = {}
    for position, instrument in enumerate(selected_instruments):
        instrument_params = dict(source_params)
        instrument_params["primary_instrument"] = instrument
        metadata = dict(instrument_configs.get(instrument) or {})
        instrument_params["openalgo_symbol"] = str(
            metadata.get("symbol") or source_params.get("openalgo_symbol")
        )
        instrument_params["instrument_config"] = metadata
        instrument_params["option_lot_size"] = int(
            (source_params.get("instrument_lot_sizes") or {}).get(instrument)
            or source_params.get("option_lot_size")
            or 1
        )
        instrument_data = data if position == 0 else load_data(
            source, instrument_params, StrategyConfig()
        )
        instrument_states[instrument] = _build_instrument_state(
            instrument_data, source, instrument_params
        )

    st.session_state.instrument_states = instrument_states
    _set_primary_instrument_aliases(instrument_states[selected_instruments[0]])
    st.session_state.source = source
    st.session_state.selected_instruments = selected_instruments
    st.session_state.market_data_logs = []


def sync_openalgo_data(source_params: dict[str, Any], cfg: StrategyConfig) -> None:
    """Refresh the cached OpenAlgo frame while preserving candle progress.

    The dashboard should not replay several days of history from index 0 on
    every fresh session. Instead, align the in-memory cursor to the last
    processed candle timestamp and only leave genuinely new candles pending.
    """
    latest_data = load_data("OPENALGO", source_params, cfg)
    existing_data = st.session_state.get("data")
    current_index = int(st.session_state.get("index", 0) or 0)
    last_processed_dt = None

    if isinstance(existing_data, pd.DataFrame) and not existing_data.empty:
        processed_idx = current_index - 1
        if 0 <= processed_idx < len(existing_data):
            last_processed_dt = pd.to_datetime(existing_data.iloc[processed_idx]["datetime"])

    if last_processed_dt is None:
        next_index = max(len(latest_data) - 1, 0)
    else:
        next_index = int((pd.to_datetime(latest_data["datetime"]) <= last_processed_dt).sum())
        next_index = min(next_index, len(latest_data))

    st.session_state.data = latest_data
    st.session_state.index = next_index

    runtime: MultiStrategyRuntime | None = st.session_state.get("runtime")
    option_frames: dict[str, dict[str, pd.DataFrame]] = {}
    if runtime is not None:
        for key, engine in runtime.engines.items():
            strategy_frames: dict[str, pd.DataFrame] = {}
            for side, sym in (("CE", engine.state.ce_symbol), ("PE", engine.state.pe_symbol)):
                if not sym:
                    continue
                try:
                    strategy_frames[side] = _load_openalgo_symbol_data(source_params, cfg, str(sym))
                except Exception:
                    continue
            if strategy_frames:
                option_frames[key] = strategy_frames
    st.session_state.option_data = option_frames


def _apply_lot_config_to_engine(lots: int, option_lot_size: int) -> None:
    """Hot-update the live engine's lot config so the next OpenAlgo order uses
    the new quantity. Safe to call every rerun; no-op if the engine isn't up
    yet or values are invalid.
    """
    try:
        lots_val = max(1, int(lots))
        lot_size_val = max(1, int(option_lot_size))
    except (TypeError, ValueError):
        return

    _apply_lot_config_to_cfg(
        st.session_state.get("cfg"),
        lots_val,
        lot_size_val,
    )

    # The engine holds its own reference to cfg (same object), so no further
    # wiring is required — the next signal will compute
    # quantity = lots × option_lot_size and send it to OpenAlgo.


def _apply_lot_config_to_cfg(
    cfg: StrategyConfig | None,
    lots: int,
    option_lot_size: int,
) -> None:
    if cfg is None:
        return
    cfg.option_lot_size = int(option_lot_size)
    cfg.full_size_lots = int(lots)
    cfg.half_size_lots = max(1, int(lots) // 2)


def _next_candle_boundary(candle_ts: pd.Timestamp, resolution_minutes: int) -> tuple[str, int]:
    """Return the next feed boundary and seconds remaining from the processed candle."""
    resolution = max(1, int(resolution_minutes))
    next_minute = ((int(candle_ts.minute) // resolution) + 1) * resolution
    next_ts = candle_ts.replace(second=0, microsecond=0)
    if next_minute >= 60:
        next_ts = next_ts.replace(minute=0) + timedelta(hours=1)
    else:
        next_ts = next_ts.replace(minute=next_minute)
    wait_seconds = resolution * 60
    return next_ts.strftime("%H:%M:%S"), wait_seconds


def _persist_monitoring_log(row: dict[str, Any]) -> None:
    """Append a monitoring row to the mounted daily CSV and tabular text log."""
    timestamp = pd.to_datetime(row.get("timestamp"), errors="coerce")
    if pd.isna(timestamp):
        return
    local_ts = timestamp.tz_localize(DISPLAY_TZ) if timestamp.tzinfo is None else timestamp.tz_convert(DISPLAY_TZ)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    date_key = local_ts.strftime("%Y%m%d")
    csv_path = LOGS_DIR / f"monitoring_{date_key}.csv"
    txt_path = LOGS_DIR / f"monitoring_{date_key}.txt"
    persisted = dict(row)
    persisted["timestamp"] = local_ts.isoformat()
    frame = pd.DataFrame([persisted])
    frame.to_csv(csv_path, mode="a", header=not csv_path.exists(), index=False)
    frame.to_csv(txt_path, mode="a", sep="\t", header=not txt_path.exists(), index=False)


def build_strategy_engine(
    strategy_name: str,
    cfg: StrategyConfig,
    risk: RiskConfig,
    broker: BrokerInterface,
) -> Any:
    definition = next(
        (item for item in STRATEGY_DEFINITIONS if item.label == strategy_name),
        STRATEGY_DEFINITIONS[0],
    )
    return MultiStrategyRuntime(cfg, risk, broker, [definition.key]).engines[definition.key]


def _process_single_instrument_candle() -> None:
    data: pd.DataFrame = st.session_state.data
    idx: int = int(st.session_state.index)
    runtime: MultiStrategyRuntime = st.session_state.runtime
    if idx >= len(data):
        st.session_state.running = False
        return

    processed_now = datetime.now(DISPLAY_TZ)
    row = data.iloc[idx]
    prev_row = data.iloc[idx - 1] if idx > 0 else None
    source_params = st.session_state.get("source_params", {}) or {}
    feed_symbol = str(source_params.get("openalgo_symbol") or "NSE:NIFTY-INDEX")
    broker = st.session_state.broker
    if isinstance(broker, DashboardBroker):
        broker.set_spot(float(row["close"]))
    ts = pd.to_datetime(row["datetime"])

    option_frames: dict[str, dict[str, pd.DataFrame]] = {}
    alert_counts_before = {
        key: len(engine.alerts) for key, engine in runtime.engines.items()
    }
    for key, engine in runtime.engines.items():
        if not engine.state.atm_locked and ts.time() >= engine.cfg.atm_lock_time:
            engine.on_day_transition_if_needed(ts)
            engine.lock_atm_for_day(ts, float(row["close"]))
        if not engine.state.atm_locked:
            continue
        strategy_frames: dict[str, pd.DataFrame] = {}
        for side, symbol in (("CE", engine.state.ce_symbol), ("PE", engine.state.pe_symbol)):
            if not symbol:
                continue
            try:
                strategy_frames[side] = _load_openalgo_symbol_data(
                    source_params, engine.cfg, str(symbol)
                )
            except Exception:
                continue
        if strategy_frames:
            option_frames[key] = strategy_frames

    runtime.process_candle(row, prev_row, option_frames)
    st.session_state.engines = runtime.engines
    selected_key = runtime.active_keys[0] if runtime.active_keys else "ema21"
    st.session_state.engine = runtime.engines.get(selected_key)
    engine = st.session_state.engine
    snapshot = engine.get_status_snapshot() if engine is not None else {}
    st.session_state.equity_curve.append(
        {
            "datetime": row["datetime"],
            "total_pnl": snapshot["total_pnl"],
            "realized_pnl": snapshot["realized_pnl"],
            "unrealized_pnl": snapshot["unrealized_pnl"],
            "spot_close": float(row["close"]),
        }
    )
    market_data_logs = st.session_state.get("market_data_logs") or []
    resolution = int(source_params.get("openalgo_resolution") or 3)
    candle_ts = pd.to_datetime(row["datetime"])
    ema21 = row.get("ema21")
    ema_text = "NA" if ema21 is None or pd.isna(ema21) else f"{float(ema21):.2f}"
    option_parts: list[str] = []
    active_parts: list[str] = []
    new_alert_parts: list[str] = []
    actionable_alert_categories = {
        "SIGNAL", "PENDING_ENTRY", "ENTRY", "EXIT", "TARGET", "SL",
        "ORDER", "RISK", "REJECT", "FAILED", "ERROR", "UNCERTAIN_ENTRY",
    }
    has_actionable_event = False
    for strategy_key, active_engine in runtime.engines.items():
        strategy_snapshot = active_engine.get_status_snapshot()
        new_alerts = active_engine.alerts[alert_counts_before.get(strategy_key, 0):]
        for alert in new_alerts:
            category = str(alert.category).upper()
            new_alert_parts.append(
                f"{category}: {str(alert.message)}"
            )
            if category in actionable_alert_categories:
                has_actionable_event = True
        for side in ("CE", "PE"):
            side_snapshot = strategy_snapshot.get(side.lower(), {}) or {}
            symbol = side_snapshot.get("watched_symbol") or strategy_snapshot.get(f"{side.lower()}_symbol")
            option_frame = (option_frames.get(strategy_key) or {}).get(side)
            option_close = None
            if isinstance(option_frame, pd.DataFrame) and not option_frame.empty:
                option_close = option_frame.iloc[-1].get("close")
            position = side_snapshot.get("position")
            pending = side_snapshot.get("pending_entry")
            status = "OPEN" if position else "PENDING" if pending else "FLAT"
            price_text = "NA" if option_close is None or pd.isna(option_close) else f"{float(option_close):.2f}"
            option_parts.append(f"{side}={symbol or '-'}@{price_text} {status}")
            if position:
                active_parts.append(
                    f"{side} LTP={float(position.get('current_price') or option_close or 0):.2f} "
                    f"Entry={float(position.get('entry_price') or 0):.2f} "
                    f"SL={float(position.get('option_stop_level') or 0):.2f} "
                    f"P&L={float(strategy_snapshot.get('unrealized_pnl') or 0):.2f} "
                    f"{position.get('progress_status') or 'ACTIVE'}"
                )
    status_text = "ACTIVE TRADE: " + " | ".join(active_parts) if active_parts else "No active trade"
    alert_text = " | ALERT: " + " | ".join(new_alert_parts) if new_alert_parts else ""
    next_ts, wait_seconds = _next_candle_boundary(candle_ts, resolution)
    # Keep routine console monitoring at three-minute cadence, but never hide
    # a candle that produced a new alert or confirmation.
    is_event = has_actionable_event
    is_monitoring_boundary = candle_ts.minute % 3 == 0
    if not is_event and not is_monitoring_boundary:
        st.session_state.last_candle_processed_at = processed_now
        st.session_state.index = idx + 1
        return

    monitoring_row = {
            "timestamp": processed_now,
            "category": "ALERT" if is_event else "DATA",
            "status": "TRIGGERED" if is_event else ("ACTIVE" if active_parts else "INFO"),
            "symbol": feed_symbol,
            "entry_price": None,
            "exit_price": None,
            "trade_pnl": None,
            "message": (
                f"{resolution}m candle {candle_ts.strftime('%H:%M:%S')} "
                f"O={float(row['open']):.2f} H={float(row['high']):.2f} "
                f"L={float(row['low']):.2f} C={float(row['close']):.2f} "
                f"EMA21={ema_text} | {' | '.join(option_parts) or 'Options=NA'} | "
                f"{status_text}{alert_text} | Next candle at {next_ts} (waiting {wait_seconds}s)"
            ),
        }
    market_data_logs.append(monitoring_row)
    _persist_monitoring_log(monitoring_row)

    if len(market_data_logs) > 500:
        market_data_logs = market_data_logs[-500:]
    st.session_state.market_data_logs = market_data_logs
    st.session_state.last_candle_processed_at = processed_now
    st.session_state.index = idx + 1


def process_next_candle() -> None:
    """Advance every selected instrument in the single Streamlit process."""
    instrument_states = st.session_state.get("instrument_states")
    if not instrument_states:
        _process_single_instrument_candle()
        return

    state_keys = (
        "cfg", "risk", "broker", "runtime", "engines", "engine", "data",
        "source_params", "index", "running", "engine_status", "equity_curve",
        "option_data",
    )
    for instrument, state in instrument_states.items():
        if not state.get("running", False):
            continue
        _set_primary_instrument_aliases(state)
        _process_single_instrument_candle()
        for key in state_keys:
            state[key] = st.session_state.get(key, state[key])
        state["running"] = st.session_state.get("running", state["running"])

    primary_instrument = next(iter(instrument_states), None)
    if primary_instrument is not None:
        _set_primary_instrument_aliases(instrument_states[primary_instrument])
        any_running = any(
            bool(instrument_state.get("running"))
            for instrument_state in instrument_states.values()
        )
        st.session_state.running = any_running
        st.session_state.engine_status = "running" if any_running else "paused"


# ── Live account refresh (funds / positions / orderbook) ─────────────────────

_LIVE_REFRESH_MIN_INTERVAL_SEC = 3.0


def refresh_live_account_metrics(source_params: dict[str, Any] | None = None) -> None:
    """Fetch live funds/positions/orderbook from OpenAlgo and push into session_state.

    Populates:
        - ``available_margin``  (float)
        - ``net_mtm``           (float, sum of realized + unrealized)
        - ``active_trades``     (int, count of non-zero net-qty positions)
        - ``live_positions``    (list[dict])
        - ``live_orders``       (list[dict])
        - ``live_account_error``(str | None)
        - ``live_account_updated_at`` (ISO timestamp string)

    Safe to call on every rerun; internally throttled so it hits OpenAlgo at
    most once every few seconds. It only reads account state, never places
    orders — paper vs. live is controlled inside OpenAlgo itself.
    """
    now = datetime.now()
    display_now = datetime.now(DISPLAY_TZ)
    last_ts = st.session_state.get("_live_refresh_last_ts")
    if isinstance(last_ts, datetime):
        if (now - last_ts).total_seconds() < _LIVE_REFRESH_MIN_INTERVAL_SEC:
            return
    st.session_state["_live_refresh_last_ts"] = now

    params = source_params or st.session_state.get("source_params", {}) or {}
    base_url = (
        params.get("openalgo_base_url")
        or os.getenv("OPENALGO_BASE_URL")
        or os.getenv("OPENALGO_HOST", "http://host.docker.internal:5002")
    )
    api_key = (
        params.get("openalgo_api_key")
        or os.getenv("OPENALGO_API_KEY", "")
    )
    if not api_key:
        st.session_state["live_account_error"] = (
            "OPENALGO_API_KEY is not set. Add it to the .env file next to the app "
            "and restart to see live funds and positions."
        )
        return

    try:
        client = OpenAlgoAccountClient(
            OpenAlgoConfig(
                base_url=base_url,
                api_key=api_key,
                product_type=params.get("product_type", "INTRADAY"),
            )
        )
        funds = client.get_funds()
        positions = client.get_positionbook()
        orders = client.get_orderbook()
    except OpenAlgoError as exc:
        msg = str(exc)
        lower_msg = msg.lower()
        if "403" in msg or ("invalid" in lower_msg and "apikey" in lower_msg):
            st.session_state["live_account_error"] = (
                f"Live account authorization failed for {base_url}. "
                "The OPENALGO_API_KEY in Trading_Setups/.env was rejected by OpenAlgo. "
                "Copy the API key from the OpenAlgo API Key page for this exact instance and restart the app."
            )
        else:
            st.session_state["live_account_error"] = msg
        return
    except Exception as exc:  # network / parsing safety net
        st.session_state["live_account_error"] = f"Live refresh failed: {exc}"
        return

    open_positions = [p for p in positions if int(p.get("quantity", 0) or 0) != 0]
    positions_pnl = sum(float(p.get("pnl", 0.0) or 0.0) for p in open_positions)
    realized_mtm = funds.get("realized_mtm", funds.get("m2mrealized", 0.0))
    unrealized_mtm = funds.get("unrealized_mtm", funds.get("m2munrealized", 0.0))
    net_mtm = float(realized_mtm or 0.0) + float(unrealized_mtm or 0.0)
    if net_mtm == 0.0 and funds.get("totalpnl") is not None:
        net_mtm = float(funds.get("totalpnl") or 0.0)
    # If broker didn't populate MTM inside funds, fall back to positions P&L.
    if net_mtm == 0.0 and positions_pnl != 0.0:
        net_mtm = positions_pnl

    available_margin = funds.get("available_margin", funds.get("availablecash", 0.0))
    st.session_state["available_margin"] = float(available_margin or 0.0)
    st.session_state["used_margin"] = float(funds.get("used_margin", 0.0))
    st.session_state["net_mtm"] = float(net_mtm)
    st.session_state["active_trades"] = len(open_positions)
    st.session_state["live_positions"] = positions
    st.session_state["live_orders"] = orders
    st.session_state["live_account_error"] = None
    st.session_state["live_account_updated_at"] = display_now.strftime("%H:%M:%S IST")


def run_premarket_checks(source_params: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Run read-only readiness checks against the current dashboard state."""
    params = source_params or st.session_state.get("source_params", {}) or {}
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    broker = st.session_state.get("broker")
    data = st.session_state.get("data")
    runtime = st.session_state.get("runtime")
    feed_symbol = str(params.get("openalgo_symbol") or "NSE:NIFTY-INDEX")

    add(
        "OpenAlgo configuration",
        "READY" if params.get("openalgo_base_url") else "FAILED",
        str(params.get("openalgo_base_url") or "Base URL is not configured"),
    )
    add(
        "Selected strategies",
        "READY" if runtime is not None and getattr(runtime, "engines", {}) else "FAILED",
        "All selected strategies initialized"
        if runtime is not None and getattr(runtime, "engines", {})
        else "One or more selected strategies are not initialized",
    )

    data_ready = isinstance(data, pd.DataFrame) and not data.empty
    indicator_ready = data_ready and {"ema21"}.issubset(data.columns)
    add(
        "Market candles and indicators",
        "READY" if indicator_ready else ("WARNING" if data_ready else "FAILED"),
        f"{len(data):,} candles loaded; EMA21 available" if indicator_ready
        else ("Candles loaded but EMA21 is missing" if data_ready else "No market candles loaded"),
    )

    quote_value = 0.0
    quote_error = ""
    if broker is not None:
        try:
            quote_value = float(broker.get_ltp(feed_symbol) or 0.0)
        except Exception as exc:
            quote_error = str(exc)
    add(
        "Live market quote",
        "READY" if quote_value > 0 else "FAILED",
        f"{feed_symbol} LTP {quote_value:.2f}" if quote_value > 0
        else (quote_error or f"No quote returned for {feed_symbol}"),
    )

    account_error = st.session_state.get("live_account_error")
    account_updated = st.session_state.get("live_account_updated_at")
    add(
        "Funds and account APIs",
        "READY" if account_updated and not account_error else "FAILED",
        f"Last successful account sync: {account_updated}" if account_updated and not account_error
        else str(account_error or "Account data has not been loaded"),
    )

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        probe = LOGS_DIR / ".premarket_write_check"
        probe.write_text("ready\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
        logs_status, logs_detail = "READY", "Logs directory is writable"
    except OSError as exc:
        logs_status, logs_detail = "FAILED", f"Logs directory is not writable: {exc}"
    add("Monitoring log storage", logs_status, logs_detail)

    return checks


# ── Sidebar (common across all pages) ─────────────────────────────────────────

def render_sidebar() -> dict[str, Any]:
    """Render sidebar controls and return source_params dict."""
    # Keep the monitoring loop alive regardless of which page is open.
    st_autorefresh(interval=60_000, key="shared-monitor-refresh")
    product_type = os.getenv("PRODUCT_TYPE", "INTRADAY").upper()

    st.sidebar.markdown(
        """
        <div style="
            margin: 0.1rem 0 1.35rem;
            padding: 0.7rem 0.75rem;
            border: 1px solid rgba(89, 208, 255, 0.24);
            border-radius: 10px;
            background: rgba(12, 26, 40, 0.58);
            color: #e8f4ff;
            font-weight: 800;
            letter-spacing: 0.35px;
            font-size: 1.05rem;
        ">
            ⚙ Trading Setup
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Strategy Selection ────────────────────────────────────────────────────
    st.sidebar.markdown("### Strategy Selection")
    if "strategy_enabled" not in st.session_state:
        st.session_state.strategy_enabled = {
            s: (s == "21EMA Strategy") for s in STRATEGY_OPTIONS
        }

    for strategy in STRATEGY_OPTIONS:
        is_on = st.sidebar.toggle(
            strategy,
            value=st.session_state.strategy_enabled[strategy],
            key=f"strat_toggle_{strategy.replace(' ', '_')}",
        )
        st.session_state.strategy_enabled[strategy] = is_on

    enabled_strategies = [s for s in STRATEGY_OPTIONS if st.session_state.strategy_enabled[s]]
    active_strategy = enabled_strategies[0] if enabled_strategies else "21EMA Strategy"

    if not enabled_strategies:
        st.sidebar.warning("No strategy active. Enable at least one.", icon="⚠️")

    # ── Trading Symbol ────────────────────────────────────────────────────────
    # Instrument metadata: exchange symbol used by OpenAlgo + default lot size
    # (quantity per lot, as per the instrument's current contract specs).
    instrument_meta: dict[str, dict[str, Any]] = {
        "Nifty50": {
            "symbol": "NSE:NIFTY-INDEX",
            "spot_symbol": "NIFTY",
            "option_index_symbol": "NIFTY",
            "exchange_spot": "NSE_INDEX",
            "exchange_options": "NFO",
            "strike_step": 50,
            "default_lot_size": 65,
            "weekly_expiry_weekday": 1,
        },
        "BankNifty": {
            "symbol": "NSE:BANKNIFTY-INDEX",
            "spot_symbol": "BANKNIFTY",
            "option_index_symbol": "BANKNIFTY",
            "exchange_spot": "NSE_INDEX",
            "exchange_options": "NFO",
            "strike_step": 100,
            "default_lot_size": 30,
            "weekly_expiry_weekday": 1,
        },
        "Sensex": {
            "symbol": "BSE:SENSEX-INDEX",
            "spot_symbol": "SENSEX",
            "option_index_symbol": "SENSEX",
            "exchange_spot": "BSE_INDEX",
            "exchange_options": "BFO",
            "strike_step": 100,
            "default_lot_size": 20,
            "weekly_expiry_weekday": 3,
        },
    }

    st.sidebar.markdown("### Trading Symbol")
    selected_instruments = st.sidebar.multiselect(
        "Trading Instruments",
        list(instrument_meta.keys()),
        default=st.session_state.get("selected_instruments", ["Nifty50"]),
        help="Select one or more instruments to trade.",
    )

    if not selected_instruments:
        st.sidebar.warning(
            "No instrument selected — defaulting to Nifty50.", icon="⚠️"
        )
        selected_instruments = ["Nifty50"]

    st.session_state.selected_instruments = selected_instruments

    # ── Lot Size (number of lots — quantity auto-scales per instrument) ─────
    st.sidebar.markdown("### Lot Size")
    if "lots" not in st.session_state:
        saved_lots = _load_dashboard_preferences().get("lots", 1)
        try:
            st.session_state.lots = max(1, min(1000, int(saved_lots)))
        except (TypeError, ValueError):
            st.session_state.lots = 1
    lots = int(
        st.sidebar.number_input(
            "Number of Lots",
            min_value=1,
            max_value=1000,
            step=1,
            key="lots",
            on_change=_save_lots_preference,
            help=(
                "Number of lots to trade. Quantity is auto-computed per "
                "instrument using its contract size "
                "(Nifty50 = 65, BankNifty = 30, Sensex = 20)."
            ),
        )
    )

    # Compute per-instrument quantity = lots × contract size.
    instrument_lot_sizes: dict[str, int] = {
        instr: int(instrument_meta[instr]["default_lot_size"])
        for instr in selected_instruments
    }
    instrument_quantities: dict[str, int] = {
        instr: lots * instrument_lot_sizes[instr] for instr in selected_instruments
    }

    # Live preview of the resulting quantities so the user can see the math.
    preview_lines = "".join(
        f"<div style='display:flex;justify-content:space-between;"
        f"padding:2px 0;color:#cfe6ff;font-size:0.86rem;'>"
        f"<span>{instr}</span>"
        f"<span><b>{lots} × {instrument_lot_sizes[instr]}</b> "
        f"= <b style='color:#59d0ff;'>{instrument_quantities[instr]}</b> qty</span>"
        f"</div>"
        for instr in selected_instruments
    )
    st.sidebar.markdown(
        f"<div style='margin-top:0.35rem;padding:0.55rem 0.7rem;"
        f"border:1px solid rgba(89,208,255,0.22);border-radius:8px;"
        f"background:rgba(12,26,40,0.55);'>{preview_lines}</div>",
        unsafe_allow_html=True,
    )

    # Primary instrument drives the live data feed and the active engine.
    primary_instrument = selected_instruments[0]
    primary_meta = instrument_meta[primary_instrument]
    openalgo_symbol = str(primary_meta["symbol"])
    primary_lot_size = instrument_lot_sizes[primary_instrument]

    # ── Broker Options ────────────────────────────────────────────────────────
    st.sidebar.markdown("### Broker Options")
    
    # OpenAlgo-first default: no manual source selection required.
    selected_source = "OPENALGO"
    st.sidebar.caption("Data Source: OPENALGO (default)")
    
    product_type = "INTRADAY"
    st.sidebar.caption("Order Product Type: INTRADAY")

    # ── OpenAlgo endpoint (env-only; edit .env to change) ────────────────────
    openalgo_base_url = (
        os.getenv("OPENALGO_BASE_URL")
        or os.getenv("OPENALGO_HOST", "http://host.docker.internal:5002")
    )
    openalgo_api_key = os.getenv("OPENALGO_API_KEY", "")
    openalgo_resolution = 3
    openalgo_days = 5

    source = selected_source

    source_params = {
        "csv_path": os.getenv("CSV_PATH", str(DEFAULT_CSV)),
        "openalgo_base_url": openalgo_base_url,
        "openalgo_api_key": openalgo_api_key,
        "openalgo_symbol": openalgo_symbol,
        "openalgo_resolution": int(openalgo_resolution),
        "openalgo_days": int(openalgo_days),
        "product_type": product_type,
        "active_strategy": active_strategy,
        "selected_strategy": enabled_strategies,
        "selected_instruments": selected_instruments,
        "primary_instrument": primary_instrument,
        "instrument_config": dict(primary_meta),
        "instrument_configs": {
            name: dict(metadata) for name, metadata in instrument_meta.items()
        },
        "instrument_lot_sizes": instrument_lot_sizes,
        "instrument_quantities": instrument_quantities,
        "lots": lots,
        "option_lot_size": primary_lot_size,
    }

    st.session_state.source = selected_source
    market_cfg = StrategyConfig()
    now_ist = datetime.now(DISPLAY_TZ).time()
    in_market_window = market_cfg.market_open <= now_ist < market_cfg.market_close

    def _log_market_pause_once() -> None:
        if in_market_window:
            return
        today_key = datetime.now(DISPLAY_TZ).date().isoformat()
        if st.session_state.get("_market_pause_logged_for") == today_key:
            return
        market_data_logs = st.session_state.get("market_data_logs") or []
        pause_row = {
            "timestamp": datetime.now(DISPLAY_TZ),
            "category": "SESSION",
            "status": "INFO",
            "symbol": openalgo_symbol,
            "entry_price": None,
            "exit_price": None,
            "trade_pnl": None,
            "message": (
                f"Market closed at {market_cfg.market_close.strftime('%H:%M')} IST — "
                f"polling paused until next session ({market_cfg.market_open.strftime('%H:%M')} IST)."
            ),
        }
        market_data_logs.append(pause_row)
        if len(market_data_logs) > 500:
            market_data_logs = market_data_logs[-500:]
        st.session_state.market_data_logs = market_data_logs
        st.session_state["_market_pause_logged_for"] = today_key

    # ── Auto-start engine: load OpenAlgo data on every rerun until it succeeds
    # ── so the app "just works" as soon as OpenAlgo is reachable. There is no
    # ── manual Start/Pause/Stop button any more.
    prev_params = st.session_state.get("source_params") or {}
    symbol_changed = prev_params.get("openalgo_symbol") != openalgo_symbol
    instruments_changed = (
        list(prev_params.get("selected_instruments") or [])
        != list(selected_instruments)
    )
    lot_config_changed = (
        int(prev_params.get("option_lot_size") or 0) != primary_lot_size
        or int(prev_params.get("lots") or 0) != lots
    )
    # Full reload only when the data feed itself must change (symbol switch or
    # first load). Lot / lot-size changes are applied live to the running
    # engine below so open positions and replay progress are preserved.
    need_reload = (
        "data" not in st.session_state
        or "runtime" not in st.session_state
        or st.session_state.get("source") != "OPENALGO"
        or symbol_changed
        or instruments_changed
    )
    if need_reload:
        try:
            _data = load_data("OPENALGO", source_params, StrategyConfig())
            init_engine_state(_data, "OPENALGO", source_params)
            for instrument_state in st.session_state.instrument_states.values():
                instrument_state["running"] = in_market_window
                instrument_state["engine_status"] = (
                    "running" if in_market_window else "paused"
                )
            if in_market_window:
                st.session_state.running = True
                st.session_state.engine_status = "running"
            else:
                st.session_state.running = False
                st.session_state.engine_status = "paused"
                _log_market_pause_once()
            st.session_state.pop("openalgo_unavailable", None)
        except (OpenAlgoError, RuntimeError, ValueError, FileNotFoundError) as exc:
            st.session_state.running = False
            st.session_state.engine_status = "stopped"
            msg = str(exc)
            lower_msg = msg.lower()
            if (
                "401" in msg
                or "403" in msg
                or "unauthorized" in lower_msg
                or ("invalid" in lower_msg and "apikey" in lower_msg)
            ):
                st.session_state["openalgo_unavailable"] = (
                    f"OpenAlgo rejected the API key for {openalgo_base_url}. "
                    f"Set OPENALGO_API_KEY in Trading_Setups/.env with your key "
                    f"from the OpenAlgo → API Key page, then restart the app."
                )
            elif not openalgo_api_key:
                st.session_state["openalgo_unavailable"] = (
                    f"OPENALGO_API_KEY is not set. Create Trading_Setups/.env with "
                    f"OPENALGO_API_KEY=<your key> and restart the app."
                )
            else:
                st.session_state["openalgo_unavailable"] = (
                    f"OpenAlgo is not reachable at {openalgo_base_url}. "
                    f"Please start OpenAlgo and refresh this page. ({exc})"
                )
    else:
        enabled_keys = [
            definition.key
            for definition in STRATEGY_DEFINITIONS
            if definition.label in enabled_strategies
        ]
        instrument_states = st.session_state.get("instrument_states", {})
        for instrument, instrument_state in instrument_states.items():
            runtime = instrument_state["runtime"]
            runtime.set_enabled(enabled_keys or ["hd"])
            instrument_state["engines"] = runtime.engines
            selected_key = runtime.active_keys[0]
            instrument_state["engine"] = runtime.engines[selected_key]
            instrument_state["source_params"]["selected_strategy"] = enabled_strategies
            instrument_state["source_params"]["lots"] = lots
            instrument_state["source_params"]["option_lot_size"] = int(
                (instrument_lot_sizes or {}).get(instrument, primary_lot_size)
            )
            _apply_lot_config_to_cfg(
                instrument_state["cfg"],
                lots,
                instrument_state["source_params"]["option_lot_size"],
            )
            if in_market_window:
                _set_primary_instrument_aliases(instrument_state)
                sync_openalgo_data(
                    instrument_state["source_params"], instrument_state["cfg"]
                )
                for key in (
                    "data", "index", "option_data", "equity_curve",
                    "last_candle_processed_at",
                ):
                    if key in st.session_state:
                        instrument_state[key] = st.session_state[key]
                instrument_state["running"] = True
                instrument_state["engine_status"] = "running"
            else:
                instrument_state["running"] = False
                instrument_state["engine_status"] = "paused"

        if not in_market_window:
            _log_market_pause_once()
        if instrument_states:
            _set_primary_instrument_aliases(next(iter(instrument_states.values())))

    # Keep source_params in session in sync every rerun so downstream code
    # (order placement, autorefresh) always reads the latest lot config.
    st.session_state.source_params = source_params

    if st.session_state.get("openalgo_unavailable"):
        st.sidebar.error(st.session_state["openalgo_unavailable"], icon="⚠️")

    background_worker_enabled = os.getenv("BACKGROUND_WORKER_ENABLED", "false").lower() == "true"
    if st.session_state.get("running") and not background_worker_enabled:
        has_engine_state = all(
            key in st.session_state for key in ("data", "engine", "broker", "index")
        )
        if has_engine_state:
            process_next_candle()
        else:
            st.session_state.running = False
            st.session_state.engine_status = "stopped"

    return source_params

