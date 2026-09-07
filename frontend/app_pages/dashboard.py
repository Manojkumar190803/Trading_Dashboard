"""Dashboard page — live metrics overview and P&L trend."""
from __future__ import annotations

import streamlit as st
from _shared import (
    inject_theme,
    refresh_live_account_metrics,
    render_section_heading,
    render_sidebar,
)

inject_theme()
source_params = render_sidebar()

# ── Live account refresh (works in Paper Mode too — read-only) ────────────────
refresh_live_account_metrics(source_params)

# ── Header + status badge ─────────────────────────────────────────────────────
net_mtm        = st.session_state.get("net_mtm", 0.0)
engine_status  = st.session_state.get("engine_status", "stopped")
active_trades  = st.session_state.get("active_trades", 0)
avail_margin   = st.session_state.get("available_margin", 0.0)
live_error     = st.session_state.get("live_account_error")
updated_at     = st.session_state.get("live_account_updated_at")

status_colors = {"running": "#27d48a", "paused": "#ffbe32", "stopped": "#8899aa"}
dot_color     = status_colors.get(engine_status, "#8899aa")
mtm_color     = "#27d48a" if net_mtm >= 0 else "#ff5f6d"

st.html(
    f"""
    <div class='hd-dashboard-header'>
        <div class='hd-header-left'>
            <h1 class='hd-dashboard-title'>Trading Dashboard</h1>
            <p class='hd-dashboard-subtitle'>Live overview of your trading account and market positions</p>
        </div>
        <div class='hd-header-right'>
            <div class='hd-status-badge'>
                <span class='hd-status-dot' style='background:{dot_color};'></span>
                <span class='hd-status-text'>Engine: {engine_status.title()}</span>
            </div>
        </div>
    </div>

    <div class='hd-metrics-grid'>
        <div class='hd-metric-card-v2'>
            <div class='hd-metric-label-v2'>Net MTM (₹)</div>
            <div class='hd-metric-value-v2' style='color:{mtm_color};'>₹{abs(net_mtm):,.0f}</div>
            <div class='hd-metric-sublabel'>Mark to Market</div>
        </div>
        <div class='hd-metric-card-v2'>
            <div class='hd-metric-label-v2'>Available Margin</div>
            <div class='hd-metric-value-v2' style='color:#59d0ff;'>₹{avail_margin:,.0f}</div>
            <div class='hd-metric-sublabel'>Buying Power</div>
        </div>
        <div class='hd-metric-card-v2'>
            <div class='hd-metric-label-v2'>Active Trades</div>
            <div class='hd-metric-value-v2' style='color:#ffd700;'>{active_trades}</div>
            <div class='hd-metric-sublabel'>Open Positions</div>
        </div>
        <div class='hd-metric-card-v2'>
            <div class='hd-metric-label-v2'>Strategy</div>
            <div class='hd-metric-value-v2' style='color:#b8e6aa;'>Active</div>
            <div class='hd-metric-sublabel'>Ready for Trade</div>
        </div>
    </div>
    """
)

# ── Live account status caption ───────────────────────────────────────────────
if live_error:
    st.warning(f"Live account: {live_error}", icon="⚠️")
elif updated_at:
    st.caption(f"Live account syncing every 10s · Last updated: {updated_at}")
