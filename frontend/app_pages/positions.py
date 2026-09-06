"""Positions page — open position and pending entry order."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from _shared import (
    format_money,
    inject_theme,
    refresh_live_account_metrics,
    render_sidebar,
)
inject_theme()
source_params = render_sidebar()
st_autorefresh(interval=10_000, key="positions-live-refresh")
refresh_live_account_metrics(source_params)

st.markdown(
    """
    <style>
    .pos-card {
        border: 1px solid rgba(86, 184, 222, 0.28);
        border-radius: 16px;
        background: rgba(12, 20, 38, 0.55);
        padding: 1.1rem 1.2rem;
        min-height: 124px;
    }
    .pos-card-label {
        color: #8e9cb0;
        font-size: 0.82rem;
        font-weight: 650;
        margin-bottom: 0.55rem;
    }
    .pos-card-value {
        color: #edf4ff;
        font-size: 1.55rem;
        font-weight: 800;
        line-height: 1.2;
        word-break: break-word;
    }
    .pos-page-title {
        text-align: center;
        font-size: 2.4rem;
        font-weight: 800;
        color: #f2f8ff;
        letter-spacing: 0.2px;
        margin: 0.25rem 0 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

engine = st.session_state.get("engine")
snapshot = engine.get_status_snapshot() if engine is not None else {}
position = snapshot.get("position") if snapshot else None

open_positions = 1 if position else 0

total_pnl = float(snapshot.get("total_pnl", 0.0)) if snapshot else 0.0
total_pnl_color = "#15c46b" if total_pnl >= 0 else "#ff7a7a"

source_params = st.session_state.get("source_params", {})
configured_strategy = source_params.get("active_strategy", "HD Strategy")
triggered = bool(
    snapshot
    and (
        snapshot.get("pending_entry") is not None
        or snapshot.get("position") is not None
        or int(snapshot.get("trades_taken", 0)) > 0
    )
)
current_strategy = configured_strategy if triggered else "None"

running_position = "None"
if position:
    running_position = (
        f"{position.get('option_symbol', 'N/A')} "
        f"({position.get('option_type', 'N/A')}) x{position.get('quantity', 'N/A')}"
    )

st.markdown("<div class='pos-page-title'>Positions</div>", unsafe_allow_html=True)

cards = st.columns(4)
cards_data = [
    ("Open position", str(open_positions), "#edf4ff"),
    ("Current Strategy Triggered", str(current_strategy), "#59d0ff"),
    ("Total P&L", f"{format_money(total_pnl)}", total_pnl_color),
    ("Current positions running", running_position, "#ffd58f"),
]

for card, (label, value, color) in zip(cards, cards_data):
    with card:
        st.markdown(
            f"""
            <div class='pos-card'>
                <div class='pos-card-label'>{label}</div>
                <div class='pos-card-value' style='color:{color};'>{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ── Live positions from OpenAlgo (read-only, works in Paper Mode too) ────────
st.markdown("<div style='height:1.1rem;'></div>", unsafe_allow_html=True)
st.markdown(
    "<div style='font-size:1.15rem;font-weight:800;color:#e8f4ff;margin-bottom:0.5rem;'>"
    "Live broker positions"
    "</div>",
    unsafe_allow_html=True,
)

live_error = st.session_state.get("live_account_error")
live_positions = st.session_state.get("live_positions") or []
updated_at = st.session_state.get("live_account_updated_at")

if live_error:
    st.warning(f"Live account: {live_error}", icon="⚠️")
elif not live_positions:
    st.info("No open positions in your broker account.")
else:
    df_live = pd.DataFrame(live_positions)
    df_live = df_live.rename(
        columns={
            "symbol": "Symbol",
            "exchange": "Exchange",
            "product": "Product",
            "quantity": "Qty",
            "avg_price": "Avg Price",
            "ltp": "LTP",
            "pnl": "P&L",
        }
    )
    st.dataframe(df_live, hide_index=True, use_container_width=True)
    if updated_at:
        st.caption(f"Synced from OpenAlgo at {updated_at}")
