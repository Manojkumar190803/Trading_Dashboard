from __future__ import annotations

import logging
import csv
import json
import os
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from core.broker import HistoricalReplayBroker, OpenAlgoBroker
from core.engine import BaseStrategyEngine, get_atm_strike
from core.indicators import add_indicators
from core.models import PendingEntry, RiskConfig, Signal, StrategyAlert, StrategyConfig
from strategies.base import SignalProvider

logger = logging.getLogger("core.runner")


def _atm_lock_path(trading_day: date, script: str) -> Path:
    return Path("logs") / f"atm_lock_{script}_{trading_day:%Y%m%d}.json"


def _trade_alert_path(trading_day: date, script: str) -> Path:
    return Path("logs") / f"trade_alerts_{script}_{trading_day:%Y%m%d}.csv"


def _persist_atm_lock(engine: BaseStrategyEngine, spot_price: float) -> None:
    if not engine.state.atm_locked or not engine.state.trading_day:
        return
    path = _atm_lock_path(engine.state.trading_day, engine.cfg.option_index_symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "trading_day": engine.state.trading_day.isoformat(),
        "spot_price": spot_price,
        "ce_symbol": engine.state.ce_symbol,
        "pe_symbol": engine.state.pe_symbol,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _restore_atm_lock(engine: BaseStrategyEngine, trading_day: date) -> bool:
    path = _atm_lock_path(trading_day, engine.cfg.option_index_symbol)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        ce_symbol = str(payload["ce_symbol"])
        pe_symbol = str(payload["pe_symbol"])
        if not ce_symbol or not pe_symbol:
            return False
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("could not restore ATM lock from %s: %s", path, exc)
        return False

    engine.on_day_transition_if_needed(datetime.combine(trading_day, engine.cfg.atm_lock_time))
    engine.state.ce_symbol = ce_symbol
    engine.state.pe_symbol = pe_symbol
    engine.state.ce.option_symbol = ce_symbol
    engine.state.pe.option_symbol = pe_symbol
    engine.state.atm_locked = True
    logger.info("restored ATM lock for %s: CE=%s PE=%s", trading_day, ce_symbol, pe_symbol)
    return True


def _restore_atm_lock_from_positions(
    engine: BaseStrategyEngine,
    broker: OpenAlgoBroker,
    trading_day: date,
) -> bool:
    """Keep a restart aligned with an already-held option instrument."""
    try:
        positions = broker.get_position_book()
    except Exception as exc:
        logger.warning("could not inspect positions while restoring ATM lock: %s", exc)
        return False

    for position in positions:
        symbol = str(position.get("symbol") or "")
        quantity = int(float(position.get("quantity") or 0))
        if quantity <= 0:
            continue
        try:
            root, expiry_code, strike, option_type = _parse_option_symbol(symbol)
        except ValueError:
            continue
        if root != engine.cfg.option_index_symbol:
            continue
        ce_symbol = build_option_symbol(root, expiry_code, strike, "CE")
        pe_symbol = build_option_symbol(root, expiry_code, strike, "PE")
        engine.on_day_transition_if_needed(datetime.combine(trading_day, engine.cfg.atm_lock_time))
        engine.state.ce_symbol = ce_symbol
        engine.state.pe_symbol = pe_symbol
        engine.state.ce.option_symbol = ce_symbol
        engine.state.pe.option_symbol = pe_symbol
        engine.state.atm_locked = True
        logger.warning(
            "restored ATM lock for %s from held broker position: CE=%s PE=%s",
            trading_day, ce_symbol, pe_symbol,
        )
        return True
    return False


def _restore_atm_lock_from_alerts(engine: BaseStrategyEngine, trading_day: date) -> bool:
    """Recover the exact live-day strike from persisted entry alerts."""
    path = _trade_alert_path(trading_day, engine.cfg.option_index_symbol)
    if not path.exists():
        return False
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = [
                row for row in csv.DictReader(handle)
                if row.get("strategy") == engine.strategy_name and row.get("category") == "ENTRY"
            ]
    except OSError as exc:
        logger.warning("could not restore ATM lock from alerts: %s", exc)
        return False
    if not rows:
        return False

    symbols = re.findall(r"\b([A-Z]+\d{2}[A-Z]{3}\d{2}\d+(?:CE|PE))\b", str(rows[-1].get("message") or ""))
    if not symbols:
        return False
    try:
        root, expiry_code, strike, _ = _parse_option_symbol(symbols[-1])
    except ValueError:
        return False
    if root != engine.cfg.option_index_symbol:
        return False

    engine.on_day_transition_if_needed(datetime.combine(trading_day, engine.cfg.atm_lock_time))
    engine.state.ce_symbol = _build_option_symbol(root, expiry_code, strike, "CE")
    engine.state.pe_symbol = _build_option_symbol(root, expiry_code, strike, "PE")
    engine.state.ce.option_symbol = engine.state.ce_symbol
    engine.state.pe.option_symbol = engine.state.pe_symbol
    engine.state.atm_locked = True
    logger.info(
        "replay restored ATM lock for %s from alerts: CE=%s PE=%s",
        trading_day, engine.state.ce_symbol, engine.state.pe_symbol,
    )
    return True


def _print_persisted_trade_alerts(strategy_name: str, trading_day: date, script: str) -> None:
    path = _trade_alert_path(trading_day, script)
    if not path.exists():
        return
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = [row for row in csv.DictReader(handle) if row.get("strategy") == strategy_name]
    except OSError as exc:
        logger.warning("could not read persisted trade alerts: %s", exc)
        return
    if not rows:
        return
    print(f"\nPast {strategy_name} trades for {trading_day}:")
    for row in rows:
        print(f"[HISTORY][{row.get('category', '?')}] {row.get('timestamp', '?')} {row.get('message', '')}")


def _load_persisted_trade_alerts(
    engine: BaseStrategyEngine,
    trading_day: date,
) -> None:
    """Restore today's entry and exit alerts so live status survives restarts."""
    path = _trade_alert_path(trading_day, engine.cfg.option_index_symbol)
    if not path.exists():
        return
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = [
                row for row in csv.DictReader(handle)
                if row.get("strategy") == engine.strategy_name
                and row.get("category") in ("ENTRY", "EXIT")
            ]
    except (OSError, ValueError) as exc:
        logger.warning("could not load persisted trade alerts: %s", exc)
        return

    for row in rows:
        try:
            timestamp = datetime.fromisoformat(str(row["timestamp"]))
        except (KeyError, TypeError, ValueError):
            continue
        engine.alerts.append(
            StrategyAlert(
                timestamp=timestamp,
                category=str(row["category"]),
                message=str(row.get("message") or ""),
            )
        )


def _restore_open_positions(engine: BaseStrategyEngine, broker: OpenAlgoBroker, trading_day: date) -> None:
    """Restore matching OpenAlgo positions and open entry orders after restart."""
    path = _trade_alert_path(trading_day, engine.cfg.option_index_symbol)
    try:
        alerts = []
        if path.exists():
            with path.open(newline="", encoding="utf-8") as handle:
                alerts = [row for row in csv.DictReader(handle) if row.get("strategy") == engine.strategy_name]
        broker_positions = broker.get_position_book()
        open_orders = broker.get_open_orders()
    except (OSError, ValueError) as exc:
        logger.warning("could not restore persisted positions: %s", exc)
        return

    entry_pattern = re.compile(
        r"(?:Entered|Uncertain) (CE|PE) (\S+)(?: @ ([\d.]+),)? qty=(\d+),?\s+"
        r"(?:alert_trigger|trigger)=([\d.]+) SL=([\d.]+)(?:, option_risk=([\d.]+))?"
    )
    for position in broker_positions:
        symbol = str(position.get("symbol") or "")
        quantity = int(float(position.get("quantity") or 0))
        if not symbol or quantity <= 0:
            continue
        matching = [
            row for row in alerts
            if row.get("category") in ("ENTRY", "UNCERTAIN_ENTRY")
            and symbol in str(row.get("message") or "")
        ]
        if matching:
            match = entry_pattern.search(str(matching[-1].get("message") or ""))
            if match is None:
                logger.warning("could not parse persisted entry for open position %s", symbol)
                continue
            side, _, parsed_entry, _, trigger, stop, risk = match.groups()
            entry_alert = matching[-1]
            entry_price = float(position.get("average_price") or parsed_entry or trigger)
            risk = risk or str(abs(float(trigger) - float(stop)))
            entry_time = datetime.fromisoformat(str(entry_alert["timestamp"]))
        else:
            try:
                _, _, _, side = _parse_option_symbol(symbol)
            except ValueError:
                continue
            entry_price = float(position.get("average_price") or 0)
            if entry_price <= 0:
                logger.warning("cannot restore open position %s without average price", symbol)
                continue
            side_state = engine._side_state(side)
            recovered_trigger = getattr(side_state, "first_red_high", None)
            recovered_stop = getattr(side_state, "setup_candle_low", None)
            if (
                side_state.order_submission_uncertain
                and side_state.option_symbol == symbol
                and recovered_trigger is not None
                and recovered_stop is not None
                and float(recovered_trigger) > float(recovered_stop)
            ):
                trigger = str(recovered_trigger)
                stop = str(recovered_stop)
                risk = str(float(recovered_trigger) - float(recovered_stop))
                logger.info(
                    "restoring uncertain %s entry intent for %s: trigger=%s stop=%s",
                    side, symbol, trigger, stop,
                )
            else:
                risk_points = max(float(engine.cfg.max_option_risk_points), engine.cfg.option_tick_size)
                trigger = str(entry_price)
                stop = str(entry_price - risk_points)
                risk = str(risk_points)
            entry_time = datetime.now()
            if recovered_trigger is None or recovered_stop is None:
                logger.warning(
                    "restoring broker-held %s without ENTRY alert; using fallback SL=%.2f "
                    "from max risk %.2f; verify the original strategy stop manually",
                    symbol, entry_price - risk_points, risk_points,
                )
        side_state = engine._side_state(side)
        was_uncertain = side_state.order_submission_uncertain
        engine.restore_open_position(
            side,
            quantity,
            entry_price,
            entry_time,
            float(stop),
            float(trigger),
            float(risk),
        )
        side_state.order_submission_uncertain = False
        engine.total_entries = max(
            engine.total_entries,
            sum(row.get("category") in ("ENTRY", "UNCERTAIN_ENTRY") for row in alerts),
        )
        if not matching:
            engine.total_entries += 1
        if open_orders is not None:
            protective_orders = [
                order for order in open_orders
                if str(order.get("symbol") or "") == symbol
                and str(order.get("action") or order.get("side") or "").upper() == "SELL"
            ]
            expected_stop = float(stop)
            matching_protective_order = any(
                abs(float(order.get("trigger_price") or order.get("trigger") or 0) - expected_stop)
                <= engine.cfg.option_tick_size
                for order in protective_orders
            )
            matching_protective = next(
                (
                    order for order in protective_orders
                    if abs(float(order.get("trigger_price") or order.get("trigger") or 0) - expected_stop)
                    <= engine.cfg.option_tick_size
                ),
                None,
            )
            if matching_protective is not None:
                engine._side_state(side).position.protective_stop_order_id = str(
                    matching_protective.get("orderid") or matching_protective.get("order_id") or ""
                )
            if not matching_protective_order and was_uncertain:
                for order in protective_orders:
                    order_id = str(order.get("orderid") or order.get("order_id") or "")
                    if order_id:
                        engine.broker.cancel_order(order_id)
            has_protective_order = matching_protective_order
            if not has_protective_order:
                engine._place_protective_stop(side, engine._side_state(side).position, entry_time)
        logger.info("restored open %s position from OpenAlgo: %s qty=%s", side, symbol, quantity)

    for order in open_orders or []:
        symbol = str(order.get("symbol") or "")
        action = str(order.get("action") or order.get("side") or "").upper()
        if not symbol or action != "BUY":
            continue
        try:
            _, _, _, side = _parse_option_symbol(symbol)
        except ValueError:
            continue
        side_state = engine._side_state(side)
        if side_state.position is not None or side_state.pending_entry is not None:
            continue

        quantity = int(float(order.get("quantity") or order.get("qty") or 0))
        trigger = float(
            order.get("trigger_price")
            or order.get("trigger")
            or order.get("price")
            or 0
        )
        limit_price = float(order.get("price") or trigger or 0)
        order_id = str(order.get("orderid") or order.get("order_id") or "")
        if quantity <= 0 or trigger <= 0 or not order_id:
            logger.warning("could not restore incomplete open order for %s: %s", symbol, order)
            continue

        risk_points = max(float(engine.cfg.max_option_risk_points), engine.cfg.option_tick_size)
        side_state.option_symbol = symbol
        side_state.order_submission_uncertain = False
        side_state.pending_entry = PendingEntry(
            signal=Signal.BUY_CE if side == "CE" else Signal.BUY_PE,
            created_at=datetime.now(),
            option_symbol=symbol,
            quantity=quantity,
            option_trigger_level=trigger,
            option_stop_level=trigger - risk_points,
            trigger_candle_high=trigger,
            trigger_candle_low=trigger,
            order_id=order_id,
        )
        logger.info(
            "restored open %s entry order from OpenAlgo: %s qty=%s trigger=%.2f limit=%.2f",
            side, symbol, quantity, trigger, limit_price,
        )


def _seconds_until_market_open(cfg: StrategyConfig, now: Optional[datetime] = None) -> float:
    """Return the wait until the next weekday market open."""
    current = now or datetime.now()
    next_open = datetime.combine(current.date(), cfg.market_open)
    if current >= next_open or current.weekday() >= 5:
        next_open += timedelta(days=1)
    while next_open.weekday() >= 5:
        next_open += timedelta(days=1)
    return max(1.0, (next_open - current).total_seconds())


def _normalize_history_df(df: pd.DataFrame) -> pd.DataFrame:
    """Convert an OpenAlgo history DataFrame into canonical columns."""
    out = df.copy()
    if isinstance(out.index, pd.DatetimeIndex):
        index_name = out.index.name or "datetime"
        out = out.reset_index().rename(columns={index_name: "datetime"})
    out.columns = [str(c).lower() for c in out.columns]
    if "datetime" not in out.columns:
        for candidate in ("timestamp", "time", "date"):
            if candidate in out.columns:
                out = out.rename(columns={candidate: "datetime"})
                break
    if "datetime" not in out.columns:
        raise RuntimeError(f"history frame missing datetime column: {list(out.columns)}")

    out["datetime"] = pd.to_datetime(out["datetime"]).dt.tz_localize(None)
    required = {"datetime", "open", "high", "low", "close", "volume"}
    missing = required - set(out.columns)
    if missing:
        if missing == {"volume"}:
            out["volume"] = 0.0
        else:
            raise RuntimeError(f"history frame missing columns: {sorted(missing)}")

    out = out[["datetime", "open", "high", "low", "close", "volume"]]
    out[["open", "high", "low", "close", "volume"]] = out[
        ["open", "high", "low", "close", "volume"]
    ].apply(pd.to_numeric, errors="coerce")
    return out.sort_values("datetime").reset_index(drop=True)


def _parse_option_symbol(symbol: str) -> tuple[str, str, int, str]:
    """Parse <ROOT><DDMMMYY><STRIKE><CE|PE> option symbols."""
    m = re.match(r"^(.*?)(\d{2}[A-Z]{3}\d{2})(\d+)(CE|PE)$", symbol)
    if not m:
        raise ValueError(f"Unrecognized option symbol format: {symbol}")
    root, expiry_code, strike_str, option_type = m.groups()
    return root, expiry_code, int(strike_str), option_type


def _build_option_symbol(root: str, expiry_code: str, strike: int, option_type: str) -> str:
    return f"{root}{expiry_code}{strike}{option_type}"


def _strike_offsets(max_steps: int = 8) -> list[int]:
    """Return 0, +1, -1, +2, -2, ... for nearby strike probing."""
    out = [0]
    for step in range(1, max_steps + 1):
        out.extend([step, -step])
    return out


def _resolve_option_pair_history(
    broker: OpenAlgoBroker,
    ce_symbol: str,
    pe_symbol: str,
    exchange: str,
    interval: str,
    start_date: str,
    end_date: str,
    strike_step: int,
    max_steps: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str, int]:
    """Try ATM and nearby strikes; return first CE/PE pair that has history."""
    ce_root, ce_exp, ce_strike, ce_type = _parse_option_symbol(ce_symbol)
    pe_root, pe_exp, pe_strike, pe_type = _parse_option_symbol(pe_symbol)
    if ce_root != pe_root or ce_exp != pe_exp or ce_type != "CE" or pe_type != "PE":
        raise RuntimeError(
            f"Cannot resolve pair for symbols CE={ce_symbol} PE={pe_symbol}"
        )
    base_strike = ce_strike
    if pe_strike != base_strike:
        base_strike = int(round((ce_strike + pe_strike) / 2))

    last_exc: Optional[Exception] = None
    for off in _strike_offsets(max_steps=max_steps):
        strike = base_strike + off * strike_step
        ce_try = _build_option_symbol(ce_root, ce_exp, strike, "CE")
        pe_try = _build_option_symbol(pe_root, pe_exp, strike, "PE")
        try:
            ce_df = _fetch_history_df(broker, ce_try, exchange, interval, start_date, end_date)
            pe_df = _fetch_history_df(broker, pe_try, exchange, interval, start_date, end_date)
            if ce_df.empty or pe_df.empty:
                continue
            return ce_df, pe_df, ce_try, pe_try, off
        except Exception as exc:
            last_exc = exc
            continue

    if last_exc is not None:
        raise RuntimeError(str(last_exc))
    raise RuntimeError(f"No option history available for {ce_symbol}/{pe_symbol}")


# ===============================================================
#  Live feed runner
# ===============================================================


class LiveFeedRunner:
    """Polls OpenAlgo history at candle boundaries and drives the engine."""

    def __init__(
        self,
        engine: BaseStrategyEngine,
        broker: OpenAlgoBroker,
        cfg: StrategyConfig,
        lookback_days: int = 5,
        poll_slack_seconds: int = 5,
    ) -> None:
        self.engine = engine
        self.broker = broker
        self.cfg = cfg
        self.lookback_days = lookback_days
        self.poll_slack_seconds = poll_slack_seconds
        self._stop = threading.Event()
        self._last_bar_time: dict[str, Optional[datetime]] = {"CE": None, "PE": None}
        self._startup_baselined: set[str] = set()
        self._shown_alert_times: dict[str, Optional[datetime]] = {"ENTRY": None, "EXIT": None}

    def stop(self) -> None:
        self._stop.set()

    def _try_lock_atm(self, now: datetime) -> None:
        if self.engine.state.atm_locked:
            return
        if _restore_atm_lock(self.engine, now.date()):
            _restore_open_positions(self.engine, self.broker, now.date())
            return
        if _restore_atm_lock_from_positions(self.engine, self.broker, now.date()):
            _restore_open_positions(self.engine, self.broker, now.date())
            return
        if now.time() < self.cfg.atm_lock_time:
            return
        try:
            spot_ltp = self.broker.get_ltp(self.cfg.spot_symbol)
        except Exception as exc:
            logger.warning("spot LTP fetch failed while locking ATM: %s", exc)
            return
        if not spot_ltp:
            logger.warning("spot LTP came back 0/None — will retry next poll")
            return
        lock_ts = datetime.combine(now.date(), self.cfg.atm_lock_time)
        self.engine.on_day_transition_if_needed(lock_ts)
        self.engine.lock_atm_for_day(lock_ts, float(spot_ltp))
        _persist_atm_lock(self.engine, float(spot_ltp))
        _restore_open_positions(self.engine, self.broker, now.date())

    def _fetch_option_history(self, option_symbol: str) -> pd.DataFrame:
        today = datetime.now().date()
        start = (today - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        interval = f"{self.cfg.timeframe_minutes}m"
        raw = self.broker.fetch_history(
            symbol=option_symbol,
            exchange=self.cfg.exchange_options,
            interval=interval,
            start_date=start,
            end_date=end,
        )
        base = _normalize_history_df(raw)
        if base.empty:
            return base
        base = add_indicators(base.reset_index(drop=True), self.cfg)
        session_start = datetime.combine(today, self.cfg.market_open)
        session_end = datetime.combine(today, self.cfg.market_close)
        base = base[(base["datetime"] >= session_start) & (base["datetime"] < session_end)]
        return base.reset_index(drop=True)

    def _seconds_until_next_boundary(self) -> float:
        now = datetime.now()
        tf = self.cfg.timeframe_minutes
        boundary_min = ((now.minute // tf) + 1) * tf
        next_ts = now.replace(second=0, microsecond=0)
        if boundary_min >= 60:
            next_ts = next_ts.replace(minute=0) + timedelta(hours=1)
        else:
            next_ts = next_ts.replace(minute=boundary_min)
        return max(1.0, (next_ts - now).total_seconds() + self.poll_slack_seconds)

    def _process_new_bars_for_side(self, side: str, data: pd.DataFrame) -> None:
        if data.empty:
            return
        now = datetime.now()
        tf_delta = timedelta(minutes=self.cfg.timeframe_minutes)
        closed = data[data["datetime"] + tf_delta <= now]
        if closed.empty:
            return

        last_ts = self._last_bar_time.get(side)
        if side not in self._startup_baselined and last_ts is None:
            latest_ts = closed["datetime"].iloc[-1]
            self._last_bar_time[side] = (
                latest_ts.to_pydatetime() if hasattr(latest_ts, "to_pydatetime") else latest_ts
            )
            self._startup_baselined.add(side)
            logger.info(
                "baselined %s at %s; historical bars will not create orders, "
                "new live signals remain enabled",
                side,
                self._last_bar_time[side],
            )
            return
        if last_ts is not None:
            closed = closed[closed["datetime"] > last_ts]
            if closed.empty:
                return

        for i, (_, row) in enumerate(closed.iterrows()):
            row_idx = row.name if hasattr(row, "name") else None
            prev_row: Optional[pd.Series] = None
            if row_idx is None:
                first_idx = closed.index[0]
                pos_in_full = data.index.get_loc(first_idx) + i
            else:
                pos_in_full = data.index.get_loc(row_idx)
            if pos_in_full > 0:
                prev_row = data.iloc[pos_in_full - 1]
            self.engine.process_option_candle(side, row, prev_row)
            ts = row["datetime"]
            self._last_bar_time[side] = (
                ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            )
            if not self.engine.verbose:
                logger.info(
                    "processed %s bar %s O=%.2f H=%.2f L=%.2f C=%.2f",
                    side, self._last_bar_time[side],
                    row["open"], row["high"], row["low"], row["close"],
                )

    def _poll_once(self) -> None:
        now = datetime.now()
        self._try_lock_atm(now)
        if not self.engine.state.atm_locked:
            return
        if any(
            self.engine._side_state(side).order_submission_uncertain
            for side in ("CE", "PE")
        ):
            _restore_open_positions(self.engine, self.broker, now.date())

        for side, symbol in (
            ("CE", self.engine.state.ce_symbol),
            ("PE", self.engine.state.pe_symbol),
        ):
            if not symbol:
                continue
            try:
                data = self._fetch_option_history(symbol)
            except Exception as exc:
                logger.warning("history fetch failed for %s %s: %s", side, symbol, exc)
                continue
            self._process_new_bars_for_side(side, data)

    def _wait_with_countdown(self, seconds: float) -> bool:
        import sys
        deadline = datetime.now() + timedelta(seconds=seconds)
        while not self._stop.is_set():
            remaining = (deadline - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            self._poll_active_ticks()
            mins, secs = divmod(int(remaining), 60)
            sys.stdout.write(f"\r⏳ Next candle in {mins:02d}:{secs:02d} ")
            sys.stdout.flush()
            if self._stop.wait(min(1.0, remaining)):
                sys.stdout.write("\r" + " " * 30 + "\r")
                sys.stdout.flush()
                return True
        sys.stdout.write("\r" + " " * 30 + "\r")
        sys.stdout.flush()
        return False

    def _poll_active_ticks(self) -> None:
        for side in ("CE", "PE"):
            side_state = self.engine._side_state(side)
            if side_state.position is None:
                continue
            try:
                ltp = self.broker.get_ltp(side_state.position.option_symbol)
            except Exception as exc:
                logger.warning("tick quote failed for %s: %s", side_state.position.option_symbol, exc)
                continue
            if ltp > 0:
                tick_time = datetime.now()
                print(
                    f"[TICK] {tick_time} side={side} "
                    f"symbol={side_state.position.option_symbol} "
                    f"ltp={float(ltp):.2f} sl={side_state.position.option_stop_level:.2f}"
                )
                self.engine.process_tick(side, float(ltp), tick_time)

    def run_forever(self) -> None:
        logger.info(
            "LiveFeedRunner starting (spot=%s exchange=%s tf=%sm)",
            self.cfg.spot_symbol, self.cfg.exchange_spot, self.cfg.timeframe_minutes,
        )
        _load_persisted_trade_alerts(self.engine, datetime.now().date())
        _print_persisted_trade_alerts(
            self.engine.strategy_name,
            datetime.now().date(),
            self.engine.cfg.option_index_symbol,
        )

        # ── Market-hours awareness ───────────────────────────────────────
        if not self._is_market_open():
            logger.info(
                "Market is closed — will sleep and resume at next session open."
            )
            while not self._is_market_open() and not self._stop.is_set():
                wait = _seconds_until_market_open(self.cfg)
                if self._wait_with_countdown(wait):
                    break

        try:
            self._poll_once()
            self._print_cycle_summary()
        except Exception as exc:
            logger.warning("initial poll failed: %s", exc)

        while not self._stop.is_set():
            # ── Skip poll if market is closed ────────────────────────────
            if not self._is_market_open():
                sleep_for = self._seconds_until_next_boundary() + 60.0
                logger.debug("market closed — sleeping %.1fs", sleep_for)
                if self._wait_with_countdown(sleep_for):
                    break
                continue

            sleep_for = self._seconds_until_next_boundary()
            logger.debug("sleeping %.1fs until next boundary", sleep_for)
            if self._wait_with_countdown(sleep_for):
                break
            try:
                self._poll_once()
                self._print_cycle_summary()
            except KeyboardInterrupt:
                break
            except Exception as exc:
                logger.exception("live loop iteration error: %s", exc)

    def _is_market_open(self) -> bool:
        """Return True if today is a weekday and current time falls within trading hours."""
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        open_t = datetime.combine(now.date(), self.cfg.market_open)
        close_t = datetime.combine(now.date(), self.cfg.market_close)
        return open_t <= now < close_t

    def _format_side_status(self, side: str) -> str:
        side_state = self.engine._side_state(side)
        symbol = side_state.option_symbol or "NOT LOCKED"
        lines = [f"│ {side}: {symbol}"]

        if self.engine._is_ema21_strategy():
            ema21 = f"{side_state.last_ema21:.1f}" if side_state.last_ema21 is not None else "--"
            ltp = f"{side_state.last_close:.1f}" if side_state.last_close is not None else "--"
            lines.append(f"│     LTP={ltp}  EMA21={ema21}")
            setup_status = self.engine.signal_provider.format_setup_status(side_state)
            if setup_status:
                lines.append(f"│     Setup: {setup_status}")
            if side_state.position is not None:
                pos = side_state.position
                current_ltp = self.engine.broker.get_ltp(pos.option_symbol)
                pnl_entry = self.engine._pnl_entry_price(pos)
                unrealized_pnl = (current_ltp - pnl_entry) * pos.quantity
                lines.append(
                    f"│     Trade: LONG entry={pos.entry_price:.2f} current={current_ltp:.2f} "
                    f"SL={pos.option_stop_level:.2f} qty={pos.quantity}/{pos.initial_quantity} "
                    f"P&L={unrealized_pnl:+.2f}"
                )
            elif side_state.pending_entry is not None:
                pending = side_state.pending_entry
                lines.append(
                    f"│     Trade: PENDING trigger={pending.option_trigger_level:.2f} "
                    f"SL={pending.option_stop_level:.2f} qty={pending.quantity}"
                )
            elif side_state.order_submission_uncertain:
                lines.append("│     Trade: ORDER UNCERTAIN - reconcile OpenAlgo before retry")
            else:
                lines.append("│     Trade: FLAT")
            return "\n".join(lines)

        rsi_str = f"{side_state.last_rsi:.1f}" if side_state.last_rsi is not None else "--"
        e13 = f"{side_state.last_ema13:.1f}" if side_state.last_ema13 is not None else "--"
        e20 = f"{side_state.last_ema20:.1f}" if side_state.last_ema20 is not None else "--"
        e50 = f"{side_state.last_ema50:.1f}" if side_state.last_ema50 is not None else "--"
        ltp = f"{side_state.last_close:.1f}" if side_state.last_close is not None else "--"

        if (
            side_state.last_ema13 is not None
            and side_state.last_ema20 is not None
            and side_state.last_ema50 is not None
        ):
            trend = (
                "📈 BULL"
                if (side_state.last_ema13 > side_state.last_ema20 or side_state.last_ema20 > side_state.last_ema50)
                else "📉 BEAR"
            )
        else:
            trend = "--"

        lines.append(f"│     LTP={ltp}  RSI={rsi_str}  EMA13={e13}  EMA20={e20}  EMA50={e50}  {trend}")

        setup_status = self.engine.signal_provider.format_setup_status(side_state)
        if setup_status:
            lines.append(f"│     Setup: {setup_status}")

        if side_state.position is not None:
            pos = side_state.position
            lines.append(
                f"│     Trade: 🟡 LONG  entry={pos.entry_price:.1f}  SL={pos.option_stop_level:.1f}"
                f"  qty={pos.quantity}/{pos.initial_quantity}  BE={'Y' if pos.breakeven_armed else 'N'}"
            )
        elif side_state.pending_entry is not None:
            pend = side_state.pending_entry
            lines.append(
                f"│     Trade: ⏫ PENDING BUY  trigger={pend.option_trigger_level:.1f}"
                f"  SL={pend.option_stop_level:.1f}  qty={pend.quantity}"
            )
        else:
            lines.append(f"│     Trade: — FLAT")

        return "\n".join(lines)

    def _print_cycle_summary(self) -> None:
        now = datetime.now()
        state = self.engine.state
        if not state.atm_locked:
            print(f"\n[{now.strftime('%H:%M:%S')}] Waiting for ATM lock (need spot price at {self.cfg.atm_lock_time})...")
            return

        ce_status = self._format_side_status("CE")
        pe_status = self._format_side_status("PE")

        print(f"\n┌─── {now.strftime('%H:%M:%S')} ─── Strategy Status {'─' * 30}┐")
        print(f"│ Strikes: {state.ce_symbol} / {state.pe_symbol}")
        unrealized_pnl = self.engine._get_unrealized_pnl()
        print(
            f"│ SL hits: {state.sl_hits_today}/{self.engine.risk.max_sl_per_day}"
            f"   Entries today: {self.engine.total_entries}"
            f"   PnL: {self.engine.realized_pnl + unrealized_pnl:+.1f}"
        )
        today_alerts = [
            alert for alert in self.engine.alerts
            if alert.timestamp.date() == state.trading_day
            and alert.category in ("ENTRY", "EXIT")
        ]
        for category in ("ENTRY", "EXIT"):
            matching = [alert for alert in today_alerts if alert.category == category]
            latest = matching[-1] if matching else None
            if latest is not None:
                print(f"│ Last {category.lower()}: [{latest.timestamp.strftime('%H:%M:%S')}] {latest.message}")
            else:
                print(f"│ Last {category.lower()}: --")
        if today_alerts:
            print("│ Trades today:")
            for alert in today_alerts:
                print(f"│   [{alert.timestamp.strftime('%H:%M:%S')}] {alert.category}: {alert.message}")
        print(f"├{'─' * 62}┤")
        print(ce_status)
        print(pe_status)
        print(f"└{'─' * 62}┘")


# ===============================================================
#  Multi-engine live feed runner
# ===============================================================


class MultiEngineLiveFeedRunner:
    """Feeds same candle data to multiple independent engines."""

    def __init__(
        self,
        engines: list[tuple[str, BaseStrategyEngine]],
        broker: OpenAlgoBroker,
        cfg: StrategyConfig,
        lookback_days: int = 5,
        poll_slack_seconds: int = 5,
    ) -> None:
        self.engines = engines  # [(name, engine), ...]
        self.broker = broker
        self.cfg = cfg
        self.lookback_days = lookback_days
        self.poll_slack_seconds = poll_slack_seconds
        self._stop = threading.Event()
        self._last_bar_time: dict[str, Optional[datetime]] = {"CE": None, "PE": None}
        self._startup_baselined: set[str] = set()

    def stop(self) -> None:
        self._stop.set()

    def _try_lock_atm(self, now: datetime) -> None:
        first_engine = self.engines[0][1]
        if first_engine.state.atm_locked:
            return
        if _restore_atm_lock(first_engine, now.date()):
            lock_ts = datetime.combine(now.date(), self.cfg.atm_lock_time)
            for _, engine in self.engines[1:]:
                engine.on_day_transition_if_needed(lock_ts)
                engine.state.ce_symbol = first_engine.state.ce_symbol
                engine.state.pe_symbol = first_engine.state.pe_symbol
                engine.state.ce.option_symbol = first_engine.state.ce_symbol
                engine.state.pe.option_symbol = first_engine.state.pe_symbol
                engine.state.atm_locked = True
            for _, engine in self.engines:
                _restore_open_positions(engine, self.broker, now.date())
            return
        if _restore_atm_lock_from_positions(first_engine, self.broker, now.date()):
            lock_ts = datetime.combine(now.date(), self.cfg.atm_lock_time)
            for _, engine in self.engines[1:]:
                engine.on_day_transition_if_needed(lock_ts)
                engine.state.ce_symbol = first_engine.state.ce_symbol
                engine.state.pe_symbol = first_engine.state.pe_symbol
                engine.state.ce.option_symbol = first_engine.state.ce_symbol
                engine.state.pe.option_symbol = first_engine.state.pe_symbol
                engine.state.atm_locked = True
            for _, engine in self.engines:
                _restore_open_positions(engine, self.broker, now.date())
            return
        if now.time() < self.cfg.atm_lock_time:
            return
        try:
            spot_ltp = self.broker.get_ltp(self.cfg.spot_symbol)
        except Exception as exc:
            logger.warning("spot LTP fetch failed while locking ATM: %s", exc)
            return
        if not spot_ltp:
            logger.warning("spot LTP came back 0/None — will retry next poll")
            return
        lock_ts = datetime.combine(now.date(), self.cfg.atm_lock_time)
        for _, engine in self.engines:
            engine.on_day_transition_if_needed(lock_ts)
            engine.lock_atm_for_day(lock_ts, float(spot_ltp))
            _restore_open_positions(engine, self.broker, now.date())
        _persist_atm_lock(first_engine, float(spot_ltp))

    def _fetch_option_history(self, option_symbol: str) -> pd.DataFrame:
        today = datetime.now().date()
        start = (today - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        interval = f"{self.cfg.timeframe_minutes}m"
        raw = self.broker.fetch_history(
            symbol=option_symbol,
            exchange=self.cfg.exchange_options,
            interval=interval,
            start_date=start,
            end_date=end,
        )
        base = _normalize_history_df(raw)
        if base.empty:
            return base
        base = add_indicators(base.reset_index(drop=True), self.cfg)
        session_start = datetime.combine(today, self.cfg.market_open)
        session_end = datetime.combine(today, self.cfg.market_close)
        base = base[(base["datetime"] >= session_start) & (base["datetime"] < session_end)]
        return base.reset_index(drop=True)

    def _seconds_until_next_boundary(self) -> float:
        now = datetime.now()
        tf = self.cfg.timeframe_minutes
        boundary_min = ((now.minute // tf) + 1) * tf
        next_ts = now.replace(second=0, microsecond=0)
        if boundary_min >= 60:
            next_ts = next_ts.replace(minute=0) + timedelta(hours=1)
        else:
            next_ts = next_ts.replace(minute=boundary_min)
        return max(1.0, (next_ts - now).total_seconds() + self.poll_slack_seconds)

    def _process_new_bars_for_side(self, side: str, data: pd.DataFrame) -> None:
        if data.empty:
            return
        now = datetime.now()
        tf_delta = timedelta(minutes=self.cfg.timeframe_minutes)
        closed = data[data["datetime"] + tf_delta <= now]
        if closed.empty:
            return

        last_ts = self._last_bar_time.get(side)
        if side not in self._startup_baselined and last_ts is None:
            latest_ts = closed["datetime"].iloc[-1]
            self._last_bar_time[side] = (
                latest_ts.to_pydatetime() if hasattr(latest_ts, "to_pydatetime") else latest_ts
            )
            self._startup_baselined.add(side)
            logger.info(
                "baselined %s at %s; historical bars will not create orders, "
                "new live signals remain enabled",
                side,
                self._last_bar_time[side],
            )
            return
        if last_ts is not None:
            closed = closed[closed["datetime"] > last_ts]
            if closed.empty:
                return

        for i, (_, row) in enumerate(closed.iterrows()):
            row_idx = row.name if hasattr(row, "name") else None
            prev_row: Optional[pd.Series] = None
            if row_idx is None:
                first_idx = closed.index[0]
                pos_in_full = data.index.get_loc(first_idx) + i
            else:
                pos_in_full = data.index.get_loc(row_idx)
            if pos_in_full > 0:
                prev_row = data.iloc[pos_in_full - 1]
            for _, engine in self.engines:
                engine.process_option_candle(side, row, prev_row)
            ts = row["datetime"]
            self._last_bar_time[side] = (
                ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            )

    def _poll_once(self) -> None:
        now = datetime.now()
        self._try_lock_atm(now)
        first_engine = self.engines[0][1]
        if not first_engine.state.atm_locked:
            return
        for _, engine in self.engines:
            if any(
                engine._side_state(side).order_submission_uncertain
                for side in ("CE", "PE")
            ):
                _restore_open_positions(engine, self.broker, now.date())

        for side, symbol in (
            ("CE", first_engine.state.ce_symbol),
            ("PE", first_engine.state.pe_symbol),
        ):
            if not symbol:
                continue
            try:
                data = self._fetch_option_history(symbol)
            except Exception as exc:
                logger.warning("history fetch failed for %s %s: %s", side, symbol, exc)
                continue
            self._process_new_bars_for_side(side, data)

    def _wait_with_countdown(self, seconds: float) -> bool:
        import sys
        deadline = datetime.now() + timedelta(seconds=seconds)
        while not self._stop.is_set():
            remaining = (deadline - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            self._poll_active_ticks()
            mins, secs = divmod(int(remaining), 60)
            sys.stdout.write(f"\r⏳ Next candle in {mins:02d}:{secs:02d} ")
            sys.stdout.flush()
            if self._stop.wait(min(1.0, remaining)):
                sys.stdout.write("\r" + " " * 30 + "\r")
                sys.stdout.flush()
                return True
        sys.stdout.write("\r" + " " * 30 + "\r")
        sys.stdout.flush()
        return False

    def _poll_active_ticks(self) -> None:
        now = datetime.now()
        seen_symbols: set[str] = set()
        for _, engine in self.engines:
            for side in ("CE", "PE"):
                position = engine._side_state(side).position
                if position is None or position.option_symbol in seen_symbols:
                    continue
                seen_symbols.add(position.option_symbol)
                try:
                    ltp = self.broker.get_ltp(position.option_symbol)
                except Exception as exc:
                    logger.warning("tick quote failed for %s: %s", position.option_symbol, exc)
                    continue
                if ltp > 0:
                    print(
                        f"[TICK] {now} symbol={position.option_symbol} "
                        f"ltp={float(ltp):.2f} sl={position.option_stop_level:.2f}"
                    )
                    for _, active_engine in self.engines:
                        for active_side in ("CE", "PE"):
                            active_position = active_engine._side_state(active_side).position
                            if active_position is not None and active_position.option_symbol == position.option_symbol:
                                active_engine.process_tick(active_side, float(ltp), now)

    def run_forever(self) -> None:
        names = ", ".join(n for n, _ in self.engines)
        logger.info(
            "MultiEngineLiveFeedRunner starting [%s] (spot=%s tf=%sm)",
            names, self.cfg.spot_symbol, self.cfg.timeframe_minutes,
        )
        for engine in self.engines:
            _load_persisted_trade_alerts(engine, datetime.now().date())
            _print_persisted_trade_alerts(
                engine.strategy_name,
                datetime.now().date(),
                engine.cfg.option_index_symbol,
            )

        # ── Market-hours awareness ───────────────────────────────────────
        if not self._is_market_open():
            logger.info(
                "Market is closed — will sleep and resume at next session open."
            )
            while not self._is_market_open() and not self._stop.is_set():
                wait = _seconds_until_market_open(self.cfg)
                if self._wait_with_countdown(wait):
                    break

        try:
            self._poll_once()
            self._print_cycle_summary()
        except Exception as exc:
            logger.warning("initial poll failed: %s", exc)

        while not self._stop.is_set():
            # ── Skip poll if market is closed ────────────────────────────
            if not self._is_market_open():
                sleep_for = self._seconds_until_next_boundary() + 60.0
                logger.debug("market closed — sleeping %.1fs", sleep_for)
                if self._wait_with_countdown(sleep_for):
                    break
                continue

            sleep_for = self._seconds_until_next_boundary()
            if self._wait_with_countdown(sleep_for):
                break
            try:
                self._poll_once()
                self._print_cycle_summary()
            except KeyboardInterrupt:
                break
            except Exception as exc:
                logger.exception("live loop iteration error: %s", exc)

    def _is_market_open(self) -> bool:
        """Return True if today is a weekday and current time falls within trading hours."""
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        open_t = datetime.combine(now.date(), self.cfg.market_open)
        close_t = datetime.combine(now.date(), self.cfg.market_close)
        return open_t <= now < close_t

    def _print_cycle_summary(self) -> None:
        now = datetime.now()
        first_engine = self.engines[0][1]
        state = first_engine.state
        if not state.atm_locked:
            print(f"\n[{now.strftime('%H:%M:%S')}] Waiting for ATM lock...")
            return

        print(f"\n┌─── {now.strftime('%H:%M:%S')} ─── Multi-Strategy Status {'─' * 24}┐")
        print(f"│ Strikes: {state.ce_symbol} / {state.pe_symbol}")
        for name, engine in self.engines:
            pnl = engine.realized_pnl
            entries = engine.total_entries
            sl = engine.state.sl_hits_today
            print(
                f"│ [{name.upper()}] Entries={entries}  SL_hits={sl}/{engine.risk.max_sl_per_day}"
                f"  PnL={pnl:+.1f}"
            )
            for side in ("CE", "PE"):
                ss = engine._side_state(side)
                setup = engine.signal_provider.format_setup_status(ss)
                if ss.position:
                    pos = ss.position
                    trade = (
                        f"LONG entry={pos.entry_price:.1f} SL={pos.option_stop_level:.1f} "
                        f"qty={pos.quantity}/{pos.initial_quantity}"
                    )
                elif ss.pending_entry:
                    trade = f"PENDING trigger={ss.pending_entry.option_trigger_level:.1f}"
                else:
                    trade = "FLAT"
                print(f"│   {side}: {trade}  | {setup}")
            today_alerts = [
                alert for alert in engine.alerts
                if alert.timestamp.date() == state.trading_day
                and alert.category in ("ENTRY", "EXIT")
            ]
            for alert in today_alerts:
                print(f"│   [{alert.timestamp.strftime('%H:%M:%S')}] {alert.category}: {alert.message}")
        print(f"└{'─' * 62}┘")


# ===============================================================
#  Historical replay
# ===============================================================


def _fetch_history_df(
    broker: OpenAlgoBroker,
    symbol: str,
    exchange: str,
    interval: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    raw = broker.fetch_history(
        symbol=symbol, exchange=exchange, interval=interval,
        start_date=start_date, end_date=end_date,
    )
    return _normalize_history_df(raw)


def _iter_trading_days(spot_df: pd.DataFrame) -> list[date]:
    return sorted({ts.date() for ts in spot_df["datetime"]})


def _slice_session(df: pd.DataFrame, day: date, cfg: StrategyConfig) -> pd.DataFrame:
    session_start = datetime.combine(day, cfg.market_open)
    session_end = datetime.combine(day, cfg.market_close)
    sub = df[(df["datetime"] >= session_start) & (df["datetime"] < session_end)]
    return sub.reset_index(drop=True)


def _warmup_and_slice(df: pd.DataFrame, day: date, cfg: StrategyConfig) -> pd.DataFrame:
    if df.empty:
        return df
    full = add_indicators(df.reset_index(drop=True), cfg)
    session_start = datetime.combine(day, cfg.market_open)
    session_end = datetime.combine(day, cfg.market_close)
    sliced = full[(full["datetime"] >= session_start) & (full["datetime"] < session_end)]
    return sliced.reset_index(drop=True)


def _find_atm_lock_price(spot_day: pd.DataFrame, cfg: StrategyConfig) -> Optional[float]:
    target = cfg.atm_lock_time
    for _, row in spot_day.iterrows():
        if row["datetime"].time() == target:
            return float(row["open"])
        if row["datetime"].time() > target:
            return float(row["open"])
    return None


def _write_verbose_trace_csv(trace_rows: list[dict], csv_path: str) -> None:
    if not trace_rows:
        logger.warning("verbose trace CSV skipped: no rows to write")
        return
    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(trace_rows).to_csv(out_path, index=False)
    logger.info("verbose trace CSV saved: %s (%d rows)", out_path, len(trace_rows))


def run_historical_replay(
    cfg: StrategyConfig,
    risk: RiskConfig,
    signal_provider: SignalProvider,
    start_date: str,
    end_date: str,
    diagnose: bool = False,
    verbose: bool = False,
    verbose_csv_path: Optional[str] = None,
) -> None:
    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        raise SystemExit("OPENALGO_API_KEY not set (check .env)")
    host = (
        os.getenv("OPENALGO_HOST")
        or os.getenv("OPENALGO_URL")
        or "http://127.0.0.1:5002"
    )
    history_broker = OpenAlgoBroker(api_key=api_key, host=host, dry_run=True)

    interval = f"{cfg.timeframe_minutes}m"
    logger.info(
        "replay: fetching spot %s %s %s [%s -> %s]",
        cfg.spot_symbol, cfg.exchange_spot, interval, start_date, end_date,
    )
    spot_df = _fetch_history_df(
        history_broker, cfg.spot_symbol, cfg.exchange_spot, interval, start_date, end_date,
    )
    if spot_df.empty:
        raise SystemExit("replay: no spot bars returned")
    logger.info(
        "replay: %d spot bars from %s to %s",
        len(spot_df), spot_df["datetime"].iloc[0], spot_df["datetime"].iloc[-1],
    )

    broker = HistoricalReplayBroker()
    engine = BaseStrategyEngine(cfg, risk, broker, signal_provider)
    engine.diagnose = diagnose
    engine.verbose = verbose
    engine.capture_trace = bool(verbose_csv_path)

    total_bars = 0
    skipped_days = 0
    for day in _iter_trading_days(spot_df):
        spot_day = _slice_session(spot_df, day, cfg)
        if spot_day.empty:
            continue

        atm_price = _find_atm_lock_price(spot_day, cfg)
        if atm_price is None:
            logger.warning("replay %s: no bar at/after %s — skipping day", day, cfg.atm_lock_time)
            skipped_days += 1
            continue

        engine.reset_for_new_day(day)
        lock_ts = datetime.combine(day, cfg.atm_lock_time)
        if not _restore_atm_lock_from_alerts(engine, day):
            atm_strike = get_atm_strike(atm_price, cfg.strike_step)
            expiry_day = history_broker.resolve_nearest_expiry(
                cfg.option_index_symbol,
                day,
                atm_strike,
                cfg.strike_step,
                preferred_weekday=cfg.weekly_expiry_weekday,
                expiry_policy=cfg.expiry_policy,
            )
            engine.lock_atm_for_day(lock_ts, atm_price, expiry_day_override=expiry_day)
        ce_sym = engine.state.ce_symbol
        pe_sym = engine.state.pe_symbol
        assert ce_sym and pe_sym

        warmup_start = (day - timedelta(days=5)).strftime("%Y-%m-%d")
        day_str = day.strftime("%Y-%m-%d")
        try:
            ce_raw, pe_raw, resolved_ce, resolved_pe, off = _resolve_option_pair_history(
                history_broker,
                ce_sym,
                pe_sym,
                cfg.exchange_options,
                interval,
                warmup_start,
                day_str,
                cfg.strike_step,
            )
            if off != 0:
                logger.warning(
                    "replay %s: ATM strike history missing; fallback offset=%+d used (CE=%s PE=%s)",
                    day,
                    off,
                    resolved_ce,
                    resolved_pe,
                )
            ce_sym = resolved_ce
            pe_sym = resolved_pe
            engine.state.ce_symbol = resolved_ce
            engine.state.pe_symbol = resolved_pe
            engine.state.ce.option_symbol = resolved_ce
            engine.state.pe.option_symbol = resolved_pe
        except Exception as exc:
            logger.warning("replay %s: option history fetch failed (%s) — skipping day", day, exc)
            skipped_days += 1
            continue

        if ce_raw.empty or pe_raw.empty:
            logger.warning(
                "replay %s: empty option history (CE=%d PE=%d) — skipping day",
                day, len(ce_raw), len(pe_raw),
            )
            skipped_days += 1
            continue

        ce_day = _warmup_and_slice(ce_raw, day, cfg)
        pe_day = _warmup_and_slice(pe_raw, day, cfg)

        ce_events = [("CE", row) for _, row in ce_day.iterrows()]
        pe_events = [("PE", row) for _, row in pe_day.iterrows()]
        spot_events = [("SPOT", row) for _, row in spot_day.iterrows()]
        events = ce_events + pe_events + spot_events
        events.sort(key=lambda ev: ev[1]["datetime"])

        prev_by_side: dict[str, Optional[pd.Series]] = {"CE": None, "PE": None}
        for side, row in events:
            if side == "SPOT":
                broker.set_current_bar(cfg.spot_symbol, row)
                continue
            symbol = ce_sym if side == "CE" else pe_sym
            broker.set_current_bar(symbol, row)
            engine.process_option_candle(side, row, prev_by_side[side])
            prev_by_side[side] = row
            total_bars += 1

        eod_ts = datetime.combine(day, cfg.force_square_off)
        engine.force_square_off_side(engine.state.ce, eod_ts)
        engine.force_square_off_side(engine.state.pe, eod_ts)

    snap = engine.get_status_snapshot()
    print("\n" + "=" * 72)
    print("REPLAY SUMMARY")
    print("=" * 72)
    print(f"Spot symbol       : {cfg.spot_symbol} / {cfg.exchange_spot}")
    print(f"Timeframe         : {cfg.timeframe_minutes}m")
    print(f"Window            : {start_date} -> {end_date}")
    print(f"Days replayed     : {len(_iter_trading_days(spot_df)) - skipped_days}")
    print(f"Days skipped      : {skipped_days}")
    print(f"Option bars fed   : {total_bars}")
    print(f"Total entries     : {snap['total_entries']}")
    print(f"Hard SL hits      : {snap['total_hard_sl_hits']}")
    print(f"Realized PnL (INR): {snap['realized_pnl']:.2f}")
    print("=" * 72)

    entries = [a for a in engine.alerts if a.category == "ENTRY"]
    exits = [a for a in engine.alerts if a.category == "EXIT"]
    management_events = [a for a in engine.alerts if a.category in {"TARGET", "TSL"}]

    print("\n─── Trade Log ─────────────────────────────────────────────")
    trade_events = sorted(
        [(evt.timestamp, "ENTRY", i + 1, evt) for i, evt in enumerate(entries)]
        + [(evt.timestamp, "EXIT", i + 1, evt) for i, evt in enumerate(exits)]
        + [(evt.timestamp, evt.category, None, evt) for evt in management_events],
        key=lambda event: event[0],
    )
    for _, event_type, event_number, evt in trade_events:
        ts = evt.timestamp.strftime("%H:%M:%S") if hasattr(evt.timestamp, "strftime") else str(evt.timestamp)
        number = f" #{event_number}" if event_number is not None else ""
        msg = evt.message or ""
        display_type = event_type
        if event_type == "EXIT":
            lower = msg.lower()
            if "breakeven" in lower:
                display_type = "BE STOP"
            elif "forced square-off" in lower or "force" in lower:
                display_type = "FORCED SQ OFF"
            elif "stop hit" in lower or "hard sl" in lower:
                display_type = "HARD SL"
        print(f"  [{ts}] {display_type}{number}  {msg}")

    print("\n─── Summary ───────────────────────────────────────────────")
    print(f"Total entries     : {len(entries)}")
    print(f"Total exits       : {len(exits)}")
    print("=" * 72)

    if verbose_csv_path:
        _write_verbose_trace_csv(engine.trace_rows, verbose_csv_path)


def run_multi_historical_replay(
    cfg: StrategyConfig,
    risk: RiskConfig,
    providers: list[tuple[str, SignalProvider]],
    start_date: str,
    end_date: str,
    diagnose: bool = False,
    verbose: bool = False,
    verbose_csv_path: Optional[str] = None,
) -> None:
    """Run multiple independent engines over the same historical data (single fetch)."""
    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        raise SystemExit("OPENALGO_API_KEY not set (check .env)")
    host = (
        os.getenv("OPENALGO_HOST")
        or os.getenv("OPENALGO_URL")
        or "http://127.0.0.1:5002"
    )
    history_broker = OpenAlgoBroker(api_key=api_key, host=host, dry_run=True)

    interval = f"{cfg.timeframe_minutes}m"
    spot_df = _fetch_history_df(
        history_broker, cfg.spot_symbol, cfg.exchange_spot, interval, start_date, end_date,
    )
    if spot_df.empty:
        raise SystemExit("replay: no spot bars returned")

    engines: list[tuple[str, BaseStrategyEngine, HistoricalReplayBroker]] = []
    for name, provider in providers:
        broker = HistoricalReplayBroker()
        engine = BaseStrategyEngine(cfg, risk, broker, provider)
        engine.diagnose = diagnose
        engine.verbose = verbose
        engine.capture_trace = bool(verbose_csv_path)
        engines.append((name, engine, broker))

    skipped_days = 0
    total_bars = 0
    for day in _iter_trading_days(spot_df):
        spot_day = _slice_session(spot_df, day, cfg)
        if spot_day.empty:
            continue

        atm_price = _find_atm_lock_price(spot_day, cfg)
        if atm_price is None:
            skipped_days += 1
            continue

        lock_ts = datetime.combine(day, cfg.atm_lock_time)
        for _, engine, _ in engines:
            engine.reset_for_new_day(day)
        if not _restore_atm_lock_from_alerts(engines[0][1], day):
            atm_strike = get_atm_strike(atm_price, cfg.strike_step)
            expiry_day = history_broker.resolve_nearest_expiry(
                cfg.option_index_symbol,
                day,
                atm_strike,
                cfg.strike_step,
                preferred_weekday=cfg.weekly_expiry_weekday,
                expiry_policy=cfg.expiry_policy,
            )
            engines[0][1].lock_atm_for_day(lock_ts, atm_price, expiry_day_override=expiry_day)
        for _, engine, _ in engines[1:]:
            engine.state.ce_symbol = engines[0][1].state.ce_symbol
            engine.state.pe_symbol = engines[0][1].state.pe_symbol
            engine.state.ce.option_symbol = engine.state.ce_symbol
            engine.state.pe.option_symbol = engine.state.pe_symbol
            engine.state.atm_locked = True

        # All engines share the same ATM symbols
        ce_sym = engines[0][1].state.ce_symbol
        pe_sym = engines[0][1].state.pe_symbol
        assert ce_sym and pe_sym

        warmup_start = (day - timedelta(days=5)).strftime("%Y-%m-%d")
        day_str = day.strftime("%Y-%m-%d")
        try:
            ce_raw, pe_raw, resolved_ce, resolved_pe, off = _resolve_option_pair_history(
                history_broker,
                ce_sym,
                pe_sym,
                cfg.exchange_options,
                interval,
                warmup_start,
                day_str,
                cfg.strike_step,
            )
            if off != 0:
                logger.warning(
                    "replay %s: ATM strike history missing; fallback offset=%+d used (CE=%s PE=%s)",
                    day,
                    off,
                    resolved_ce,
                    resolved_pe,
                )
            ce_sym = resolved_ce
            pe_sym = resolved_pe
            for _, engine, _ in engines:
                engine.state.ce_symbol = resolved_ce
                engine.state.pe_symbol = resolved_pe
                engine.state.ce.option_symbol = resolved_ce
                engine.state.pe.option_symbol = resolved_pe
        except Exception as exc:
            logger.warning("replay %s: option history fetch failed (%s) — skipping", day, exc)
            skipped_days += 1
            continue

        if ce_raw.empty or pe_raw.empty:
            skipped_days += 1
            continue

        ce_day = _warmup_and_slice(ce_raw, day, cfg)
        pe_day = _warmup_and_slice(pe_raw, day, cfg)

        ce_events = [("CE", row) for _, row in ce_day.iterrows()]
        pe_events = [("PE", row) for _, row in pe_day.iterrows()]
        spot_events = [("SPOT", row) for _, row in spot_day.iterrows()]
        events = ce_events + pe_events + spot_events
        events.sort(key=lambda ev: ev[1]["datetime"])

        prev_by_side: dict[str, Optional[pd.Series]] = {"CE": None, "PE": None}
        for side, row in events:
            if side == "SPOT":
                for _, _, broker in engines:
                    broker.set_current_bar(cfg.spot_symbol, row)
                continue
            symbol = ce_sym if side == "CE" else pe_sym
            for _, engine, broker in engines:
                broker.set_current_bar(symbol, row)
                engine.process_option_candle(side, row, prev_by_side[side])
            prev_by_side[side] = row
            total_bars += 1

        eod_ts = datetime.combine(day, cfg.force_square_off)
        for _, engine, _ in engines:
            engine.force_square_off_side(engine.state.ce, eod_ts)
            engine.force_square_off_side(engine.state.pe, eod_ts)

    # Print combined summary
    days_replayed = len(_iter_trading_days(spot_df)) - skipped_days
    print("\n" + "=" * 72)
    print("MULTI-STRATEGY REPLAY SUMMARY")
    print("=" * 72)
    print(f"Spot symbol       : {cfg.spot_symbol} / {cfg.exchange_spot}")
    print(f"Timeframe         : {cfg.timeframe_minutes}m")
    print(f"Window            : {start_date} -> {end_date}")
    print(f"Days replayed     : {days_replayed}")
    print(f"Days skipped      : {skipped_days}")
    print(f"Option bars fed   : {total_bars}")
    print("-" * 72)

    combined_pnl = 0.0
    for name, engine, _ in engines:
        snap = engine.get_status_snapshot()
        combined_pnl += snap["realized_pnl"]
        print(f"\n  [{name.upper()}]")
        print(f"    Entries       : {snap['total_entries']}")
        print(f"    Hard SL hits  : {snap['total_hard_sl_hits']}")
        print(f"    Realized PnL  : {snap['realized_pnl']:.2f}")

        entry_alerts = [a for a in engine.alerts if a.category == "ENTRY"]
        exit_alerts = [a for a in engine.alerts if a.category == "EXIT"]
        management_events = [a for a in engine.alerts if a.category in {"TARGET", "TSL"}]
        trade_events = sorted(
            [(evt.timestamp, "ENTRY", evt) for evt in entry_alerts]
            + [(evt.timestamp, "EXIT", evt) for evt in exit_alerts]
            + [(evt.timestamp, evt.category, evt) for evt in management_events],
            key=lambda event: event[0],
        )
        for _, event_type, evt in trade_events:
            ts = evt.timestamp.strftime("%H:%M:%S")
            print(f"      [{ts}] {event_type:<6} {evt.message}")

    print(f"\n{'─' * 72}")
    print(f"  COMBINED PnL    : {combined_pnl:.2f}")
    print("=" * 72)

    if verbose_csv_path:
        base = Path(verbose_csv_path)
        for name, engine, _ in engines:
            if len(engines) == 1:
                out_path = base
            else:
                out_path = base.with_name(f"{base.stem}_{name}{base.suffix or '.csv'}")
            _write_verbose_trace_csv(engine.trace_rows, str(out_path))
