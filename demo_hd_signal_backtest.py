"""Signal-only historical trace for the HD strategy using OpenAlgo data."""

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
    "spot_ema13",
    "spot_ema20",
    "spot_ema50",
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
    for ema in (13, 20, 50):
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
        ("spot_ema13", "spot_ema13"),
        ("spot_ema20", "spot_ema20"),
        ("spot_ema50", "spot_ema50"),
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
    """Print a terminal-only timeline of HD rules evaluated on NIFTY spot."""
    print("HD NIFTY SPOT RULE CHECK (DIAGNOSTIC ONLY; NOT OPTION-PARITY BACKTEST)")
    rows = results.to_dict("records")
    labels = {
        "RSI_CROSS_BELOW_20": "RSI CROSS",
        "ALERT_CANDLE": "ALERT OK",
        "NEXT_CANDLE_REJECTED": "REJECTED",
        "SIGNAL_FILTERED_TREND": "TREND FLT",
        "SIGNAL": "SIGNAL",
    }
    for row in rows:
        row["rule"] = labels.get(row.get("event"), row.get("event", "-"))
        row["time_short"] = (row.get("time") or "-")[:5]
        row["spot_short"] = f"{row['spot_close']:.1f}" if row.get("spot_close") is not None else "-"
        row["rsi_short"] = f"{row['rsi3']:.1f}" if row.get("rsi3") is not None else "-"
        row["trend_short"] = {
            "BULLISH": "BULL",
            "BEARISH": "BEAR",
            "AMBIGUOUS": "AMBIG",
        }.get(row.get("trend"), "-")
        row["result_short"] = {
            "WAIT FOR NEXT SPOT CANDLE": "WAIT NEXT",
            "ALERT CANDLE OK": "ALERT OK",
            "SETUP REJECTED": "SETUP REJ",
            "FILTERED BY SPOT TREND": "TREND FLT",
            "SPOT RULE SIGNAL": "SPOT SIGNAL",
            "AFTER ENTRY CUTOFF": "AFTER CUTOFF",
        }.get(row.get("result"), row.get("result", "-"))
    _print_table(
        "SPOT SIGNAL RULE TIMELINE",
        rows,
        [
            ("DATE", "date", 10),
            ("TIME", "time_short", 5),
            ("RULE", "rule", 9),
            ("SD", "side", 3),
            ("SPOT", "spot_short", 7),
            ("RSI3", "rsi_short", 5),
            ("TREND", "trend_short", 6),
            ("RESULT", "result_short", 11),
        ],
    )
    if results.empty or not (results["event"] == "SIGNAL").any():
        print("\nNo HD setup signal was generated on the spot candles in this date range.")
    signals = results[results["event"] == "SIGNAL"]
    if not signals.empty:
        _print_table(
            "SPOT SIGNAL LEVELS (INDEX POINTS)",
            signals.to_dict("records"),
            [
                ("TIME", "time", 8),
                ("SIDE", "side", 4),
                ("TRIGGER", "spot_trigger", 9),
                ("STOP", "stop_level", 9),
                ("RISK", "spot_risk_points", 8),
                ("RESULT", "result", 18),
            ],
        )
    print("\nSpot uses index points; live HD calculates RSI and alert candles on options.")


def trace_spot_rules(
    candles: pd.DataFrame,
    provider: HDSignalProvider,
    cfg: StrategyConfig,
) -> list[dict[str, Any]]:
    """Evaluate the HD rule sequence against spot candles for diagnosis only."""
    events: list[dict[str, Any]] = []
    side_state = provider.create_side_state()
    previous: Optional[pd.Series] = None

    for _, row in candles.iterrows():
        was_setup_pending = side_state.setup_pending
        previous_rsi = None if previous is None else _as_float(previous.get("rsi3"))
        current_rsi = _as_float(row.get("rsi3"))

        provider.update_state(side_state, row, previous)
        trend = provider._market_trend(row)
        side = "CE" if trend == "BULLISH" else "PE" if trend == "BEARISH" else "-"

        if previous_rsi is not None and current_rsi is not None and previous_rsi >= 20 and current_rsi < 20:
            events.append(_event_row(
                "RSI_CROSS_BELOW_20",
                side,
                row,
                f"RSI(3) crossed below 20 from {previous_rsi:.2f} to {current_rsi:.2f}; waiting for next candle",
                trend=trend,
                result="WAIT FOR NEXT SPOT CANDLE",
            ))

        if was_setup_pending:
            if side_state.alert_ready:
                events.append(_event_row(
                    "ALERT_CANDLE",
                    side,
                    row,
                    "Next spot candle passed the green strong-body/hammer check",
                    trend=trend,
                    result="ALERT CANDLE OK",
                ))
            else:
                events.append(_event_row(
                    "NEXT_CANDLE_REJECTED",
                    side,
                    row,
                    "Next spot candle did not pass the HD alert-candle check",
                    trend=trend,
                    result="SETUP REJECTED",
                ))

        signal = Signal.NONE
        if trend == "BULLISH":
            signal = provider.generate_signal("CE", side_state, row, previous)
        elif trend == "BEARISH":
            signal = provider.generate_signal("PE", side_state, row, previous)
        if side_state.alert_ready and signal is Signal.NONE:
            events.append(_event_row(
                "SIGNAL_FILTERED_TREND",
                side,
                row,
                f"Alert candle passed, but spot trend is {trend}",
                trend=trend,
                result="FILTERED BY SPOT TREND",
            ))
        elif signal is not Signal.NONE:
            trigger = float(row["high"])
            stop = provider.compute_stop_level(side_state, row)
            risk_points = trigger - stop
            timestamp = pd.Timestamp(row["datetime"])
            if timestamp.time() >= cfg.entry_cutoff:
                result = "AFTER ENTRY CUTOFF"
            else:
                result = "SPOT RULE SIGNAL"
            events.append(_event_row(
                "SIGNAL",
                side,
                row,
                f"{signal.value} on spot; marker=alert candle high, stop=alert candle low",
                trend=trend,
                spot_trigger=trigger,
                stop_level=stop,
                spot_risk_points=risk_points,
                result=result,
            ))

        previous = row

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
    spot_history = _normalize_history_df(broker.fetch_history(
        cfg.spot_symbol,
        cfg.exchange_spot,
        interval,
        warmup_start,
        end_text,
    ))
    if spot_history.empty:
        raise RuntimeError("OpenAlgo returned no NIFTY spot history for this range")

    events: list[dict[str, Any]] = []
    trading_days = [
        day for day in _iter_trading_days(spot_history)
        if start_date <= day <= end_date
    ]
    for day in trading_days:
        spot_day = _warmup_and_slice(spot_history, day, cfg)
        if spot_day.empty:
            events.append(_event_row("DAY_SKIPPED", "-", None, "No spot candles in the monitoring window", date=day.isoformat()))
            continue

        lock_timestamp = datetime.combine(day, cfg.atm_lock_time)
        signal_day = spot_day[spot_day["datetime"] >= lock_timestamp].reset_index(drop=True)
        if signal_day.empty:
            events.append(_event_row("DAY_SKIPPED", "-", None, "No spot candles at or after the HD start time", date=day.isoformat()))
            continue

        spot_candles = _prepare_spot_candles(signal_day)
        events.extend(trace_spot_rules(spot_candles, HDSignalProvider(), cfg))

    if not events:
        events.append(_event_row("NO_EVENTS", "-", None, "No trading days found in the requested range"))

    results = pd.DataFrame(events)
    for column in OUTPUT_COLUMNS:
        if column not in results.columns:
            results[column] = None
    results = results[OUTPUT_COLUMNS]
    return results


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check HD signal rules on NIFTY spot history; prints only, no option data or files.")
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
    results = run_backtest(args.start_date, args.end_date, cfg, broker)

    print_spot_report(results)
    print(f"\nSignal rows: {(results['event'] == 'SIGNAL').sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())