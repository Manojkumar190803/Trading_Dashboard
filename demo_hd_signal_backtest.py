"""HD-style spot-proxy diagnostic using historical OpenAlgo spot candles.

This diagnostic deliberately does not fetch option symbols or option history.
Its spot-based RSI results are proxies, not actual HD option signals.
"""

from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

from core.broker import OpenAlgoBroker
from core.indicators import add_indicators
from core.models import Signal, StrategyConfig
from core.runner import _iter_trading_days, _normalize_history_df
from strategies.hd import HDSignalProvider


OUTPUT_COLUMNS = [
    "date",
    "time",
    "event",
    "spot_symbol",
    "spot_open",
    "spot_high",
    "spot_low",
    "spot_close",
    "spot_rsi3",
    "rsi_dip",
    "spot_ema13",
    "spot_ema20",
    "spot_ema50",
    "trend",
    "entry_trigger",
    "entry_price",
    "quantity",
    "stop_loss",
    "trailing_stop",
    "exit_price",
    "max_rr_achieved",
    "exit_rr",
    "pnl_inr_proxy",
    "trade_status",
    "exit_time",
    "result",
    "detail",
]


def _as_float(value: Any) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _event_row(
    event: str,
    spot_symbol: str,
    row: Optional[pd.Series],
    detail: str,
    **extra: Any,
) -> dict[str, Any]:
    timestamp = None if row is None else pd.Timestamp(row["datetime"])
    record: dict[str, Any] = {
        "date": timestamp.date().isoformat() if timestamp is not None else None,
        "time": timestamp.strftime("%H:%M:%S") if timestamp is not None else None,
        "event": event,
        "spot_symbol": spot_symbol,
        "detail": detail,
    }
    for source, target in (
        ("open", "spot_open"),
        ("high", "spot_high"),
        ("low", "spot_low"),
        ("close", "spot_close"),
        ("rsi3", "spot_rsi3"),
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


def _print_table(
    title: str,
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str, int]],
) -> None:
    print(f"\n{title}")
    if not rows:
        print("  No rows.")
        return
    widths = [max(len(label), width) for label, _, width in columns]
    header = " | ".join(
        label.ljust(widths[index])
        for index, (label, _, _) in enumerate(columns)
    )
    separator = "-+-".join("-" * width for width in widths)
    print(header)
    print(separator)
    for row in rows:
        print(
            " | ".join(
                _table_text(row.get(key), widths[index]).ljust(widths[index])
                for index, (_, key, _) in enumerate(columns)
            )
        )


def print_proxy_report(results: pd.DataFrame) -> None:
    """Print spot-based HD-rule attempts, clearly labeled as proxy results."""
    print("HD-STYLE SPOT PROXY (NOT OPTION-CANDLE HD SIGNALS)")
    print("INR P&L is a spot-unit proxy, not actual option or broker P&L.")
    print(
        "MAX R is max favorable candle move / initial risk; "
        "EXIT R is realized move / initial risk."
    )
    print("Candle high/low order is unknown, so MAX R is an OHLC estimate.")
    if results.empty:
        print("No qualifying spot RSI(3) dips occurred in this date range.")
        return
    _print_table(
        "SPOT PROXY RESULTS",
        results.to_dict("records"),
        [
            ("DATE", "date", 10),
            ("TIME", "time", 8),
            ("RSI DIP", "rsi_dip", 8),
            ("EMA13", "spot_ema13", 9),
            ("EMA20", "spot_ema20", 9),
            ("EMA50", "spot_ema50", 9),
            ("SPOT", "spot_symbol", 12),
            ("CLOSE", "spot_close", 10),
            ("ENTRY", "entry_price", 10),
            ("INITIAL SL", "stop_loss", 12),
            ("TRAIL SL", "trailing_stop", 10),
            ("EXIT", "exit_price", 10),
            ("MAX R", "max_rr_achieved", 8),
            ("EXIT R", "exit_rr", 8),
            ("P&L INR PROXY", "pnl_inr_proxy", 13),
            ("TRADE", "trade_status", 18),
            ("RESULT", "result", 25),
        ],
    )


@dataclass
class _SpotProxyTrade:
    event: dict[str, Any]
    direction: str
    entry_trigger: float
    stop_loss: float
    quantity: float
    status: str = "PENDING_ENTRY"
    fill_price: Optional[float] = None
    initial_risk: Optional[float] = None
    current_stop: Optional[float] = None
    max_favorable_price: Optional[float] = None
    max_rr_achieved: float = 0.0


def _close_proxy_trade(
    trade: _SpotProxyTrade,
    row: pd.Series,
    exit_price: float,
    status: str,
) -> None:
    if trade.fill_price is None:
        return
    pnl_inr = (
        exit_price - trade.fill_price
        if trade.direction == "BULLISH"
        else trade.fill_price - exit_price
    ) * trade.quantity
    exit_rr = (
        (exit_price - trade.fill_price)
        if trade.direction == "BULLISH"
        else (trade.fill_price - exit_price)
    ) / trade.initial_risk
    trade.status = status
    trade.event.update(
        exit_price=exit_price,
        exit_rr=round(exit_rr, 2),
        pnl_inr_proxy=round(pnl_inr, 2),
        trade_status=status,
        exit_time=pd.Timestamp(row["datetime"]).strftime("%H:%M:%S"),
    )


def _record_favorable_excursion(trade: _SpotProxyTrade, row: pd.Series) -> None:
    if trade.fill_price is None or trade.initial_risk is None:
        return
    high = float(row["high"])
    low = float(row["low"])
    if trade.direction == "BULLISH":
        previous_max = (
            trade.fill_price
            if trade.max_favorable_price is None
            else trade.max_favorable_price
        )
        trade.max_favorable_price = max(previous_max, high)
        favorable_move = trade.max_favorable_price - trade.fill_price
    else:
        previous_max = (
            trade.fill_price
            if trade.max_favorable_price is None
            else trade.max_favorable_price
        )
        trade.max_favorable_price = min(previous_max, low)
        favorable_move = trade.fill_price - trade.max_favorable_price

    trade.max_rr_achieved = max(
        trade.max_rr_achieved,
        favorable_move / trade.initial_risk,
    )
    trade.event["max_rr_achieved"] = round(trade.max_rr_achieved, 2)


def _update_trailing_stop(trade: _SpotProxyTrade) -> None:
    if (
        trade.fill_price is None
        or trade.initial_risk is None
        or trade.max_favorable_price is None
    ):
        return
    favorable_move = (
        trade.max_favorable_price - trade.fill_price
        if trade.direction == "BULLISH"
        else trade.fill_price - trade.max_favorable_price
    )
    risk = trade.initial_risk
    if favorable_move < 1.5 * risk:
        return
    extra_steps = math.floor((favorable_move - 1.5 * risk + 1e-9) / (0.5 * risk))
    locked_r = extra_steps * 0.5
    candidate = (
        trade.fill_price + locked_r * risk
        if trade.direction == "BULLISH"
        else trade.fill_price - locked_r * risk
    )
    if trade.current_stop is None:
        return
    if trade.direction == "BULLISH":
        trade.current_stop = max(trade.current_stop, candidate)
    else:
        trade.current_stop = min(trade.current_stop, candidate)
    trade.event["trailing_stop"] = trade.current_stop


def _update_proxy_trade(
    trade: _SpotProxyTrade,
    row: pd.Series,
    entry_cutoff: time,
) -> None:
    timestamp = pd.Timestamp(row["datetime"])
    open_price = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])

    if trade.status == "PENDING_ENTRY":
        if timestamp.time() >= entry_cutoff:
            trade.status = "NOT_FILLED_CUTOFF"
            trade.event.update(pnl_inr_proxy=0.0, trade_status=trade.status)
            return
        if trade.direction == "BULLISH" and high >= trade.entry_trigger:
            trade.fill_price = max(open_price, trade.entry_trigger)
        elif trade.direction == "BEARISH" and low <= trade.entry_trigger:
            trade.fill_price = min(open_price, trade.entry_trigger)
        else:
            return
        trade.status = "OPEN"
        trade.initial_risk = abs(trade.fill_price - trade.stop_loss)
        trade.current_stop = trade.stop_loss
        trade.max_favorable_price = trade.fill_price
        trade.event.update(
            entry_price=trade.fill_price,
            trade_status=trade.status,
        )

    if trade.status != "OPEN":
        return
    if trade.current_stop is None:
        return
    _record_favorable_excursion(trade, row)
    if trade.direction == "BULLISH" and low <= trade.current_stop:
        # If a bar crosses both entry and stop, assume the stop was hit.
        _close_proxy_trade(
            trade, row, min(open_price, trade.current_stop), "CLOSED_SL"
        )
    elif trade.direction == "BEARISH" and high >= trade.current_stop:
        # If a bar crosses both entry and stop, assume the stop was hit.
        _close_proxy_trade(
            trade, row, max(open_price, trade.current_stop), "CLOSED_SL"
        )
    else:
        # A stop raised at this candle's close applies from the next candle.
        _update_trailing_stop(trade)


def trace_spot_proxy_rules(
    candles: pd.DataFrame,
    spot_symbol: str,
    provider: HDSignalProvider,
    cfg: StrategyConfig,
    quantity: float = 1.0,
) -> list[dict[str, Any]]:
    """Apply the HD RSI/alert/trend rules to spot candles as an explicit proxy."""
    events: list[dict[str, Any]] = []
    side_state = provider.create_side_state()
    previous: Optional[pd.Series] = None
    active_trade: Optional[_SpotProxyTrade] = None

    for _, row in candles.iterrows():
        if active_trade is not None:
            _update_proxy_trade(active_trade, row, cfg.entry_cutoff)
            if active_trade.status in {"CLOSED_SL", "NOT_FILLED_CUTOFF"}:
                active_trade = None

        was_setup_pending = side_state.setup_pending
        provider.update_state(side_state, row, previous)
        trend = provider._market_trend(row)

        signal_direction = (
            "CE" if trend == "BULLISH" else "PE" if trend == "BEARISH" else None
        )
        signal = (
            provider.generate_signal(signal_direction, side_state, row, previous)
            if signal_direction is not None
            else Signal.NONE
        )

        timestamp = pd.Timestamp(row["datetime"])
        if was_setup_pending:
            proxy_signal = (
                signal is not Signal.NONE and timestamp.time() < cfg.entry_cutoff
            )
            dip_rsi = None if previous is None else _as_float(previous.get("rsi3"))
            extra: dict[str, Any] = {
                "trend": trend,
                "rsi_dip": dip_rsi,
                "result": "HD" if proxy_signal else "RSI dipped below 20",
            }
            detail = "Spot-only proxy; no option candles or orders are used"
            if proxy_signal:
                if signal_direction == "CE":
                    direction = "BULLISH"
                    entry_trigger = float(row["high"]) + 1.0
                    stop_loss = float(row["low"]) - 1.0
                else:
                    direction = "BEARISH"
                    entry_trigger = float(row["low"]) - 1.0
                    stop_loss = float(row["high"]) + 1.0
                extra.update(
                    entry_trigger=entry_trigger,
                    quantity=quantity,
                    stop_loss=stop_loss,
                )
                if active_trade is None:
                    extra.update(
                        entry_price=None,
                        trailing_stop=None,
                        exit_price=None,
                        max_rr_achieved=0.0,
                        exit_rr=None,
                        pnl_inr_proxy=None,
                        trade_status="PENDING_ENTRY",
                        exit_time=None,
                    )
                    active_trade = _SpotProxyTrade(
                        event={},
                        direction=direction,
                        entry_trigger=entry_trigger,
                        stop_loss=stop_loss,
                        quantity=quantity,
                    )
                else:
                    extra["trade_status"] = "SKIPPED_ACTIVE_TRADE"
                    detail = "HD proxy signal skipped because another spot trade is active"
            elif timestamp.time() >= cfg.entry_cutoff:
                detail = "Following alert candle was outside the entry cutoff"
            elif not side_state.alert_ready:
                detail = "Spot RSI dip was not followed by a valid alert candle"
            else:
                detail = f"Alert candle found, but spot trend was {trend}"

            event = _event_row(
                "HD" if proxy_signal else "RSI_DIP",
                spot_symbol,
                row,
                detail,
                **extra,
            )
            events.append(event)
            if proxy_signal and active_trade is not None and not active_trade.event:
                active_trade.event = event

        previous = row

    if active_trade is not None:
        if active_trade.status == "OPEN" and not candles.empty:
            last_row = candles.iloc[-1]
            _close_proxy_trade(
                active_trade,
                last_row,
                float(last_row["close"]),
                "CLOSED_SESSION",
            )
        elif active_trade.status == "PENDING_ENTRY":
            active_trade.status = "NOT_FILLED"
            active_trade.event.update(
                pnl_inr_proxy=0.0,
                trade_status=active_trade.status,
            )

    if side_state.setup_pending and previous is not None:
        events.append(
            _event_row(
                "RSI_DIP",
                spot_symbol,
                previous,
                "No following spot candle was available to confirm the RSI dip",
                trend=provider._market_trend(previous),
                rsi_dip=_as_float(previous.get("rsi3")),
                result="RSI dipped below 20",
            )
        )

    return events


def _parse_time(value: str) -> time:
    return time.fromisoformat(value)


def _slice_spot_history(
    spot_history: pd.DataFrame,
    day: date,
    cfg: StrategyConfig,
) -> pd.DataFrame:
    start = datetime.combine(day, cfg.market_open)
    end = datetime.combine(day, cfg.market_close)
    return spot_history.loc[
        (spot_history["datetime"] >= start)
        & (spot_history["datetime"] < end)
    ].reset_index(drop=True)


def _attach_spot_ema_columns(candles: pd.DataFrame) -> pd.DataFrame:
    spot = candles.copy()
    for period in (13, 20, 50):
        source = f"ema{period}"
        if source in spot:
            spot[f"spot_{source}"] = spot[source]
    return spot


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
        exchange_spot=args.exchange_spot or "NSE_INDEX",
        timeframe_minutes=args.timeframe,
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
    quantity: float = 1.0,
) -> pd.DataFrame:
    """Fetch spot candles only and evaluate HD-style spot-proxy attempts."""
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
        raise RuntimeError(
            f"OpenAlgo returned no {cfg.spot_symbol} spot history for this range"
        )

    spot_history = add_indicators(spot_history, cfg)

    events: list[dict[str, Any]] = []
    provider = HDSignalProvider()
    trading_days = [
        day
        for day in _iter_trading_days(spot_history)
        if start_date <= day <= end_date and day.weekday() < 5
    ]
    for day in trading_days:
        spot_day = _slice_spot_history(spot_history, day, cfg)
        if spot_day.empty:
            continue
        lock_timestamp = datetime.combine(day, cfg.atm_lock_time)
        signal_day = spot_day[spot_day["datetime"] >= lock_timestamp].reset_index(
            drop=True
        )
        if signal_day.empty:
            continue
        candles = _attach_spot_ema_columns(signal_day)
        events.extend(
            trace_spot_proxy_rules(
                candles,
                cfg.spot_symbol,
                provider,
                cfg,
                quantity,
            )
        )

    results = pd.DataFrame(events)
    for column in OUTPUT_COLUMNS:
        if column not in results.columns:
            results[column] = None
    return results[OUTPUT_COLUMNS]


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print HD-style spot-proxy results from historical spot candles."
    )
    parser.add_argument(
        "--start-date",
        required=True,
        type=date.fromisoformat,
        help="First trading date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        type=date.fromisoformat,
        help="Last trading date (YYYY-MM-DD)",
    )
    parser.add_argument("--spot-symbol", default="NIFTY")
    parser.add_argument("--exchange-spot")
    parser.add_argument(
        "--quantity",
        type=float,
        default=1.0,
        help="Spot-proxy units used to calculate INR P&L (default: 1)",
    )
    parser.add_argument(
        "--timeframe",
        type=int,
        default=3,
        help="Candle interval in minutes",
    )
    parser.add_argument(
        "--entry-cutoff",
        default=os.getenv("HD_ENTRY_CUTOFF", "14:40"),
    )
    return parser


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    load_dotenv(project_dir / ".env")
    args = _argument_parser().parse_args()
    if args.start_date > args.end_date:
        raise SystemExit("--start-date must be on or before --end-date")
    if args.timeframe <= 0:
        raise SystemExit("--timeframe must be positive")
    if args.quantity <= 0:
        raise SystemExit("--quantity must be positive")

    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        raise SystemExit("OPENALGO_API_KEY is not set in the environment or .env")
    host = (
        os.getenv("OPENALGO_HOST")
        or os.getenv("OPENALGO_URL")
        or "http://127.0.0.1:5002"
    )
    broker = OpenAlgoBroker(api_key=api_key, host=host, dry_run=True)
    cfg = _build_config(args)
    print(
        f"Fetching {cfg.spot_symbol} spot candles only from OpenAlgo "
        f"for {args.start_date} through {args.end_date}...",
        flush=True,
    )
    try:
        results = run_backtest(
            args.start_date,
            args.end_date,
            cfg,
            broker,
            quantity=args.quantity,
        )
    except RuntimeError as exc:
        raise SystemExit(f"Backtest cannot continue: {exc}") from exc

    print_proxy_report(results)
    print(f"\nHD proxy rows: {(results['event'] == 'HD').sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
