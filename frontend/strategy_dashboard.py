"""Multi-page Streamlit trading dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

FRONTEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FRONTEND_DIR.parent
for import_path in (FRONTEND_DIR, PROJECT_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

st.set_page_config(
    page_title="Trading Setups",
    page_icon=":material/candlestick_chart:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

pages = st.navigation(
    [
        st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/dashboard:"),
        st.Page(
            "app_pages/positions.py",
            title="Positions",
            icon=":material/account_balance_wallet:",
        ),
        st.Page("app_pages/orderbook.py", title="Orderbook", icon=":material/receipt_long:"),
        st.Page("app_pages/analytics.py", title="Analytics", icon=":material/bar_chart:"),
        st.Page("app_pages/logs.py", title="Logs", icon=":material/terminal:"),
    ],
    position="top",
)

pages.run()
