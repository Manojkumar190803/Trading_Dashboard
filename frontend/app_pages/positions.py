"""Positions page — open position and pending entry order."""
from __future__ import annotations

from html import escape

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
        border: 1px solid rgba(89, 208, 255, .25);
        border-radius: 14px;
        background: linear-gradient(145deg, rgba(19, 43, 55, .92), rgba(9, 24, 34, .82));
        padding: 1rem 1.05rem;
        min-height: 108px;
        box-shadow: 0 12px 28px rgba(0, 0, 0, .14);
        position: relative;
        overflow: hidden;
    }
    .pos-card::after { content: ''; position: absolute; left: 0; top: 0; width: 100%; height: 3px; background: var(--pos-color, #59d0ff); }
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
        font-size: 1.55rem;
        font-weight: 800;
        color: #f2f8ff;
        margin: .35rem 0 .2rem;
    }
    .pos-page-subtitle { color: #a9c2cc; font-size: .86rem; margin-bottom: 1rem; }
    .pos-table { overflow-x: auto; border: 1px solid rgba(89, 208, 255, .3); border-radius: 14px; background: rgba(5, 16, 24, .6); }
    .pos-table table { width: 100%; min-width: 760px; border-collapse: collapse; font-size: .8rem; }
    .pos-table th { color: #8fa9b4; background: rgba(26, 34, 47, .96); text-align: left; font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; padding: .72rem .65rem; }
    .pos-table td { color: #e5f4f8; border-top: 1px solid rgba(126, 168, 180, .13); padding: .72rem .65rem; white-space: nowrap; }
    .pos-symbol { color: #f0fbff; font-weight: 750; }
    .pos-table tr.pos-profit td { background: rgba(39, 212, 138, .10); }
    .pos-table tr.pos-loss td { background: rgba(255, 95, 109, .11); }
    .pos-table tr.pos-neutral td { background: rgba(255, 190, 50, .12); }
    .pos-table tr:hover td { background: rgba(89, 208, 255, .12); }
    .pos-pnl-positive { color: #54e2a4; font-weight: 800; }
    .pos-pnl-negative { color: #ff8a92; font-weight: 800; }
    .pos-pnl-neutral { color: #ffd166; font-weight: 800; }
    </style>
    """,
    unsafe_allow_html=True,
)

engine = st.session_state.get("engine")
snapshot = engine.get_status_snapshot() if engine is not None else {}
position = snapshot.get("position") if snapshot else None
live_positions = st.session_state.get("live_positions") or []


def _position_quantity(row: dict[str, object]) -> int:
    try:
        return int(float(row.get("quantity", row.get("qty", 0)) or 0))
    except (TypeError, ValueError):
        return 0


def _contract_size(symbol: str) -> int:
    symbol_upper = symbol.upper()
    if symbol_upper.startswith("BANKNIFTY"):
        return 30
    if symbol_upper.startswith("SENSEX"):
        return 20
    if symbol_upper.startswith("NIFTY"):
        return 65
    return 1


def _position_table_rows(positions: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for position_row in positions:
        row = dict(position_row)
        symbol = str(row.get("symbol") or row.get("tradingsymbol") or "")
        quantity = _position_quantity(row)
        contract_size = _contract_size(symbol)
        row["lots"] = quantity // contract_size if contract_size > 1 else quantity
        if contract_size > 1 and quantity % contract_size:
            row["lots"] = f"{quantity / contract_size:.2f}"
        rows.append(row)
    return rows


broker_open_positions = [
    row for row in live_positions if _position_quantity(row) != 0
]

open_positions = 1 if position else len(broker_open_positions)

if snapshot and (snapshot.get("position") or snapshot.get("pending_entry")):
    total_pnl = float(snapshot.get("total_pnl", 0.0))
else:
    total_pnl = float(st.session_state.get("net_mtm", 0.0) or 0.0)
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
current_strategy = configured_strategy if triggered or broker_open_positions else "None"

running_position = "None"
if position:
    running_position = (
        f"{position.get('option_symbol', 'N/A')} "
        f"({position.get('option_type', 'N/A')}) x{position.get('quantity', 'N/A')}"
    )
elif broker_open_positions:
    broker_symbols = []
    for row in broker_open_positions:
        symbol = str(row.get("symbol") or row.get("tradingsymbol") or "N/A")
        quantity = _position_quantity(row)
        broker_symbols.append(f"{symbol} x{quantity}")
    running_position = ", ".join(broker_symbols)

st.markdown(
    """
    <div class='pos-page-title'>Positions</div>
    <div class='pos-page-subtitle'>Live exposure, broker quantities, and running mark-to-market from OpenAlgo.</div>
    """,
    unsafe_allow_html=True,
)

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
            <div class='pos-card' style='--pos-color:{color};'>
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
updated_at = st.session_state.get("live_account_updated_at")

if live_error:
    st.warning(f"Live account: {live_error}", icon="⚠️")
elif not live_positions:
    st.info("No open positions in your broker account.")
else:
    position_rows = _position_table_rows(live_positions)
    df_live = pd.DataFrame(position_rows)
    df_live = df_live.rename(
        columns={
            "symbol": "Symbol",
            "exchange": "Exchange",
            "product": "Product",
            "quantity": "Qty",
            "avg_price": "Avg Price",
            "ltp": "LTP",
            "pnl": "P&L",
            "lot_size": "Broker Lot Size",
            "lots": "Lots",
        }
    )
    table_rows = []
    for _, row in df_live.iterrows():
        pnl = float(row.get("P&L", 0) or 0)
        if pnl > 0.005:
            row_class, pnl_class = "pos-profit", "pos-pnl-positive"
        elif pnl < -0.005:
            row_class, pnl_class = "pos-loss", "pos-pnl-negative"
        else:
            row_class, pnl_class = "pos-neutral", "pos-pnl-neutral"
        table_rows.append(
            f"<tr class='{row_class}'>"
            f"<td class='pos-symbol'>{escape(str(row.get('Symbol', '-')))}</td>"
            f"<td>{escape(str(row.get('Exchange', '-')))}</td>"
            f"<td>{escape(str(row.get('Product', '-')))}</td>"
            f"<td>{escape(str(row.get('Qty', 0)))}</td>"
            f"<td>{escape(str(row.get('Lots', 0)))}</td>"
            f"<td>{escape(str(row.get('Avg Price', 0)))}</td>"
            f"<td>{escape(str(row.get('LTP', 0)))}</td>"
            f"<td class='{pnl_class}'>{escape(str(row.get('P&L', 0)))}</td>"
            "</tr>"
        )
    st.markdown(
        "<div class='pos-table'><table><thead><tr>"
        "<th>Symbol</th><th>Exchange</th><th>Product</th><th>Qty</th><th>Lots</th>"
        "<th>Avg Price</th><th>LTP</th><th>P&amp;L</th>"
        f"</tr></thead><tbody>{''.join(table_rows)}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    if updated_at:
        st.caption(f"Synced from OpenAlgo at {updated_at}")
