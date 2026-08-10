from __future__ import annotations

import logging
import os
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from core.broker import HistoricalReplayBroker, OpenAlgoBroker
from core.display import format_status_table, format_candle_table, format_candle_header, format_candle_footer, format_candle_data_with_status, save_candle_data, export_all_candles_to_csv, export_all_candles_to_single_csv
from core.engine import BaseStrategyEngine, get_atm_strike
from core.indicators import add_indicators
from core.models import RiskConfig, StrategyConfig
from strategies.base import SignalProvider

logger = logging.getLogger("core.runner")


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
        strategy_name: str = "UNKNOWN",
        lookback_days: int = 5,
        poll_slack_seconds: int = 5,
    ) -> None:
        self.engine = engine
        self.broker = broker
        self.cfg = cfg
        self.strategy_name = strategy_name
        self.lookback_days = lookback_days
        self.poll_slack_seconds = poll_slack_seconds
        self._stop = threading.Event()
        self._last_bar_time: dict[str, Optional[datetime]] = {"CE": None, "PE": None}
        self._candle_buffer: dict[str, list[dict]] = {"CE": [], "PE": []}
        self._header_printed: dict[str, bool] = {"CE": False, "PE": False}

    def stop(self) -> None:
        self._stop.set()
        self.export_candle_data()

    def export_candle_data(self, output_dir: str = "logs") -> None:
        """Export all buffered candle data to a SINGLE consolidated CSV file in logs/ directory.
        
        Format: trading_log_YYYYMMDD.csv
        Contains ALL candles from the entire trading session.
        
        Args:
            output_dir: Directory to save the CSV file (defaults to "logs")
        """
        # Prepare data structure for export: {symbol: {side: [candles]}}
        all_candles = {
            self.cfg.spot_symbol: {
                "CE": self._candle_buffer.get("CE", []),
                "PE": self._candle_buffer.get("PE", []),
            }
        }
        
        # Export to SINGLE consolidated CSV file
        filepath = export_all_candles_to_single_csv(all_candles, output_dir, "trading_log")
        
        if filepath:
            total = len(self._candle_buffer.get("CE", [])) + len(self._candle_buffer.get("PE", []))
            logger.info(
                "[EXPORT] Consolidated %d candles to %s",
                total, filepath
            )

    def _try_lock_atm(self, now: datetime) -> None:
        if self.engine.state.atm_locked:
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
            logger.debug("[%s] no data received", side)
            return
        now = datetime.now()
        tf_delta = timedelta(minutes=self.cfg.timeframe_minutes)
        closed = data[data["datetime"] + tf_delta <= now]
        if closed.empty:
            logger.debug("[%s] no closed bars yet (data has %d rows, checking closed bars)", side, len(data))
            return

        last_ts = self._last_bar_time.get(side)
        if last_ts is not None:
            closed = closed[closed["datetime"] > last_ts]
            if closed.empty:
                logger.debug("[%s] no new bars since %s", side, last_ts)
                return

        logger.info("[%s] processing %d new closed bar(s)", side, len(closed))
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
            
            # Print table header on first candle for this side
            if not self._header_printed[side]:
                logger.info("[%s] ╔════════════════════════════════════════════════════════════════════╗", side)
                logger.info("[%s] ║                    CANDLESTICK DATA - %s                          ║", side, side)
                logger.info("[%s] ╚════════════════════════════════════════════════════════════════════╝", side)
                header_lines = format_candle_header().split('\n')
                for line in header_lines:
                    logger.info("[%s] %s", side, line)
                self._header_printed[side] = True
            
            # Format candle row with status
            side_state = self.engine.state.ce if side == "CE" else self.engine.state.pe
            candle_row, rsi_val, status = format_candle_data_with_status(
                self.strategy_name, self.cfg.spot_symbol, side, row, side_state
            )
            logger.info("[%s] %s", side, candle_row)
            
            # Buffer candle data for file export
            self._candle_buffer[side].append({
                "datetime": self._last_bar_time[side],
                "strategy": self.strategy_name,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]) if "volume" in row else 0,
                "rsi": rsi_val,
                "ema13": float(row.get("ema13", 0)) if row.get("ema13") else None,
                "ema20": float(row.get("ema20", 0)) if row.get("ema20") else None,
                "ema50": float(row.get("ema50", 0)) if row.get("ema50") else None,
                "vwap": float(row.get("vwap", 0)) if row.get("vwap") else None,
                "status": status,
            })

    def _poll_once(self) -> None:
        now = datetime.now()
        self._try_lock_atm(now)
        if not self.engine.state.atm_locked:
            logger.debug("Poll: ATM not yet locked")
            return

        logger.debug("[POLL] fetching data for CE/PE symbols")
        for side, symbol in (
            ("CE", self.engine.state.ce_symbol),
            ("PE", self.engine.state.pe_symbol),
        ):
            if not symbol:
                continue
            try:
                logger.debug("[POLL] fetching history for %s (%s)", symbol, side)
                data = self._fetch_option_history(symbol)
                logger.debug("[POLL] received %d rows for %s (%s)", len(data), symbol, side)
            except Exception as exc:
                logger.warning("history fetch failed for %s %s: %s", side, symbol, exc)
                continue
            self._process_new_bars_for_side(side, data)

    def _wait_with_countdown(self, seconds: float) -> bool:
        """Wait for specified seconds, checking for stop signal."""
        deadline = datetime.now() + timedelta(seconds=seconds)
        while not self._stop.is_set():
            remaining = (deadline - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            if self._stop.wait(min(1.0, remaining)):
                return True
        return False

    def run_forever(self) -> None:
        logger.info(
            "LiveFeedRunner starting (spot=%s exchange=%s tf=%sm)",
            self.cfg.spot_symbol, self.cfg.exchange_spot, self.cfg.timeframe_minutes,
        )

        # ── Market-hours awareness ───────────────────────────────────────
        if not self._is_market_open():
            logger.info(
                "Market is closed — will sleep and resume at next session open."
            )
            while not self._is_market_open() and not self._stop.is_set():
                wait = 3600.0  # 1 hour
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
        print(
            f"│ SL hits: {state.sl_hits_today}/{self.engine.risk.max_sl_per_day}"
            f"   Entries today: {self.engine.total_entries}"
            f"   PnL: {self.engine.realized_pnl:+.1f}"
        )
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
        self._candle_buffer: dict[str, list[dict]] = {"CE": [], "PE": []}
        self._header_printed: dict[str, bool] = {"CE": False, "PE": False}

    def stop(self) -> None:
        self._stop.set()
        self.export_candle_data()

    def export_candle_data(self, output_dir: str = "logs") -> None:
        """Export all buffered candle data to a SINGLE consolidated CSV file in logs/ directory.
        
        Format: trading_log_YYYYMMDD.csv
        Contains ALL symbols and sides from the entire trading session.
        
        Args:
            output_dir: Directory to save the CSV file (defaults to "logs")
        """
        # Prepare data structure for export: {symbol: {side: [candles]}}
        all_candles = {
            self.cfg.spot_symbol: {
                "CE": self._candle_buffer.get("CE", []),
                "PE": self._candle_buffer.get("PE", []),
            }
        }
        
        # Export to SINGLE consolidated CSV file
        filepath = export_all_candles_to_single_csv(all_candles, output_dir, "trading_log")
        
        if filepath:
            total = len(self._candle_buffer.get("CE", [])) + len(self._candle_buffer.get("PE", []))
            logger.info(
                "[EXPORT] Consolidated %d candles to %s",
                total, filepath
            )

    def _try_lock_atm(self, now: datetime) -> None:
        first_engine = self.engines[0][1]
        if first_engine.state.atm_locked:
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
            logger.debug("[%s] no data received", side)
            return
        now = datetime.now()
        tf_delta = timedelta(minutes=self.cfg.timeframe_minutes)
        closed = data[data["datetime"] + tf_delta <= now]
        if closed.empty:
            logger.debug("[%s] no closed bars yet (data has %d rows)", side, len(data))
            return

        last_ts = self._last_bar_time.get(side)
        if last_ts is not None:
            closed = closed[closed["datetime"] > last_ts]
            if closed.empty:
                logger.debug("[%s] no new bars since %s", side, last_ts)
                return

        logger.info("[%s] processing %d new closed bar(s) across %d engines", side, len(closed), len(self.engines))
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
            
            # Process candle for all engines
            for _, engine in self.engines:
                engine.process_option_candle(side, row, prev_row)
            
            ts = row["datetime"]
            self._last_bar_time[side] = (
                ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            )
            
            # Print table header on first candle for this side
            if not self._header_printed[side]:
                logger.info("[%s] ╔════════════════════════════════════════════════════════════════════╗", side)
                logger.info("[%s] ║                    CANDLESTICK DATA - %s                          ║", side, side)
                logger.info("[%s] ╚════════════════════════════════════════════════════════════════════╝", side)
                header_lines = format_candle_header().split('\n')
                for line in header_lines:
                    logger.info("[%s] %s", side, line)
                self._header_printed[side] = True
            
            # Log one row per engine/strategy
            for strategy_name, engine in self.engines:
                side_state = engine.state.ce if side == "CE" else engine.state.pe
                candle_row, rsi_val, status = format_candle_data_with_status(
                    strategy_name, self.cfg.spot_symbol, side, row, side_state
                )
                logger.info("[%s] %s", side, candle_row)
            
            # Buffer candle data for file export (just once per candle, for first engine)
            first_strategy, _ = self.engines[0]
            side_state = engine.state.ce if side == "CE" else engine.state.pe
            _, rsi_val, status = format_candle_data_with_status(
                first_strategy, self.cfg.spot_symbol, side, row, side_state
            )
            self._candle_buffer[side].append({
                "datetime": self._last_bar_time[side],
                "strategy": first_strategy,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]) if "volume" in row else 0,
                "rsi": rsi_val,
                "status": status,
            })

    def _poll_once(self) -> None:
        now = datetime.now()
        self._try_lock_atm(now)
        first_engine = self.engines[0][1]
        if not first_engine.state.atm_locked:
            logger.debug("Poll: ATM not yet locked")
            return

        logger.debug("[POLL] fetching data for CE/PE symbols")
        for side, symbol in (
            ("CE", first_engine.state.ce_symbol),
            ("PE", first_engine.state.pe_symbol),
        ):
            if not symbol:
                continue
            try:
                logger.debug("[POLL] fetching history for %s (%s)", symbol, side)
                data = self._fetch_option_history(symbol)
                logger.debug("[POLL] received %d rows for %s (%s)", len(data), symbol, side)
            except Exception as exc:
                logger.warning("history fetch failed for %s %s: %s", side, symbol, exc)
                continue
            self._process_new_bars_for_side(side, data)

    def _wait_with_countdown(self, seconds: float) -> bool:
        """Wait for specified seconds, checking for stop signal."""
        deadline = datetime.now() + timedelta(seconds=seconds)
        while not self._stop.is_set():
            remaining = (deadline - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            if self._stop.wait(min(1.0, remaining)):
                return True
        return False

    def run_forever(self) -> None:
        names = ", ".join(n for n, _ in self.engines)
        logger.info(
            "MultiEngineLiveFeedRunner starting [%s] (spot=%s tf=%sm)",
            names, self.cfg.spot_symbol, self.cfg.timeframe_minutes,
        )

        # ── Market-hours awareness ───────────────────────────────────────
        if not self._is_market_open():
            logger.info(
                "Market is closed — will sleep and resume at next session open."
            )
            while not self._is_market_open() and not self._stop.is_set():
                wait = 3600.0  # 1 hour
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
            logger.debug("[%s] Waiting for ATM lock at %s", self.cfg.spot_symbol, self.cfg.atm_lock_time)
            return

        # Collect status from all engines for tabular display
        engines_status = {}
        for name, engine in self.engines:
            engines_status[name.upper()] = engine.get_status_snapshot()
        
        # Display as formatted table
        print(format_status_table(self.cfg.spot_symbol, engines_status))


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
        atm_strike = get_atm_strike(atm_price, cfg.strike_step)
        expiry_day = history_broker.resolve_nearest_expiry(
            cfg.option_index_symbol,
            day,
            atm_strike,
            cfg.strike_step,
            preferred_weekday=cfg.weekly_expiry_weekday,
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

    print("\n─── Trade Log ─────────────────────────────────────────────")
    for i, evt in enumerate(entries):
        ts = evt.timestamp.strftime("%H:%M:%S") if hasattr(evt.timestamp, "strftime") else str(evt.timestamp)
        print(f"  [{ts}] ENTRY #{i+1}  {evt.message}")
    for i, evt in enumerate(exits):
        ts = evt.timestamp.strftime("%H:%M:%S") if hasattr(evt.timestamp, "strftime") else str(evt.timestamp)
        msg = evt.message or ""
        lower = msg.lower()
        if "breakeven" in lower:
            exit_type = "BE STOP"
        elif "forced square-off" in lower or "force" in lower:
            exit_type = "FORCED SQ OFF"
        elif "stop hit" in lower or "hard sl" in lower:
            exit_type = "HARD SL"
        else:
            exit_type = "EXIT"
        print(f"  [{ts}] {exit_type} #{i+1}  {msg}")

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
        atm_strike = get_atm_strike(atm_price, cfg.strike_step)
        expiry_day = history_broker.resolve_nearest_expiry(
            cfg.option_index_symbol,
            day,
            atm_strike,
            cfg.strike_step,
            preferred_weekday=cfg.weekly_expiry_weekday,
        )
        for _, engine, _ in engines:
            engine.reset_for_new_day(day)
            engine.lock_atm_for_day(lock_ts, atm_price, expiry_day_override=expiry_day)

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
        for evt in entry_alerts:
            ts = evt.timestamp.strftime("%H:%M:%S")
            print(f"      [{ts}] ENTRY  {evt.message}")
        for evt in exit_alerts:
            ts = evt.timestamp.strftime("%H:%M:%S")
            print(f"      [{ts}] EXIT   {evt.message}")

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
