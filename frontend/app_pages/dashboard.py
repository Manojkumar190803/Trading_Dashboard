"""Dashboard page — live metrics overview and P&L trend."""
from __future__ import annotations

import streamlit as st
from _shared import (
    inject_theme,
    refresh_live_account_metrics,
    render_alert_toasts,
    render_section_heading,
    render_sidebar,
    run_premarket_checks,
)

inject_theme()
source_params = render_sidebar()

# ── Live account refresh (works in Paper Mode too — read-only) ────────────────
refresh_live_account_metrics(source_params)
render_alert_toasts()

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
            <div style='color:#59d0ff;text-transform:uppercase;letter-spacing:.14em;font-size:.7rem;font-weight:800;margin-bottom:.25rem;'>Live control room</div>
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
            <div class='hd-metric-value-v2' style='color:{mtm_color};'>₹{net_mtm:,.0f}</div>
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

# ── Pre-market readiness (kept in the sidebar so the main dashboard stays clear)
if "premarket_checks" not in st.session_state:
    st.session_state.premarket_checks = run_premarket_checks(source_params)
    st.session_state.premarket_checked_at = updated_at or "now"

checks = st.session_state.get("premarket_checks", [])
ready_count = sum(check["status"] == "READY" for check in checks)
failed_count = sum(check["status"] == "FAILED" for check in checks)
overall = "READY" if checks and failed_count == 0 else "ACTION REQUIRED"
overall_color = "#27d48a" if overall == "READY" else "#ffbe32"

st.sidebar.markdown("---")
st.sidebar.markdown("**Pre-Market Readiness**")
st.sidebar.markdown(
    f"<div style='color:{overall_color};font-weight:800;font-size:.82rem;'>"
    f"{overall} · {ready_count}/{len(checks)} passed</div>",
    unsafe_allow_html=True,
)
st.sidebar.caption(f"Checked: {st.session_state.get('premarket_checked_at', 'not checked')}")
if st.sidebar.button("Run checks", key="sidebar_run_premarket_checks", use_container_width=True):
    progress = st.sidebar.empty()

    def _show_check_progress(updated_checks: list[dict[str, str]]) -> None:
        completed = len(updated_checks)
        rows = "".join(
            f"<div style='padding:.35rem 0;border-bottom:1px solid rgba(86,184,222,.10);'>"
            f"<strong style='color:{'#27d48a' if check['status'] == 'READY' else '#ffbe32' if check['status'] == 'WARNING' else '#ff5f6d'};'>"
            f"{check['status']}</strong><br><span style='font-size:.75rem;'>{check['name']}</span></div>"
            for check in updated_checks
        )
        progress.markdown(
            f"<div style='margin:.65rem 0;color:#a9b8c9;font-size:.78rem;'>"
            f"Checking one by one: {completed}/6 complete</div>{rows}",
            unsafe_allow_html=True,
        )

    _show_check_progress([])
    st.session_state.premarket_checks = run_premarket_checks(
        source_params,
        on_check=_show_check_progress,
    )
    st.session_state.premarket_checked_at = updated_at or "now"
    st.rerun()

with st.sidebar.expander("View check details", expanded=False):
    for check in checks:
        status_color = {"READY": "#27d48a", "WARNING": "#ffbe32", "FAILED": "#ff5f6d"}.get(
            check["status"], "#8899aa"
        )
        st.markdown(
            f"<div style='padding:.2rem 0;border-bottom:1px solid rgba(86,184,222,.10);'>"
            f"<strong style='color:{status_color};'>{check['status']}</strong><br>"
            f"<span style='font-size:.75rem;'>{check['name']}</span></div>",
            unsafe_allow_html=True,
        )
