"""Orderbook page — history of all orders placed this session."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from _shared import (
    inject_theme,
    refresh_live_account_metrics,
    render_section_heading,
    render_sidebar,
)
from core.engine import BaseStrategyEngine

inject_theme()
source_params = render_sidebar()
st_autorefresh(interval=10_000, key="orderbook-live-refresh")
refresh_live_account_metrics(source_params)

st.markdown(
    """
    <style>
    .ob-card {
        border: 1px solid rgba(86, 184, 222, 0.28);
        border-radius: 16px;
        background: rgba(12, 20, 38, 0.55);
        padding: 1.1rem 1.2rem;
        min-height: 118px;
    }
    .ob-card-label {
        color: #8e9cb0;
        font-size: 0.82rem;
        font-weight: 650;
        margin-bottom: 0.55rem;
    }
    .ob-card-value {
        font-size: 2.1rem;
        font-weight: 800;
        line-height: 1;
    }
    .ob-empty {
        border: 1px solid rgba(86, 184, 222, 0.28);
        border-radius: 18px;
        background: rgba(12, 20, 38, 0.55);
        min-height: 240px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #96a3b8;
        font-size: 1.08rem;
        font-weight: 600;
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

engine: BaseStrategyEngine | None = st.session_state.get("engine")
orders_today_df = pd.DataFrame(columns=["Timestamp", "Category", "Order info"])

if engine is not None:
    orders = [
        a for a in engine.alerts if str(a.category).upper() in {"ORDER", "ENTRY", "EXIT", "SL", "REJECT"}
    ]
    if orders:
        orders_today_df = pd.DataFrame(
            [
                {
                    "Timestamp": a.timestamp,
                    "Category": str(a.category).upper(),
                    "Order info": a.message,
                }
                for a in orders
            ]
        )
        orders_today_df["Timestamp"] = pd.to_datetime(orders_today_df["Timestamp"], errors="coerce")

        trading_day = None
        snapshot = engine.get_status_snapshot()
        trading_day = snapshot.get("trading_day")
        if trading_day is not None:
            day = pd.to_datetime(trading_day, errors="coerce")
            if pd.notna(day):
                orders_today_df = orders_today_df[
                    orders_today_df["Timestamp"].dt.date == day.date()
                ]

orders_count = len(orders_today_df)
completed_count = len(
    orders_today_df[orders_today_df["Category"].isin(["ENTRY", "EXIT", "ORDER", "SL"])]
)
rejected_count = len(orders_today_df[orders_today_df["Category"].isin(["REJECT", "ERROR"])])

open_count = 0
if engine is not None:
    snap = engine.get_status_snapshot()
    if snap.get("position") is not None or snap.get("pending_entry") is not None:
        open_count = 1

cards = st.columns(4)
cards_data = [
    ("Orders", str(orders_count), "#edf4ff"),
    ("Completed", str(completed_count), "#15c46b"),
    ("Currently open", str(open_count), "#2f7bff"),
    ("Rejected", str(rejected_count), "#ff7a7a"),
]

for card, (label, value, color) in zip(cards, cards_data):
    with card:
        st.markdown(
            f"""
            <div class='ob-card'>
                <div class='ob-card-label'>{label}</div>
                <div class='ob-card-value' style='color:{color};'>{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:0.9rem;'></div>", unsafe_allow_html=True)

with st.container(border=True):
    render_section_heading(
        "Execution log",
        "Trades executed today",
        "All trades executed during the current trading day.",
    )

    if engine is None:
        st.markdown("<div class='ob-empty'>Engine not started yet</div>", unsafe_allow_html=True)
    elif orders_today_df.empty:
        st.markdown("<div class='ob-empty'>No orders today</div>", unsafe_allow_html=True)
    else:
        st.dataframe(
            orders_today_df.sort_values("Timestamp", ascending=False),
            hide_index=True,
            use_container_width=True,
        )

# ── Live broker orderbook (from OpenAlgo, works in Paper Mode too) ───────────
st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
with st.container(border=True):
    render_section_heading(
        "Live orderbook",
        "Orders from your broker",
        "Fetched live from OpenAlgo — reflects your actual broker orderbook.",
    )

    live_error = st.session_state.get("live_account_error")
    live_orders = st.session_state.get("live_orders") or []
    updated_at = st.session_state.get("live_account_updated_at")

    if live_error:
        st.warning(f"Live account: {live_error}", icon="⚠️")
    elif not live_orders:
        st.markdown(
            "<div class='ob-empty'>No orders in broker orderbook</div>",
            unsafe_allow_html=True,
        )
    else:
        df_live = pd.DataFrame(live_orders).rename(
            columns={
                "order_id": "Order ID",
                "symbol": "Symbol",
                "exchange": "Exchange",
                "action": "Side",
                "quantity": "Qty",
                "price": "Price",
                "trigger_price": "Trigger",
                "product": "Product",
                "order_type": "Type",
                "status": "Status",
                "timestamp": "Time",
            }
        )
        st.dataframe(df_live, hide_index=True, use_container_width=True)
        if updated_at:
            st.caption(f"Synced from OpenAlgo at {updated_at}")
