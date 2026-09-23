"""Analytics page — equity curve and underlying spot charts."""
from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from _shared import (
    inject_theme,
    refresh_live_account_metrics,
    render_section_heading,
    render_sidebar,
)

inject_theme()
source_params = render_sidebar()
refresh_live_account_metrics(source_params)

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

engine = st.session_state.get("engine")
ANALYTICS_TRADES_PATH = Path("logs") / "analytics_trades.csv"
ANALYTICS_RESET_PATH = Path("logs") / "analytics_reset.txt"
ANALYTICS_COLUMNS = ["timestamp", "strategy", "pnl", "source", "message"]

STRATEGY_LABELS = {
    "HDSignalProvider": "HD Strategy",
    "CDSignalProvider": "CD Strategy",
    "TCSignalProvider": "TC Strategy",
    "EMA21SignalProvider": "21EMA Strategy",
}


def _display_strategy_name(strategy: object) -> str:
    name = str(strategy or "").strip()
    return STRATEGY_LABELS.get(name, name or "Unknown")


def _extract_pnl(message: str) -> float | None:
    match = re.search(r"trade_pnl=([\-0-9]+(?:\.[0-9]+)?)", message, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def _load_alert_trades(since: str | None = None) -> list[dict[str, str]]:
    trades: list[dict[str, str]] = []
    for path in sorted(Path("logs").glob("trade_alerts_*.csv")):
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    timestamp = str(row.get("timestamp") or "")
                    if since and timestamp < since:
                        continue
                    message = str(row.get("message") or "")
                    if str(row.get("category") or "").upper() != "EXIT":
                        continue
                    pnl = _extract_pnl(message)
                    if pnl is None:
                        continue
                    trades.append({
                        "timestamp": timestamp,
                        "strategy": str(row.get("strategy") or "Unknown"),
                        "pnl": str(pnl),
                        "source": path.name,
                        "message": message,
                    })
        except (OSError, csv.Error):
            continue
    return trades


def _load_analytics_trades() -> pd.DataFrame:
    reset_at = None
    if ANALYTICS_RESET_PATH.exists():
        try:
            reset_at = ANALYTICS_RESET_PATH.read_text(encoding="utf-8").strip() or None
        except OSError:
            reset_at = None

    if not ANALYTICS_TRADES_PATH.exists():
        rows = _load_alert_trades(since=reset_at)
        ANALYTICS_TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=ANALYTICS_COLUMNS).to_csv(ANALYTICS_TRADES_PATH, index=False)
    try:
        trades = pd.read_csv(ANALYTICS_TRADES_PATH)
    except (OSError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=ANALYTICS_COLUMNS)
    for column in ANALYTICS_COLUMNS:
        if column not in trades:
            trades[column] = ""
    trades["pnl"] = pd.to_numeric(trades["pnl"], errors="coerce")
    trades = trades.dropna(subset=["pnl"])

    known_keys = set(zip(trades["timestamp"], trades["message"]))
    new_rows = [
        row for row in _load_alert_trades(since=reset_at)
        if (row["timestamp"], row["message"]) not in known_keys
    ]
    if new_rows:
        trades = pd.concat([trades, pd.DataFrame(new_rows, columns=ANALYTICS_COLUMNS)], ignore_index=True)
        trades.to_csv(ANALYTICS_TRADES_PATH, index=False)
    return trades.sort_values("timestamp")


analytics_trades = _load_analytics_trades()
trade_pnls = analytics_trades["pnl"].astype(float).tolist()
equity_curve: list[dict[str, object]] = []
running_pnl = 0.0
for _, trade in analytics_trades.iterrows():
    running_pnl += float(trade["pnl"])
    equity_curve.append({"datetime": trade["timestamp"], "total_pnl": running_pnl})
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

toolbar_left, toolbar_download, toolbar_reset = st.columns([5, 1, 1])
with toolbar_download:
    st.download_button(
        "Download CSV",
        data=analytics_trades[ANALYTICS_COLUMNS].to_csv(index=False),
        file_name="analytics_trades.csv",
        mime="text/csv",
        use_container_width=True,
    )
with toolbar_reset:
    if st.button("Reset data", use_container_width=True):
        pd.DataFrame(columns=ANALYTICS_COLUMNS).to_csv(ANALYTICS_TRADES_PATH, index=False)
        ANALYTICS_RESET_PATH.write_text(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            encoding="utf-8",
        )
        st.rerun()


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
    active_strategy = str(source_params.get("active_strategy", "21EMA Strategy"))

    strategy_list = [
        _display_strategy_name(name)
        for name in analytics_trades["strategy"].dropna().unique()
    ]
    if not strategy_list and active_strategy:
        strategy_list.append(_display_strategy_name(active_strategy))

    rows: list[dict] = []
    for strategy_name in strategy_list:
        strategy_trades = analytics_trades[
            analytics_trades["strategy"].map(_display_strategy_name) == strategy_name
        ]
        completed = len(strategy_trades)
        strat_yield = float(strategy_trades["pnl"].sum()) if completed else 0.0
        wins = int((strategy_trades["pnl"] > 0).sum())

        accuracy = (wins / completed * 100.0) if completed else 0.0
        rows.append(
            {
                "Strategy": strategy_name,
                "Completed trades": int(completed),
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
        df = df.sort_values(
            ["Rank", "Yield", "Completed trades"], ascending=[True, False, False]
        )
    return df


strategy_df = _strategy_tracking_df()

with st.container(border=True):
    render_section_heading(
        "Performance",
        "Performance analytics",
        "Historical realized P&L from completed strategy trades. Live broker P&L is shown separately.",
    )

    live_pnl = float(st.session_state.get("net_mtm", 0.0) or 0.0)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Expectancy", f"₹ {expectancy:,.2f}", delta=f"Across {completed_trades} trades", delta_color=expectancy_color)
    m2.metric("Win-rate", f"{win_rate:.2f}%", delta=win_rate_delta)
    m3.metric("Factor", factor_display, delta=factor_delta)
    m4.metric("Completed trades", str(completed_trades))
    m5.metric("Live broker P&L", f"₹ {live_pnl:,.2f}", delta="Current account MTM")

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
        "Completed trades, realized yield, accuracy, leaderboard, and distribution by strategy.",
    )

    if strategy_df.empty:
        st.info("No strategy tracking data yet.", icon=":material/tune:")
    else:
        st.dataframe(
            strategy_df[["Rank", "Strategy", "Completed trades", "Yield", "Accuracy %"]],
            hide_index=True,
            use_container_width=True,
        )

        top_strategy = str(strategy_df.iloc[0]["Strategy"])
        top_yield = float(strategy_df.iloc[0]["Yield"])
        total_completed = int(strategy_df["Completed trades"].sum())

        s1, s2, s3 = st.columns(3)
        s1.metric("Leaderboard", top_strategy)
        s2.metric("Best yield", f"₹ {top_yield:,.2f}")
        s3.metric("Total completed trades", str(total_completed))

        dist_cols = st.columns(2)
        with dist_cols[0]:
            st.markdown("##### Distribution: completed trades by strategy")
            completed_dist = strategy_df.set_index("Strategy")[["Completed trades"]]
            st.bar_chart(completed_dist, use_container_width=True, height=260)

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
