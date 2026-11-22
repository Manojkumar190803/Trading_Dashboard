"""Spot-based HD signal diagnostic using historical OpenAlgo data."""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
import textwrap
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

from core.broker import OpenAlgoBroker
from core.models import Signal, StrategyConfig
from core.runner import (
    _iter_trading_days,
    _normalize_history_df,
    _warmup_and_slice,
)
from strategies.hd import HDSignalProvider


OUTPUT_COLUMNS = [
    "date",
    "time",
    "event",
    "side",
    "spot_open",
    "spot_high",
    "spot_low",
    "spot_close",
    "rsi3",
    "rsi_value",
    "spot_ema13",
    "spot_ema20",
    "spot_ema50",
    "spot_ema100",
    "spot_ema200",
    "trend",
    "spot_trigger",
    "stop_level",
    "spot_risk_points",
    "result",
    "detail",
]


def _as_float(value: Any) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _prepare_spot_candles(spot_df: pd.DataFrame) -> pd.DataFrame:
    candles = spot_df.copy()
    for ema in (13, 20, 50, 100, 200):
        source = f"ema{ema}"
        if source not in candles:
            candles[source] = candles["close"].ewm(span=ema, adjust=False).mean()
        candles[f"spot_ema{ema}"] = candles[f"ema{ema}"]
    return candles


def _event_row(
    event: str,
    side: str,
    row: Optional[pd.Series],
    detail: str,
    **extra: Any,
) -> dict[str, Any]:
    timestamp = None if row is None else pd.Timestamp(row["datetime"])
    record: dict[str, Any] = {
        "date": timestamp.date().isoformat() if timestamp is not None else None,
        "time": timestamp.strftime("%H:%M:%S") if timestamp is not None else None,
        "event": event,
        "side": side,
        "detail": detail,
    }
    for source, target in (
        ("open", "spot_open"),
        ("high", "spot_high"),
        ("low", "spot_low"),
        ("close", "spot_close"),
        ("rsi3", "rsi3"),
        ("rsi3", "rsi_value"),
        ("spot_ema13", "spot_ema13"),
        ("spot_ema20", "spot_ema20"),
        ("spot_ema50", "spot_ema50"),
        ("spot_ema100", "spot_ema100"),
        ("spot_ema200", "spot_ema200"),
    ):
        record[target] = None if row is None else _as_float(row.get(source))
    record.update(extra)
    return record


def _table_text(value: Any, width: int) -> str:
    if value is None or pd.isna(value):
        text = "-"
    elif isinstance(value, float):
        text = f"{value:.2f}"
    else:
        text = str(value)
    return text if len(text) <= width else text[: width - 3] + "..."


def _print_table(title: str, rows: list[dict[str, Any]], columns: list[tuple[str, str, int]]) -> None:
    print(f"\n{title}")
    if not rows:
        print("  No rows.")
        return
    widths = [max(len(label), width) for label, _, width in columns]
    header = " | ".join(label.ljust(widths[index]) for index, (label, _, _) in enumerate(columns))
    separator = "-+-".join("-" * width for width in widths)
    print(header)
    print(separator)
    for row in rows:
        print(" | ".join(
            _table_text(row.get(key), widths[index]).ljust(widths[index])
            for index, (_, key, _) in enumerate(columns)
        ))


def print_spot_report(results: pd.DataFrame) -> None:
    """Print every RSI dip attempt and whether it became an HD signal."""
    print("HD SIGNAL ATTEMPTS (SPOT DIAGNOSTIC; NOT OPTION-PARITY BACKTEST)")
    if results.empty:
        print("No RSI(3) dips occurred in this date range.")
        print("\nSpot uses index points; live HD calculates RSI and alert candles on options.")
        return
    _print_table(
        "HD SIGNAL RESULTS",
        results.to_dict("records"),
        [
            ("DATE", "date", 10),
            ("TIME", "time", 8),
            ("RSI DIP", "rsi_value", 8),
            ("EMA13", "spot_ema13", 9),
            ("EMA20", "spot_ema20", 9),
            ("EMA50", "spot_ema50", 9),
            ("EMA100", "spot_ema100", 10),
            ("EMA200", "spot_ema200", 10),
            ("CLOSE", "spot_close", 10),
            ("SIDE", "side", 4),
            ("RESULT", "result", 16),
        ],
    )
    print("\nSpot uses index points; live HD calculates RSI and alert candles on options.")


def _valid_signal_rows(results: pd.DataFrame) -> pd.DataFrame:
    required_columns = {"event", "result", "side"}
    if results.empty or not required_columns.issubset(results.columns):
        return results.iloc[0:0]
    valid = (
        results["event"].eq("SIGNAL")
        & results["result"].eq("HD CAME")
        & results["side"].isin(("CE", "PE"))
    )
    return results.loc[valid].reset_index(drop=True)


def trace_spot_rules(
    candles: pd.DataFrame,
    provider: HDSignalProvider,
    cfg: StrategyConfig,
) -> list[dict[str, Any]]:
    """Report each RSI dip after evaluating its immediately following candle."""
    events: list[dict[str, Any]] = []
    side_state = provider.create_side_state()
    previous: Optional[pd.Series] = None

    for _, row in candles.iterrows():
        was_setup_pending = side_state.setup_pending
        provider.update_state(side_state, row, previous)
        trend = provider._market_trend(row)
        side = "CE" if trend == "BULLISH" else "PE" if trend == "BEARISH" else "-"

        signal = Signal.NONE
        if trend == "BULLISH":
            signal = provider.generate_signal("CE", side_state, row, previous)
        elif trend == "BEARISH":
            signal = provider.generate_signal("PE", side_state, row, previous)
        timestamp = pd.Timestamp(row["datetime"])
        if was_setup_pending:
            hd_came = signal is not Signal.NONE and timestamp.time() < cfg.entry_cutoff
            dip_rsi = None if previous is None else _as_float(previous.get("rsi3"))
            extra: dict[str, Any] = {
                "trend": trend,
                "rsi_value": dip_rsi,
                "result": "HD CAME" if hd_came else "HD DID NOT COME",
            }
            if hd_came:
                trigger = float(row["high"])
                stop = provider.compute_stop_level(side_state, row)
                extra.update(
                    spot_trigger=trigger,
                    stop_level=stop,
                    spot_risk_points=trigger - stop,
                )
            events.append(_event_row(
                "SIGNAL" if hd_came else "SETUP_ATTEMPT",
                side,
                row,
                (
                    f"{signal.value} on spot"
                    if hd_came
                    else "RSI dip was not followed by a valid in-window HD signal"
                ),
                **extra,
            ))

        previous = row

    if side_state.setup_pending and previous is not None:
        trend = provider._market_trend(previous)
        side = "CE" if trend == "BULLISH" else "PE" if trend == "BEARISH" else "-"
        events.append(_event_row(
            "SETUP_ATTEMPT",
            side,
            previous,
            "No following candle was available to confirm the RSI dip",
            trend=trend,
            rsi_value=_as_float(previous.get("rsi3")),
            result="HD DID NOT COME",
        ))

    return events


def _parse_time(value: str) -> time:
    return time.fromisoformat(value)


def _build_config(args: argparse.Namespace) -> StrategyConfig:
    monitoring_start = _parse_time(os.getenv("HD_MONITORING_START_TIME", "09:15"))
    monitoring_end = _parse_time(os.getenv("HD_MONITORING_END_TIME", "15:30"))
    entry_cutoff = _parse_time(args.entry_cutoff)
    if monitoring_start >= monitoring_end:
        raise ValueError("monitoring start must be earlier than monitoring end")
    if not monitoring_start <= entry_cutoff <= monitoring_end:
        raise ValueError("entry cutoff must be within the monitoring window")

    return StrategyConfig(
        spot_symbol=args.spot_symbol,
        option_index_symbol=args.spot_symbol,
        timeframe_minutes=args.timeframe,
        exchange_spot=args.exchange_spot,
        market_open=monitoring_start,
        market_close=monitoring_end,
        atm_lock_time=max(time(9, 20), monitoring_start),
        entry_cutoff=entry_cutoff,
    )


def run_backtest(
    start_date: date,
    end_date: date,
    cfg: StrategyConfig,
    broker: OpenAlgoBroker,
) -> pd.DataFrame:
    interval = f"{cfg.timeframe_minutes}m"
    warmup_start = (start_date - timedelta(days=10)).isoformat()
    end_text = end_date.isoformat()
    spot_history = _normalize_history_df(
        broker.fetch_history(
            cfg.spot_symbol,
            cfg.exchange_spot,
            interval,
            warmup_start,
            end_text,
        )
    ).sort_values("datetime").reset_index(drop=True)
    if spot_history.empty:
        raise RuntimeError("OpenAlgo returned no NIFTY spot history for this range")
    for ema in (100, 200):
        spot_history[f"ema{ema}"] = spot_history["close"].ewm(
            span=ema,
            adjust=False,
        ).mean()

    events: list[dict[str, Any]] = []
    trading_days = [
        day for day in _iter_trading_days(spot_history)
        if start_date <= day <= end_date and day.weekday() < 5
    ]
    for day in trading_days:
        spot_day = _warmup_and_slice(spot_history, day, cfg)
        if spot_day.empty:
            continue

        lock_timestamp = datetime.combine(day, cfg.atm_lock_time)
        signal_day = spot_day[spot_day["datetime"] >= lock_timestamp].reset_index(drop=True)
        if signal_day.empty:
            continue

        spot_candles = _prepare_spot_candles(signal_day)
        events.extend(trace_spot_rules(spot_candles, HDSignalProvider(), cfg))

    results = pd.DataFrame(events)
    for column in OUTPUT_COLUMNS:
        if column not in results.columns:
            results[column] = None
    results = results[OUTPUT_COLUMNS]
    return results


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print HD signal-attempt results from NIFTY spot history."
    )
    parser.add_argument("--start-date", required=True, type=date.fromisoformat, help="First trading date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, type=date.fromisoformat, help="Last trading date (YYYY-MM-DD)")
    parser.add_argument("--spot-symbol", default="NIFTY")
    parser.add_argument("--exchange-spot", default="NSE_INDEX")
    parser.add_argument("--timeframe", type=int, default=3, help="Candle interval in minutes")
    parser.add_argument("--entry-cutoff", default=os.getenv("HD_ENTRY_CUTOFF", "14:40"))
    return parser


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    load_dotenv(project_dir / ".env")
    args = _argument_parser().parse_args()
    if args.start_date > args.end_date:
        raise SystemExit("--start-date must be on or before --end-date")
    if args.timeframe <= 0:
        raise SystemExit("--timeframe must be positive")

    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        raise SystemExit("OPENALGO_API_KEY is not set in the environment or .env")
    host = os.getenv("OPENALGO_HOST") or os.getenv("OPENALGO_URL") or "http://127.0.0.1:5002"
    cfg = _build_config(args)
    broker = OpenAlgoBroker(api_key=api_key, host=host, dry_run=True)
    print(
        f"Fetching {cfg.spot_symbol} {cfg.timeframe_minutes}m candles from OpenAlgo "
        f"for {args.start_date} through {args.end_date}...",
        flush=True,
    )
    results = run_backtest(
        args.start_date,
        args.end_date,
        cfg,
        broker,
    )

    print_spot_report(results)
    print(f"\nSignal rows: {(results['event'] == 'SIGNAL').sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())