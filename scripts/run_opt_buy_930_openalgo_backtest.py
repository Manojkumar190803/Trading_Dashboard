from __future__ import annotations

import logging
import os
import time as time_module
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

import pandas as pd

from core.broker import OpenAlgoBroker
from strategies.opt_buy_930 import OptionCandidate, OptBuy930Config, TradeResult, run_backtest, select_watchlist

logger = logging.getLogger("opt_buy_930.runner")
IST_START = time(9, 20)
IST_END = time(10, 1)


def normalize_history(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    frame.columns = [str(column).lower() for column in frame.columns]
    for candidate in ("timestamp", "time", "date"):
        if "datetime" not in frame.columns and candidate in frame.columns:
            frame = frame.rename(columns={candidate: "datetime"})
    if "datetime" not in frame.columns:
        raise RuntimeError("history is missing datetime")
    frame["datetime"] = pd.to_datetime(frame["datetime"]).dt.tz_localize(None)
    required = {"datetime", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise RuntimeError(f"history is missing columns: {sorted(missing)}")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.dropna(subset=["datetime", "close"]).sort_values("datetime").reset_index(drop=True)


def day_window(frame: pd.DataFrame, day: date) -> pd.DataFrame:
    return frame[(frame["datetime"].dt.date == day) & (frame["datetime"].dt.time >= IST_START) & (frame["datetime"].dt.time <= IST_END)]


def build_symbol(root: str, expiry: date, strike: int, side: str) -> str:
    return f"{root}{expiry.strftime('%d%b%y').upper()}{strike}{side}"


def fetch_history(broker: OpenAlgoBroker, symbol: str, exchange: str, start: str, end: str) -> pd.DataFrame:
    return normalize_history(broker.fetch_history(symbol, exchange, "1m", start, end))


def run_openalgo_backtest(start: str, end: str, output_csv: Optional[str], output_txt: Optional[str], profile: Optional[dict[str, object]] = None, strikes_each_side: int = 8) -> list[TradeResult]:
    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        raise SystemExit("OPENALGO_API_KEY not set (check .env)")
    host = os.getenv("OPENALGO_HOST") or os.getenv("OPENALGO_URL") or "http://127.0.0.1:5002"
    broker = OpenAlgoBroker(api_key=api_key, host=host, dry_run=True)
    profile = profile or broker.discover_index_profile("NIFTY")
    spot = fetch_history(broker, str(profile["spot_symbol"]), str(profile["exchange_spot"]), start, end)
    config = OptBuy930Config(quantity=130, lot_size=int(profile["option_lot_size"]))
    results: list[TradeResult] = []
    for day in sorted({stamp.date() for stamp in spot["datetime"] if stamp.weekday() < 5}):
        spot_day = day_window(spot, day)
        scan = spot_day[spot_day["datetime"].dt.time >= time(9, 25)]
        if scan.empty:
            continue
        step = int(profile["strike_step"])
        atm = int(round(float(scan.iloc[0]["close"]) / step) * step)
        expiry = broker.resolve_nearest_expiry(str(profile["option_index_symbol"]), day, atm, step, int(profile["weekly_expiry_weekday"]))
        if expiry is None:
            continue
        candidate_data: list[tuple[OptionCandidate, pd.DataFrame]] = []
        for offset in range(-strikes_each_side, strikes_each_side + 1):
            for side in ("CE", "PE"):
                strike = atm + offset * step
                symbol = build_symbol(str(profile["option_index_symbol"]), expiry, strike, side)
                try:
                    history = fetch_history(broker, symbol, str(profile["exchange_options"]), start, end)
                except Exception:
                    continue
                rows = history[(history["datetime"].dt.date == day) & (history["datetime"].dt.time >= time(9, 25))]
                if not rows.empty:
                    candidate_data.append((OptionCandidate(symbol, side, strike, float(rows.iloc[0]["close"])), history))
        try:
            selected = select_watchlist([candidate for candidate, _ in candidate_data], config)
        except ValueError:
            continue
        histories = {candidate.symbol: history for candidate, history in candidate_data}
        ticks = [(side, float(row["close"]), row["datetime"].to_pydatetime()) for side, candidate in selected.items() for _, row in day_window(histories[candidate.symbol], day).iterrows() if row["datetime"].time() >= config.signal_start]
        trade = run_backtest(selected.values(), ticks, config)
        if trade is not None:
            results.append(trade)
    if output_csv is not None and output_txt is not None:
        fields = ["side", "symbol", "quantity", "entry_time", "entry_price", "stop_loss", "target", "exit_time", "exit_price", "exit_reason", "gross_pnl"]
        with Path(output_csv).open("w", encoding="utf-8") as csv_handle, Path(output_txt).open("w", encoding="utf-8") as txt_handle:
            csv_handle.write(",".join(fields) + "\n")
            txt_handle.write("\t".join(fields) + "\n")
            for trade in results:
                values = [getattr(trade, field) if field != "gross_pnl" else trade.gross_pnl for field in fields]
                csv_handle.write(",".join(str(value) for value in values) + "\n")
                txt_handle.write("\t".join(str(value) for value in values) + "\n")
    return results


def _broker_from_env(profile: dict[str, object], dry_run: bool) -> OpenAlgoBroker:
    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        raise SystemExit("OPENALGO_API_KEY not set (check .env)")
    host = os.getenv("OPENALGO_HOST") or os.getenv("OPENALGO_URL") or "http://127.0.0.1:5002"
    return OpenAlgoBroker(api_key=api_key, host=host, ws_url=os.getenv("OPENALGO_WS_URL"), exchange_options=str(profile["exchange_options"]), dry_run=dry_run)


def run_openalgo_live(profile: dict[str, object], dry_run: bool = True, stop_event: Optional[object] = None) -> None:
    """Run the 09:30 strategy by polling quotes until its session is complete."""
    broker = _broker_from_env(profile, dry_run)
    config = OptBuy930Config(quantity=130, lot_size=int(profile["option_lot_size"]))
    logger.info(
        "OPT-Buy live started (spot=%s dry_run=%s); waiting for scan at 09:25",
        profile["spot_symbol"], dry_run,
    )
    last_wait_log = 0.0
    while datetime.now().time() < time(9, 25):
        if stop_event is not None and stop_event.is_set():
            logger.info("OPT-Buy live stopped before scan")
            return
        now_monotonic = time_module.monotonic()
        if now_monotonic - last_wait_log >= 30:
            logger.info("OPT-Buy waiting for 09:25 scan; current time=%s", datetime.now().strftime("%H:%M:%S"))
            last_wait_log = now_monotonic
        time_module.sleep(1)
    logger.info("OPT-Buy scan starting")
    spot = broker.get_ltp(str(profile["spot_symbol"]))
    if spot <= 0:
        logger.error(
            "OPT-Buy cannot start: no spot quote for %s. "
            "OpenAlgo/Fyers returned no price; refresh the broker session/token and retry.",
            profile["spot_symbol"],
        )
        return
    step = int(profile["strike_step"])
    atm = int(round(spot / step) * step)
    expiry = broker.resolve_nearest_expiry(str(profile["option_index_symbol"]), datetime.now().date(), atm, step, int(profile["weekly_expiry_weekday"]))
    if expiry is None:
        raise RuntimeError("unable to resolve OPT-Buy expiry")
    logger.info("OPT-Buy spot=%.2f ATM=%s next_expiry=%s; probing option quotes", spot, atm, expiry)
    candidates = []
    for offset in range(-8, 9):
        for side in ("CE", "PE"):
            strike = atm + offset * step
            symbol = build_symbol(str(profile["option_index_symbol"]), expiry, strike, side)
            premium = broker.get_ltp(symbol)
            if premium:
                candidates.append(OptionCandidate(symbol, side, strike, premium))
            time_module.sleep(0.15)
    logger.info("OPT-Buy quote scan complete: %d valid candidates", len(candidates))
    for side in ("CE", "PE"):
        premiums = [candidate.premium for candidate in candidates if candidate.side == side]
        if premiums:
            logger.info(
                "OPT-Buy %s premiums: min=%.2f max=%.2f count=%d",
                side, min(premiums), max(premiums), len(premiums),
            )
    from strategies.opt_buy_930 import OptBuy930Strategy
    strategy = OptBuy930Strategy(config)
    try:
        strategy.scan(candidates)
    except ValueError:
        logger.error(
            "OPT-Buy cannot start: CE and PE quotes were unavailable or outside "
            "the premium selection range (%.2f +/- %.2f). Check the premium "
            "range, broker session, and option symbols.",
            config.reference_premium, config.max_selection_distance,
        )
        return
    logger.info("OPT-Buy watchlist: %s", {side: item.symbol for side, item in strategy.state.selected.items()})
    logger.info("OPT-Buy watching for entries from 09:30 to 09:45")
    last_heartbeat = 0.0
    while datetime.now().time() < config.hard_exit_time and (stop_event is None or not stop_event.is_set()):
        now = datetime.now()
        now_monotonic = time_module.monotonic()
        if now_monotonic - last_heartbeat >= 30:
            logger.info(
                "OPT-Buy heartbeat: status=%s time=%s selected=%s",
                strategy.state.session_status,
                now.strftime("%H:%M:%S"),
                {side: item.symbol for side, item in strategy.state.selected.items()},
            )
            last_heartbeat = now_monotonic
        for side, candidate in strategy.state.selected.items():
            price = broker.get_ltp(candidate.symbol)
            if price:
                if strategy.state.trade is None:
                    trade = strategy.process_tick(side, price, now)
                    if trade is not None:
                        logger.info(
                            "OPT-Buy entry: side=%s symbol=%s price=%.2f qty=%s SL=%.2f target=%.2f",
                            trade.side, trade.symbol, trade.entry_price, trade.quantity,
                            trade.stop_loss, trade.target,
                        )
                else:
                    strategy.process_position_tick(price, now)
                    strategy.process_time(price, now)
        if strategy.state.trade and strategy.state.trade.exit_reason != "ACTIVE":
            logger.info("OPT-Buy trade closed: %s", strategy.state.trade)
            return
        time_module.sleep(1)
    if stop_event is not None and stop_event.is_set():
        logger.info("OPT-Buy live stopped; final status=%s", strategy.state.session_status)
    else:
        logger.info("OPT-Buy session complete at 10:00; final status=%s", strategy.state.session_status)
