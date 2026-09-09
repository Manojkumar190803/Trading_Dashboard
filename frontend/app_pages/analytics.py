"""Analytics page — equity curve and underlying spot charts."""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from _shared import inject_theme, render_section_heading, render_sidebar

inject_theme()
render_sidebar()

st.markdown(
    """
    <style>
    .analytics-hero { border:1px solid rgba(89,208,255,.24); border-radius:18px; padding:1.2rem 1.35rem; margin:.3rem 0 1.1rem; background:linear-gradient(110deg,rgba(18,57,70,.9),rgba(12,29,40,.62)); box-shadow:0 16px 36px rgba(0,0,0,.16); }
    .analytics-kicker { color:#59d0ff; text-transform:uppercase; letter-spacing:.14em; font-size:.7rem; font-weight:800; }
    .analytics-title { color:#edfaff; font-size:1.55rem; font-weight:800; margin-top:.25rem; }
    .analytics-copy { color:#a9c2cc; font-size:.86rem; margin-top:.25rem; }
    </style>
    <div class="analytics-hero">
        <div class="analytics-kicker">Performance intelligence</div>
        <div class="analytics-title">Analytics</div>
        <div class="analytics-copy">Read the session through expectancy, risk, equity movement, and strategy quality.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

equity_curve = st.session_state.get("equity_curve", [])
engine = st.session_state.get("engine")


def _load_persisted_alerts() -> list[dict[str, str]]:
    source_params = st.session_state.get("source_params", {}) or {}
    instrument = str(source_params.get("option_index_symbol") or "NIFTY").upper()
    path = Path("logs") / f"trade_alerts_{instrument}_{date.today():%Y%m%d}.csv"
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return [row for row in csv.DictReader(handle) if row.get("message")]
    except (OSError, csv.Error):
        return []


persisted_alerts = _load_persisted_alerts()


def _extract_trade_pnls() -> list[float]:
    pnls: list[float] = []
    alerts = (
        [
            {"category": str(alert.category), "message": str(alert.message)}
            for alert in engine.alerts
        ]
        if engine is not None
        else []
    )
    alerts.extend(persisted_alerts)
    seen: set[tuple[str, str]] = set()
    for alert in alerts:
        category = str(alert.get("category") or "").upper()
        message = str(alert.get("message") or "")
        key = (category, message)
        if key in seen or category != "EXIT":
            continue
        seen.add(key)
        match = re.search(r"trade_pnl=([\-0-9]+(?:\.[0-9]+)?)", message, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            pnls.append(float(match.group(1)))
        except (TypeError, ValueError):
            continue
    return pnls


trade_pnls = _extract_trade_pnls()
completed_trades = len(trade_pnls)
gross_profit = sum(p for p in trade_pnls if p > 0)
gross_loss_abs = abs(sum(p for p in trade_pnls if p < 0))
winning_trades = sum(1 for p in trade_pnls if p > 0)
expectancy = (sum(trade_pnls) / completed_trades) if completed_trades else 0.0
win_rate = ((winning_trades / completed_trades) * 100.0) if completed_trades else 0.0
profit_factor = (gross_profit / gross_loss_abs) if gross_loss_abs > 0 else (float("inf") if gross_profit > 0 else 0.0)

factor_display = "∞" if profit_factor == float("inf") else f"{profit_factor:.2f}"
expectancy_color = "normal" if expectancy >= 0 else "inverse"
win_rate_delta = f"{winning_trades}/{completed_trades} wins" if completed_trades else "No completed trades"
factor_delta = (
    f"Gross +{gross_profit:,.2f} vs -{gross_loss_abs:,.2f}"
    if completed_trades
    else "No completed trades"
)


def _max_streak(values: list[float], winning: bool) -> int:
    best = 0
    current = 0
    for value in values:
        is_match = value > 0 if winning else value < 0
        if is_match:
            current += 1
            if current > best:
                best = current
        else:
            current = 0
    return best


longest_win_streak = _max_streak(trade_pnls, winning=True)
longest_loss_streak = _max_streak(trade_pnls, winning=False)

snapshot = engine.get_status_snapshot() if engine is not None else {}
position = snapshot.get("position") if snapshot else None

base_capital = float(st.session_state.get("available_margin", 100000.0) or 100000.0)
exposure = 0.0
exposure_pct = 0.0
if position is not None:
    qty = float(position.get("quantity", 0) or 0)
    entry_price = float(position.get("entry_price", 0) or 0)
    exposure = qty * entry_price
    if base_capital > 0:
        exposure_pct = (exposure / base_capital) * 100.0

max_drawdown_pct = 0.0
sharpe_ratio = 0.0
if equity_curve:
    curve_df = pd.DataFrame(equity_curve).sort_values("datetime")
    equity_series = base_capital + curve_df["total_pnl"].astype(float)
    rolling_peak = equity_series.cummax()
    drawdown = ((equity_series - rolling_peak) / rolling_peak.replace(0, pd.NA)).fillna(0.0)
    max_drawdown_pct = abs(float(drawdown.min()) * 100.0)

    pnl_returns = curve_df["total_pnl"].astype(float).diff().dropna()
    if len(pnl_returns) > 1 and float(pnl_returns.std(ddof=1)) > 0:
        sharpe_ratio = float((pnl_returns.mean() / pnl_returns.std(ddof=1)) * (len(pnl_returns) ** 0.5))


def _strategy_tracking_df() -> pd.DataFrame:
    source_params = st.session_state.get("source_params", {})
    active_strategy = str(source_params.get("active_strategy", "HD Strategy"))

    strategy_enabled = st.session_state.get("strategy_enabled", {})
    strategy_list = [str(name) for name in strategy_enabled.keys()] or [active_strategy]
    if active_strategy not in strategy_list:
        strategy_list.append(active_strategy)

    entry_alerts = [
        row for row in persisted_alerts
        if str(row.get("category") or "").upper() == "ENTRY"
    ]
    if engine is not None:
        entry_alerts.extend(
            {"category": str(a.category), "message": str(a.message)}
            for a in engine.alerts
            if str(a.category).upper() == "ENTRY"
        )
    entry_alerts = list({str(row.get("message") or "") for row in entry_alerts})

    triggers_for_active = len(entry_alerts)
    wins_for_active = sum(1 for pnl in trade_pnls if pnl > 0)
    yield_for_active = float(sum(trade_pnls))

    rows: list[dict] = []
    for strategy_name in strategy_list:
        if strategy_name == active_strategy:
            triggers = triggers_for_active
            strat_yield = yield_for_active
            wins = wins_for_active
        else:
            triggers = 0
            strat_yield = 0.0
            wins = 0

        accuracy = (wins / triggers * 100.0) if triggers else 0.0
        rows.append(
            {
                "Strategy": strategy_name,
                "Triggers": int(triggers),
                "Yield": float(strat_yield),
                "Accuracy %": float(accuracy),
                "Wins": int(wins),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["Rank"] = (
            df["Yield"].rank(method="dense", ascending=False).astype(int)
        )
        df = df.sort_values(["Rank", "Yield", "Triggers"], ascending=[True, False, False])
    return df


strategy_df = _strategy_tracking_df()

with st.container(border=True):
    render_section_heading(
        "Performance",
        "Performance analytics",
        "Curve, expectancy, win-rate, and profit factor for the full trading session.",
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Expectancy", f"₹ {expectancy:,.2f}", delta=f"Across {completed_trades} trades", delta_color=expectancy_color)
    m2.metric("Win-rate", f"{win_rate:.2f}%", delta=win_rate_delta)
    m3.metric("Factor", factor_display, delta=factor_delta)
    m4.metric("Completed trades", str(completed_trades))

    if not equity_curve:
        st.info(
            "No analytics data yet. Start the engine and process some candles.",
            icon=":material/bar_chart:",
        )
    else:
        curve = pd.DataFrame(equity_curve).set_index("datetime")
        st.markdown("##### Cumulative P&L curve")
        st.line_chart(curve[["total_pnl"]], use_container_width=True, height=320)

with st.container(border=True):
    render_section_heading(
        "Risk",
        "Risk analytics",
        "Drawdowns, streaks, Sharpe, and live capital exposure.",
    )

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Drawdowns", f"{max_drawdown_pct:.2f}%", delta="Max peak-to-trough drop")
    r2.metric("Streaks", f"W {longest_win_streak} / L {longest_loss_streak}", delta="Longest win/loss run")
    r3.metric("Sharpe", f"{sharpe_ratio:.2f}", delta="Return adjusted for volatility")
    r4.metric("Exposure", f"₹ {exposure:,.2f}", delta=f"{exposure_pct:.2f}% capital deployed")

with st.container(border=True):
    render_section_heading(
        "Strategy tracking",
        "Strategy tracking dashboard",
        "Triggers, yield, accuracy, leaderboard, and distribution by strategy.",
    )

    if strategy_df.empty:
        st.info("No strategy tracking data yet.", icon=":material/tune:")
    else:
        st.dataframe(
            strategy_df[["Rank", "Strategy", "Triggers", "Yield", "Accuracy %"]],
            hide_index=True,
            use_container_width=True,
        )

        top_strategy = str(strategy_df.iloc[0]["Strategy"])
        top_yield = float(strategy_df.iloc[0]["Yield"])
        total_triggers = int(strategy_df["Triggers"].sum())

        s1, s2, s3 = st.columns(3)
        s1.metric("Leaderboard", top_strategy)
        s2.metric("Best yield", f"₹ {top_yield:,.2f}")
        s3.metric("Total triggers", str(total_triggers))

        dist_cols = st.columns(2)
        with dist_cols[0]:
            st.markdown("##### Distribution: trade triggers by strategy")
            trigger_dist = strategy_df.set_index("Strategy")[["Triggers"]]
            st.bar_chart(trigger_dist, use_container_width=True, height=260)

        with dist_cols[1]:
            st.markdown("##### Distribution: net yield by strategy")
            yield_dist = strategy_df.set_index("Strategy")[["Yield"]]
            st.bar_chart(yield_dist, use_container_width=True, height=260)

# ── Raw data table ─────────────────────────────────────────────────────────────
if equity_curve:
    with st.container(border=True):
        render_section_heading(
            "Raw data",
            "Session data table",
            "Every processed candle with its P&L snapshot.",
        )
        df = pd.DataFrame(equity_curve).sort_values("datetime", ascending=False)
        st.dataframe(df, hide_index=True, use_container_width=True)
