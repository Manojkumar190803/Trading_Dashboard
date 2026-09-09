"""Orderbook page — history of all orders placed this session."""
from __future__ import annotations

from html import escape
import re

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from _shared import (
    LOGS_DIR,
    OpenAlgoAccountClient,
    OpenAlgoConfig,
    OpenAlgoError,
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
        border: 1px solid rgba(89, 208, 255, 0.25);
        border-radius: 14px;
        background: linear-gradient(145deg, rgba(19, 43, 55, 0.92), rgba(9, 24, 34, 0.82));
        padding: 1rem 1.05rem;
        min-height: 104px;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.14);
        position: relative;
        overflow: hidden;
    }
    .ob-card::after {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        width: 100%;
        height: 3px;
        background: var(--ob-color, #59d0ff);
        opacity: .85;
    }
    .ob-card-label {
        color: #8e9cb0;
        font-size: 0.82rem;
        font-weight: 650;
        margin-bottom: 0.55rem;
    }
    .ob-card-value {
        font-size: 2rem;
        font-weight: 800;
        line-height: 1;
    }
    .ob-hero {
        border: 1px solid rgba(89, 208, 255, .24);
        border-radius: 18px;
        padding: 1.2rem 1.35rem;
        margin: .3rem 0 1.1rem;
        background: linear-gradient(110deg, rgba(18, 57, 70, .9), rgba(12, 29, 40, .62));
        box-shadow: 0 16px 36px rgba(0, 0, 0, .16);
    }
    .ob-hero-kicker { color: #59d0ff; text-transform: uppercase; letter-spacing: .14em; font-size: .7rem; font-weight: 800; }
    .ob-hero-title { color: #edfaff; font-size: 1.55rem; font-weight: 800; margin-top: .25rem; }
    .ob-hero-copy { color: #a9c2cc; font-size: .86rem; margin-top: .25rem; }
    .ob-live-table { overflow-x: auto; border: 1px solid rgba(89, 208, 255, .3); border-radius: 14px; background: rgba(5, 16, 24, .6); }
    .ob-live-table table { width: 100%; min-width: 920px; border-collapse: collapse; font-size: .78rem; }
    .ob-live-table th { color: #8fa9b4; background: rgba(26, 34, 47, .96); text-align: left; font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; padding: .72rem .65rem; white-space: nowrap; }
    .ob-live-table td { color: #e5f4f8; border-top: 1px solid rgba(126, 168, 180, .13); padding: .7rem .65rem; white-space: nowrap; }
    .ob-live-table tr:hover td { background: rgba(89, 208, 255, .06); }
    .ob-live-table tr.ob-open td { background: rgba(39, 212, 138, .055); }
    .ob-action-cell { text-align: right; width: 48px; }
    .ob-cancel-hint { color: #91aab4; font-size: .72rem; }
    div[data-testid="stButton"] > button {
        min-height: 2rem; min-width: 2.5rem; width: 2.5rem; padding: 0; border-radius: 7px;
        border: 1px solid rgba(255, 95, 109, .7) !important; color: #ffb0b6 !important;
        background: rgba(255, 95, 109, .16) !important; font-size: .72rem; font-weight: 800;
    }
    div[data-testid="stButton"] > button p { color: inherit !important; white-space: nowrap !important; overflow: visible !important; }
    div[data-testid="stButton"] > button:hover {
        color: #fff; border-color: #ff7d87; background: rgba(255, 95, 109, .28);
    }
    div[data-testid="stHorizontalBlock"] div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stHorizontalBlock"] div[data-testid="stMarkdownContainer"] span {
        white-space: nowrap !important;
        word-break: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    div[data-testid="stHorizontalBlock"] { align-items: center; }
    .ob-order-scroll { width: 100%; padding: .2rem 0 .55rem; }
    .ob-row-label { color: #7f9aa7; font-size: .64rem; text-transform: uppercase; letter-spacing: .06em; }
    .ob-row-value { color: #e8f7fb; font-size: .78rem; font-weight: 650; line-height: 1.35; white-space: nowrap; }
    .ob-row-subvalue { color: #91aab4; font-size: .68rem; line-height: 1.35; white-space: nowrap; }
    .ob-row-open { border-left: 3px solid #54e2a4; padding-left: .55rem; }
    .ob-row-terminal { border-left: 3px solid rgba(126, 168, 180, .28); padding-left: .55rem; }
    .ob-action-label { color: #7f9aa7; font-size: .62rem; text-transform: uppercase; letter-spacing: .06em; text-align: center; }
    div[data-testid="stButton"] > button:disabled {
        color: #8aa0aa !important; border-color: rgba(138, 160, 170, .35) !important;
        background: rgba(96, 121, 133, .12) !important; opacity: .85;
    }
    .ob-symbol { display: block; font-size: .72rem; font-weight: 750; color: #f0fbff; white-space: nowrap; }
    .ob-muted { color: #91aab4; }
    .ob-pill { display: inline-block; border-radius: 999px; padding: .2rem .48rem; font-size: .68rem; font-weight: 800; letter-spacing: .02em; }
    .ob-buy { color: #07251a; background: #27d48a; }
    .ob-sell { color: #351316; background: #ff8a92; }
    .ob-open-pill { color: #06291c; background: #54e2a4; }
    .ob-complete-pill { color: #bceeff; background: rgba(89, 208, 255, .18); }
    .ob-cancel-pill, .ob-reject-pill { color: #ffd5d8; background: rgba(255, 95, 109, .16); }
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

st.markdown(
    """
    <div class="ob-hero">
        <div class="ob-hero-kicker">Broker execution monitor</div>
        <div class="ob-hero-title">Order Book</div>
        <div class="ob-hero-copy">Watch every trigger, fill, cancellation, and rejection from OpenAlgo in one place.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

engine: BaseStrategyEngine | None = st.session_state.get("engine")
orders_today_df = pd.DataFrame(columns=["Timestamp", "Category", "Order info", "P&L"])


def _normalize_live_orders(raw_orders: list[dict[str, object]]) -> pd.DataFrame:
    """Normalize OpenAlgo orderbook variants to the fields shown by its UI."""
    rows: list[dict[str, object]] = []
    for order in raw_orders:
        action = str(order.get("action") or order.get("side") or "").upper()
        status = str(
            order.get("order_status")
            or order.get("status")
            or order.get("orderStatus")
            or ""
        ).upper()
        rows.append(
            {
                "Symbol": order.get("symbol") or order.get("tradingsymbol") or "-",
                "Exchange": order.get("exchange") or "-",
                "Action": action or "-",
                "Qty": order.get("quantity") or order.get("qty") or 0,
                "Price": order.get("price") or order.get("limit_price") or 0,
                "Trigger": order.get("trigger_price") or order.get("trigger") or 0,
                "Type": order.get("price_type") or order.get("pricetype") or order.get("order_type") or "-",
                "Product": order.get("product") or order.get("product_type") or "-",
                "Order ID": order.get("order_id") or order.get("orderid") or "-",
                "Status": status.title() if status else "-",
                "Time": order.get("timestamp") or order.get("order_timestamp") or order.get("time") or "-",
            }
        )
    return pd.DataFrame(rows, columns=[
        "Symbol", "Exchange", "Action", "Qty", "Price", "Trigger",
        "Type", "Product", "Order ID", "Status", "Time",
    ])


def _order_status(value: object) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _message_pnl(message: object) -> float | None:
    match = re.search(r"trade_pnl=([\-0-9]+(?:\.[0-9]+)?)", str(message or ""), flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _live_order_table(df: pd.DataFrame) -> str:
    headers = ["Symbol", "Exchange", "Action", "Qty", "Price", "Trigger", "Type", "Product", "Order ID", "Status", "Time"]
    body: list[str] = []
    for _, row in df.iterrows():
        status_key = _order_status(row["Status"])
        status_class = (
            "ob-open-pill" if status_key not in terminal_statuses else
            "ob-complete-pill" if status_key in {"complete", "completed", "filled", "executed"} else
            "ob-cancel-pill"
        )
        action = str(row["Action"])
        action_class = "ob-buy" if action == "BUY" else "ob-sell" if action == "SELL" else "ob-complete-pill"
        row_class = "ob-open" if status_key not in terminal_statuses else ""
        cells = [
            f'<span class="ob-symbol">{escape(str(row["Symbol"]))}</span>',
            f'<span class="ob-muted">{escape(str(row["Exchange"]))}</span>',
            f'<span class="ob-pill {action_class}">{escape(action)}</span>',
            escape(str(row["Qty"])), escape(str(row["Price"])), escape(str(row["Trigger"])),
            escape(str(row["Type"])), escape(str(row["Product"])), escape(str(row["Order ID"])),
            f'<span class="ob-pill {status_class}">{escape(str(row["Status"]))}</span>',
            escape(str(row["Time"])),
        ]
        body.append(f'<tr class="{row_class}">' + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    heading = "".join(f"<th>{escape(header)}</th>" for header in headers)
    return f'<div class="ob-live-table"><table><thead><tr>{heading}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def _cancellable_order(row: pd.Series) -> bool:
    return bool(
        str(row.get("Order ID") or "-") not in {"", "-"}
        and _order_status(row.get("Status")) not in terminal_statuses
    )


def _render_live_order_rows(df: pd.DataFrame, source_params: dict[str, object]) -> None:
    """Render readable broker rows with a real cancel control in its own column."""
    headers = ["Instrument", "Trade details", "Broker order", "Status / time", ""]
    widths = [2.45, 2.15, 1.65, 1.55, .72]
    st.markdown("<div class='ob-order-scroll'>", unsafe_allow_html=True)
    header = st.columns(widths)
    for column, label in zip(header, headers):
        column.markdown(f"<div class='ob-row-label'>{escape(label)}</div>", unsafe_allow_html=True)
    for index, (_, row) in enumerate(df.iterrows()):
        status_key = _order_status(row["Status"])
        action = str(row["Action"])
        action_class = "ob-buy" if action == "BUY" else "ob-sell" if action == "SELL" else "ob-complete-pill"
        status_class = (
            "ob-open-pill" if status_key not in terminal_statuses else
            "ob-complete-pill" if status_key in {"complete", "completed", "filled", "executed"} else
            "ob-cancel-pill"
        )
        row_class = "ob-row-open" if status_key not in terminal_statuses else "ob-row-terminal"
        values = [
            f"<div class='{row_class}'><div class='ob-row-value'>{escape(str(row['Symbol']))}</div><div class='ob-row-subvalue'>{escape(str(row['Exchange']))}</div></div>",
            f"<div><span class='ob-pill {action_class}'>{escape(action)}</span><div class='ob-row-subvalue'>Qty {escape(str(row['Qty']))} &middot; {escape(str(row['Type']))} &middot; {escape(str(row['Product']))}</div><div class='ob-row-subvalue'>Price {escape(str(row['Price']))} &middot; Trigger {escape(str(row['Trigger']))}</div></div>",
            f"<div class='ob-row-value'>{escape(str(row['Order ID']))}</div>",
            f"<div><span class='ob-pill {status_class}'>{escape(str(row['Status']))}</span><div class='ob-row-subvalue'>{escape(str(row['Time']))}</div></div>",
        ]
        cells = st.columns(widths)
        for cell, value in zip(cells[:-1], values):
            cell.markdown(value, unsafe_allow_html=True)
        if _cancellable_order(row):
            if cells[-1].button("X", key=f"cancel-order-{row['Order ID']}-{index}", help="Cancel this broker order"):
                params = source_params or st.session_state.get("source_params", {}) or {}
                try:
                    client = OpenAlgoAccountClient(OpenAlgoConfig(
                        base_url=str(params.get("openalgo_base_url") or "http://host.docker.internal:5002"),
                        api_key=str(params.get("openalgo_api_key") or ""),
                        product_type=str(params.get("product_type") or "INTRADAY"),
                    ))
                    if not client.cancel_order(str(row["Order ID"])):
                        st.error("OpenAlgo did not accept the cancellation.")
                    else:
                        st.session_state["_live_refresh_last_ts"] = None
                        st.success(f"Order {row['Order ID']} cancellation requested.")
                        st.rerun()
                except OpenAlgoError as exc:
                    st.error(str(exc))
        else:
            cells[-1].button(
                "X",
                key=f"cancel-order-disabled-{row['Order ID']}-{index}",
                help="This order is already complete or cancelled",
                disabled=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


def _load_persisted_order_events() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    categories = {"ORDER", "ENTRY", "EXIT", "SL", "REJECT", "ERROR", "UNCERTAIN_ENTRY"}
    for path in sorted(LOGS_DIR.glob("trade_alerts_*.csv")):
        try:
            persisted = pd.read_csv(path)
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        if not {"timestamp", "category", "message"}.issubset(persisted.columns):
            continue
        for _, row in persisted.iterrows():
            category = str(row.get("category") or "").upper()
            if category not in categories:
                continue
            timestamp = pd.to_datetime(row.get("timestamp"), errors="coerce")
            if pd.isna(timestamp):
                continue
            rows.append({
                "Timestamp": timestamp,
                "Category": category,
                "Order info": str(row.get("message") or ""),
                "P&L": _message_pnl(row.get("message")),
            })
    return pd.DataFrame(rows, columns=["Timestamp", "Category", "Order info", "P&L"])

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
                    "P&L": _message_pnl(a.message),
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

persisted_orders_df = _load_persisted_order_events()
if not persisted_orders_df.empty:
    persisted_orders_df = persisted_orders_df[
        persisted_orders_df["Timestamp"].dt.date == pd.Timestamp.now().date()
    ]
    orders_today_df = pd.concat([orders_today_df, persisted_orders_df], ignore_index=True)
    orders_today_df = orders_today_df.drop_duplicates(
        subset=["Timestamp", "Category", "Order info"], keep="last"
    )


def _execution_row_style(row: pd.Series) -> list[str]:
    pnl = row.get("P&L")
    try:
        value = float(pnl)
    except (TypeError, ValueError):
        return [""] * len(row)
    if value > 0.005:
        color = "rgba(39, 212, 138, .16)"
    elif value < -0.005:
        color = "rgba(255, 95, 109, .16)"
    else:
        color = "rgba(255, 190, 50, .16)"
    return [f"background-color: {color}"] * len(row)

live_orders = st.session_state.get("live_orders") or []
live_orders_df = _normalize_live_orders(live_orders)
terminal_statuses = {"complete", "completed", "filled", "executed", "cancelled", "rejected", "failed"}
live_statuses = live_orders_df["Status"].map(_order_status) if not live_orders_df.empty else pd.Series(dtype=str)
orders_count = len(live_orders_df)
buy_count = int((live_orders_df["Action"].str.upper() == "BUY").sum()) if not live_orders_df.empty else 0
sell_count = int((live_orders_df["Action"].str.upper() == "SELL").sum()) if not live_orders_df.empty else 0
completed_count = int(live_statuses.isin({"complete", "completed", "filled", "executed"}).sum())
rejected_count = int(live_statuses.isin({"rejected", "failed"}).sum())

open_count = int((~live_statuses.isin(terminal_statuses)).sum())

cards = st.columns(5)
cards_data = [
    ("Buy orders", str(buy_count), "#15c46b"),
    ("Sell orders", str(sell_count), "#ff7a7a"),
    ("Completed", str(completed_count), "#15c46b"),
    ("Open", str(open_count), "#2f7bff"),
    ("Rejected", str(rejected_count), "#ff7a7a"),
]

for card, (label, value, color) in zip(cards, cards_data):
    with card:
        st.markdown(
            f"""
            <div class='ob-card' style='--ob-color:{color};'>
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
            orders_today_df.sort_values("Timestamp", ascending=False).style.apply(
                _execution_row_style, axis=1
            ),
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
    updated_at = st.session_state.get("live_account_updated_at")

    if live_error:
        st.warning(f"Live account: {live_error}", icon="⚠️")
    elif not live_orders:
        st.markdown(
            "<div class='ob-empty'>No orders in broker orderbook</div>",
            unsafe_allow_html=True,
        )
    else:
        _render_live_order_rows(live_orders_df, source_params)
        if updated_at:
            st.caption(f"● Live sync · OpenAlgo · {updated_at}")
