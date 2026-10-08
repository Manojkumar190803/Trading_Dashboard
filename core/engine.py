from __future__ import annotations

import logging
import csv
import json
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from core.broker import BrokerInterface
from core.models import (
    BaseSideState,
    DayState,
    OrderSide,
    PendingEntry,
    Position,
    RiskConfig,
    Signal,
    StrategyAlert,
    StrategyConfig,
)
from core.signal_logger import SignalLogger
from strategies.base import SignalProvider

logger = logging.getLogger("core.engine")


def _shared_sl_count_path(trading_day: date) -> Path:
    configured = os.getenv("SHARED_SL_COUNT_FILE", "").strip()
    if configured:
        return Path(configured)
    return Path("logs") / f"sl_hits_{trading_day:%Y%m%d}.json"


def _read_shared_sl_count(trading_day: date) -> int:
    path = _shared_sl_count_path(trading_day)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return max(0, int(payload.get("count", 0))) if isinstance(payload, dict) else 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return 0


def _increment_shared_sl_count(trading_day: date) -> int:
    """Atomically increment the daily SL count shared by live containers."""
    path = _shared_sl_count_path(trading_day)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            try:
                payload = json.load(handle)
            except (json.JSONDecodeError, ValueError):
                payload = {}
            count = max(0, int(payload.get("count", 0))) + 1 if isinstance(payload, dict) else 1
            handle.seek(0)
            handle.truncate()
            json.dump({"trading_day": trading_day.isoformat(), "count": count}, handle)
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return count
    except (OSError, TypeError, ValueError):
        logger.exception("could not update shared SL count at %s", path)
        return _read_shared_sl_count(trading_day)


def get_atm_strike(spot_price: float, strike_step: int) -> int:
    return int(round(spot_price / strike_step) * strike_step)


def build_option_symbol(index_name: str, expiry_code: str, strike: int, option_type: str) -> str:
    return f"{index_name}{expiry_code}{strike}{option_type}"


def get_current_weekly_expiry(trade_day: date, expiry_weekday: int) -> date:
    days_ahead = (expiry_weekday - trade_day.weekday()) % 7
    return trade_day if days_ahead == 0 else trade_day.fromordinal(trade_day.toordinal() + days_ahead)


def choose_weekly_expiry_for_entry(trade_day: date, expiry_weekday: int) -> date:
    current_weekly_expiry = get_current_weekly_expiry(trade_day, expiry_weekday)
    if trade_day == current_weekly_expiry:
        return trade_day.fromordinal(trade_day.toordinal() + 7)
    return current_weekly_expiry


def choose_monthly_expiry_for_entry(trade_day: date, expiry_weekday: int) -> date:
    """Choose the last configured weekday in the current or next month."""
    month_end = trade_day.replace(day=28) + timedelta(days=4)
    month_end = month_end - timedelta(days=month_end.day)
    while month_end.weekday() != expiry_weekday:
        month_end -= timedelta(days=1)
    if month_end <= trade_day:
        next_month = month_end.replace(day=28) + timedelta(days=4)
        next_month_end = next_month - timedelta(days=next_month.day)
        while next_month_end.weekday() != expiry_weekday:
            next_month_end -= timedelta(days=1)
        return next_month_end
    return month_end


def format_expiry_code(expiry_day: date) -> str:
    return expiry_day.strftime("%d%b%y").upper()


class BaseStrategyEngine:
    """Strategy-agnostic trade engine. Signal logic is delegated to a SignalProvider."""

    def __init__(
        self,
        cfg: StrategyConfig,
        risk: RiskConfig,
        broker: BrokerInterface,
        signal_provider: SignalProvider,
    ) -> None:
        self.cfg = cfg
        self.risk = risk
        self.broker = broker
        self.signal_provider = signal_provider
        self.state = DayState()
        self.alerts: list[StrategyAlert] = []
        self.realized_pnl: float = 0.0
        self.last_processed_candle_time: Optional[datetime] = None
        self.total_entries: int = 0
        self.total_hard_sl_hits: int = 0
        self.diagnose: bool = False
        self.verbose: bool = False
        self._verbose_header_printed: bool = False
        self.capture_trace: bool = False
        self.trace_rows: list[dict[str, Any]] = []
        self.persist_alerts: bool = False

    @property
    def strategy_name(self) -> str:
        return self.signal_provider.__class__.__name__

    def _trace_enabled(self) -> bool:
        return self.verbose or self.capture_trace

    def _is_ema21_strategy(self) -> bool:
        return getattr(self.signal_provider, "strategy_key", None) == "ema21"

    def _round_option_price(self, price: float) -> float:
        tick_size = max(float(getattr(self.cfg, "option_tick_size", 0.05)), 0.0001)
        return round(round(float(price) / tick_size) * tick_size, 10)

    def _fmt_signal(self, signal: Signal) -> str:
        return signal.value if isinstance(signal, Signal) else str(signal)

    def _safe_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime().isoformat(sep=" ")
        if isinstance(value, datetime):
            return value.isoformat(sep=" ")
        if pd.isna(value):
            return None
        return value

    def _record_trace_row(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        signal: Signal,
        trade_initiated: bool,
        remark: str,
    ) -> None:
        if not self._trace_enabled():
            return

        trace = {
            "strategy": self.strategy_name,
            "script": side_state.option_symbol or (self.state.ce_symbol if side == "CE" else self.state.pe_symbol) or "",
            "spot_symbol": self.cfg.spot_symbol,
            "timestamp": self._safe_value(row.get("datetime")),
            "side": side,
            "signal": self._fmt_signal(signal),
            "trade_initiated": trade_initiated,
            "remark": remark,
            "sl_hits_today": self.state.sl_hits_today,
            "sl_cap": self.risk.max_sl_per_day,
            "atm_locked": self.state.atm_locked,
            "has_position": side_state.position is not None,
            "has_pending_entry": side_state.pending_entry is not None,
            "setup_status": self.signal_provider.format_setup_status(side_state),
        }

        for col, value in row.items():
            trace[str(col)] = self._safe_value(value)

        pos = side_state.position
        if pos is not None:
            trace.update(
                {
                    "position_symbol": pos.option_symbol,
                    "position_qty": pos.quantity,
                    "position_entry_price": pos.entry_price,
                    "position_stop": pos.option_stop_level,
                }
            )

        pend = side_state.pending_entry
        if pend is not None:
            trace.update(
                {
                    "pending_symbol": pend.option_symbol,
                    "pending_qty": pend.quantity,
                    "pending_trigger": pend.option_trigger_level,
                    "pending_stop": pend.option_stop_level,
                }
            )

        for attr in (
            "p1_price",
            "p1_rsi",
            "p1_candle_time",
            "p2_price",
            "p2_rsi",
            "p2_candle_time",
        ):
            if hasattr(side_state, attr):
                trace[attr] = self._safe_value(getattr(side_state, attr))

        self.trace_rows.append(trace)

    # ── helpers ──────────────────────────────────────────────────────

    def _record_alert(self, ts: datetime, category: str, message: str) -> None:
        if category in {"SIGNAL", "PENDING_ENTRY"} and any(
            alert.timestamp.date() == ts.date()
            and alert.category == category
            and alert.message == message
            for alert in self.alerts
        ):
            return
        self.alerts.append(StrategyAlert(timestamp=ts, category=category, message=message))
        if len(self.alerts) > 500:
            self.alerts = self.alerts[-500:]
        if self.persist_alerts and category in (
            "SIGNAL", "PENDING_ENTRY", "ENTRY", "EXIT", "TARGET", "SL", "CANCEL",
            "ORDER", "PROTECTIVE_SL", "TSL", "RISK", "REJECT", "FAILED", "ERROR", "UNCERTAIN_ENTRY",
        ):
            self._persist_trade_alert(ts, category, message)
        print(f"[ENGINE][{category}] {message}")

    def _sync_shared_sl_count(self, trading_day: date) -> None:
        if self.broker.is_replay:
            return
        self.state.sl_hits_today = max(
            self.state.sl_hits_today,
            _read_shared_sl_count(trading_day),
        )

    def restore_open_position(
        self,
        side: str,
        quantity: int,
        entry_price: float,
        entry_time: datetime,
        stop_level: float,
        entry_trigger: float,
        risk_points: float,
    ) -> None:
        """Restore broker-confirmed live state after a process restart."""
        side_state = self._side_state(side)
        if side_state.position is not None or quantity <= 0:
            return
        configured_initial_quantity = self.cfg.full_size_lots * self.cfg.option_lot_size
        initial_quantity = max(quantity, configured_initial_quantity)
        is_partial_position = quantity < initial_quantity
        side_state.position = Position(
            option_symbol=side_state.option_symbol or "",
            option_type=side,
            quantity=quantity,
            initial_quantity=initial_quantity,
            entry_price=entry_price,
            entry_time=entry_time,
            option_stop_level=stop_level,
            option_entry_trigger=entry_trigger,
            option_risk_points=risk_points,
            t2_done=is_partial_position,
            next_target_rr=(self.cfg.t2_rr + self.cfg.trailing_step_rr if is_partial_position else None),
            progress_status=(
                f"{self.cfg.t2_rr:.1f}R reached - half lot booked; "
                f"looking for {self.cfg.t2_rr + self.cfg.trailing_step_rr:.1f}R"
                if is_partial_position
                else "Monitoring position"
            ),
        )

    def _persist_trade_alert(self, ts: datetime, category: str, message: str) -> None:
        script = self.cfg.option_index_symbol or self.cfg.spot_symbol or "UNKNOWN"
        path = Path("logs") / f"trade_alerts_{script}_{ts:%Y%m%d}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not path.exists()
        alert_key = (ts.isoformat(sep=" "), self.strategy_name, category, message)
        if not needs_header:
            try:
                with path.open(newline="", encoding="utf-8") as handle:
                    for row in csv.DictReader(handle):
                        existing_key = (
                            row.get("timestamp", ""),
                            row.get("strategy", ""),
                            row.get("category", ""),
                            row.get("message", ""),
                        )
                        if existing_key == alert_key:
                            return
            except OSError as exc:
                logger.warning("could not check persisted alert duplicate: %s", exc)
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if needs_header:
                writer.writerow(("timestamp", "strategy", "category", "message"))
            writer.writerow((ts.isoformat(sep=" "), self.strategy_name, category, message))

    @staticmethod
    def _fmt_candle_context(row: pd.Series, symbol: str, ema21_only: bool = False) -> str:
        if ema21_only:
            ema21 = row.get("ema21")
            ema21_text = "NA" if ema21 is None or pd.isna(ema21) else f"{ema21:.2f}"
            ts = row.get("datetime")
            ts_str = ts.strftime("%Y-%m-%d %H:%M") if ts is not None else "?"
            return (
                f"  >> [{ts_str}] {symbol} O={row['open']:.2f} H={row['high']:.2f} "
                f"L={row['low']:.2f} C={row['close']:.2f} | EMA21={ema21_text}"
            )

        rsi = row.get("rsi3")
        ema13 = row.get("ema13")
        ema20 = row.get("ema20")
        ema50 = row.get("ema50")
        vwap = row.get("vwap")
        ts = row.get("datetime")
        ts_str = ts.strftime("%Y-%m-%d %H:%M") if ts is not None else "?"
        return (
            f"  >> [{ts_str}] {symbol} O={row['open']:.2f} H={row['high']:.2f} "
            f"L={row['low']:.2f} C={row['close']:.2f} | "
            f"RSI3={'NA' if (rsi is None or pd.isna(rsi)) else f'{rsi:.2f}'} "
            f"EMA13={'NA' if (ema13 is None or pd.isna(ema13)) else f'{ema13:.2f}'} "
            f"EMA20={'NA' if (ema20 is None or pd.isna(ema20)) else f'{ema20:.2f}'} "
            f"EMA50={'NA' if (ema50 is None or pd.isna(ema50)) else f'{ema50:.2f}'} "
            f"VWAP={'NA' if (vwap is None or pd.isna(vwap)) else f'{vwap:.2f}'}"
        )

    def _side_state(self, side: str) -> BaseSideState:
        return self.state.ce if side == "CE" else self.state.pe

    def _pnl_entry_price(self, pos: Position) -> float:
        return pos.entry_price

    def _broker_quantity(self, symbol: str) -> Optional[int]:
        if not getattr(self.broker, "requires_position_reconciliation", False):
            return None
        try:
            for position in self.broker.get_position_book():
                if str(position.get("symbol") or "") == symbol:
                    return int(float(position.get("quantity") or 0))
        except Exception as exc:
            logger.warning("position reconciliation failed for %s: %s", symbol, exc)
        return 0

    def _place_protective_stop(self, side: str, position: Position, ts: datetime) -> None:
        if self.broker.is_replay:
            return
        stop_level = self._round_option_price(position.option_stop_level)
        limit_level = self._round_option_price(
            max(self.cfg.option_tick_size, stop_level - self.cfg.stop_buffer_points)
        )

        # Reconcile before every submission so a delayed cancel or a restart
        # cannot leave multiple active protective sells for one position.
        try:
            open_orders = self.broker.get_open_orders()
        except Exception as exc:
            self._record_alert(
                ts, "RISK",
                f"{side} protective SL blocked: order check failed for {position.option_symbol}: {exc}",
            )
            return
        if open_orders is None:
            self._record_alert(
                ts, "RISK",
                f"{side} protective SL blocked: order check unavailable for {position.option_symbol}",
            )
            return

        protective_orders = [
            order for order in open_orders
            if str(order.get("symbol") or "") == position.option_symbol
            and str(order.get("action") or order.get("side") or "").upper() == "SELL"
        ]
        matching_order = next(
            (
                order for order in protective_orders
                if abs(float(order.get("trigger_price") or order.get("trigger") or 0) - stop_level)
                <= self.cfg.option_tick_size
                and int(float(order.get("quantity") or order.get("qty") or 0)) == position.quantity
            ),
            None,
        )
        if matching_order is not None:
            position.protective_stop_order_id = str(
                matching_order.get("orderid") or matching_order.get("order_id") or ""
            ) or None
            return

        cancelled_ids: set[str] = set()
        for existing_order in protective_orders:
            order_id = str(existing_order.get("orderid") or existing_order.get("order_id") or "")
            if not order_id or not self.broker.cancel_order(order_id):
                self._record_alert(
                    ts, "RISK",
                    f"{side} protective SL blocked: could not cancel existing order "
                    f"{order_id or '<unknown>'} for {position.option_symbol}",
                )
                return
            cancelled_ids.add(order_id)

        if cancelled_ids:
            try:
                remaining_orders = self.broker.get_open_orders()
            except Exception as exc:
                self._record_alert(
                    ts, "RISK",
                    f"{side} protective SL blocked: could not verify cancelled orders "
                    f"for {position.option_symbol}: {exc}",
                )
                return
            if remaining_orders is None:
                self._record_alert(
                    ts, "RISK",
                    f"{side} protective SL blocked: cancelled-order verification unavailable "
                    f"for {position.option_symbol}",
                )
                return
            still_open = {
                str(order.get("orderid") or order.get("order_id") or "")
                for order in remaining_orders
            }
            if cancelled_ids & still_open:
                self._record_alert(
                    ts, "RISK",
                    f"{side} protective SL blocked: cancelled order still active for "
                    f"{position.option_symbol}; will retry after broker confirmation",
                )
                return

        print(
            f"[TRADE PROTECTION] ABOUT TO PLACE SL ORDER side={side} "
            f"symbol={position.option_symbol} qty={position.quantity} "
            f"type=SL trigger={stop_level:.2f} limit={limit_level:.2f} time={ts}"
        )
        try:
            position.protective_stop_order_id = self.broker.place_stop_limit_order(
                position.option_symbol,
                OrderSide.SELL,
                position.quantity,
                trigger_price=stop_level,
                limit_price=limit_level,
            )
            self._record_alert(
                ts,
                "PROTECTIVE_SL",
                f"{side} protective SL placed for {position.option_symbol} "
                f"qty={position.quantity} trigger={stop_level:.2f} limit={limit_level:.2f} "
                f"order_id={position.protective_stop_order_id}",
            )
        except Exception as exc:
            self._record_alert(
                ts,
                "RISK",
                f"{side} protective SL submission failed for {position.option_symbol}; "
                f"manual protection required: {exc}",
            )

    def _refresh_protective_stop(self, side: str, position: Position, ts: datetime) -> None:
        """Modify the existing broker stop after its level or quantity changes."""
        order_id = position.protective_stop_order_id
        if not order_id:
            self._record_alert(
                ts, "RISK",
                f"{side} protective SL update blocked: existing order ID is missing "
                f"for {position.option_symbol}",
            )
            return

        stop_level = self._round_option_price(position.option_stop_level)
        limit_level = self._round_option_price(
            max(self.cfg.option_tick_size, stop_level - self.cfg.stop_buffer_points)
        )
        try:
            modified = self.broker.modify_stop_limit_order(
                order_id,
                position.option_symbol,
                OrderSide.SELL,
                position.quantity,
                trigger_price=stop_level,
                limit_price=limit_level,
            )
        except Exception as exc:
            modified = False
            logger.warning("%s protective SL modify failed for %s: %s", side, order_id, exc)
        if not modified:
            self._record_alert(
                ts, "RISK",
                f"{side} protective SL update failed for {position.option_symbol} "
                f"order_id={order_id}; existing SL was not replaced",
            )
            return
        self._record_alert(
            ts, "PROTECTIVE_SL",
            f"{side} protective SL modified for {position.option_symbol} "
            f"qty={position.quantity} trigger={stop_level:.2f} limit={limit_level:.2f} "
            f"order_id={order_id}",
        )

    def _get_unrealized_pnl(self) -> float:
        pnl = 0.0
        for side_state in (self.state.ce, self.state.pe):
            pos = side_state.position
            if pos is None:
                continue
            option_ltp = self.broker.get_ltp(pos.option_symbol)
            pnl += (option_ltp - self._pnl_entry_price(pos)) * pos.quantity
        return pnl

    def _exit_position(
        self,
        side_state: BaseSideState,
        ts: datetime,
        quantity: int,
        reason: str,
        is_hard_sl: bool = False,
        row: Optional[pd.Series] = None,
        refresh_protection: bool = True,
    ) -> None:
        pos = side_state.position
        if pos is None:
            return

        qty = min(quantity, pos.quantity)
        if qty <= 0:
            return

        broker_quantity = self._broker_quantity(pos.option_symbol)
        if broker_quantity is not None and broker_quantity < qty:
            side = pos.option_type
            self._record_alert(
                ts,
                "RISK",
                f"{side} exit blocked: broker quantity for {pos.option_symbol} is "
                f"{broker_quantity}, local long quantity is {qty}",
            )
            return

        exit_ltp = self.broker.get_ltp(pos.option_symbol)
        self._record_alert(
            ts,
            "ORDER",
            f"{pos.option_type} exit order placed for {pos.option_symbol} "
            f"qty={qty} reason={reason}",
        )
        try:
            exit_order_id = self.broker.place_market_order(pos.option_symbol, OrderSide.SELL, qty)
        except Exception as exc:
            self._record_alert(
                ts,
                "ERROR",
                f"{pos.option_type} exit order failed for {pos.option_symbol} "
                f"qty={qty}: {exc}",
            )
            return
        self._record_alert(
            ts,
            "ORDER",
            f"{pos.option_type} exit order accepted for {pos.option_symbol} "
            f"qty={qty} order_id={exit_order_id}",
        )

        pnl_entry_price = self._pnl_entry_price(pos)
        trade_pnl = (exit_ltp - pnl_entry_price) * qty
        self.realized_pnl += trade_pnl

        pos.quantity -= qty
        self._record_alert(
            ts,
            "EXIT",
            f"{reason}: exited {pos.option_type} {pos.option_symbol} qty={qty} at {exit_ltp:.2f}, "
            f"pnl_entry={pnl_entry_price:.2f}, trade_pnl={trade_pnl:.2f}, "
            f"remaining={pos.quantity}",
        )
        if row is not None:
            print(self._fmt_candle_context(row, pos.option_symbol, self._is_ema21_strategy()))

        if pos.quantity <= 0:
            if pos.protective_stop_order_id:
                self.broker.cancel_order(pos.protective_stop_order_id)
            side_state.position = None
            if hasattr(side_state, "setup_active"):
                self.signal_provider.reset_after_entry(side_state)
        elif pos.protective_stop_order_id and refresh_protection:
            self._refresh_protective_stop(pos.option_type, pos, ts)

        if is_hard_sl:
            self.state.sl_hits_today = _increment_shared_sl_count(ts.date())
            self.total_hard_sl_hits += 1
            if self.state.sl_hits_today >= self.risk.max_sl_per_day:
                self._record_alert(
                    ts,
                    "RISK",
                    f"Daily SL cap reached ({self.state.sl_hits_today}/"
                    f"{self.risk.max_sl_per_day}) — no new entries today",
                )

    def get_status_snapshot(self) -> dict:
        if self.state.trading_day is not None:
            self._sync_shared_sl_count(self.state.trading_day)
        unrealized_pnl = self._get_unrealized_pnl()
        total_pnl = self.realized_pnl + unrealized_pnl

        def _side_payload(side_state: BaseSideState) -> dict:
            pos = side_state.position
            pending = side_state.pending_entry
            return {
                "watched_symbol": side_state.option_symbol,
                "position": None if pos is None else {
                    "option_symbol": pos.option_symbol,
                    "option_type": pos.option_type,
                    "quantity": pos.quantity,
                    "initial_quantity": pos.initial_quantity,
                    "entry_price": pos.entry_price,
                    "entry_time": pos.entry_time,
                    "option_stop_level": pos.option_stop_level,
                    "option_entry_trigger": pos.option_entry_trigger,
                    "option_risk_points": pos.option_risk_points,
                    "breakeven_armed": pos.breakeven_armed,
                    "current_price": pos.current_price,
                    "progress_status": pos.progress_status,
                    "next_target_rr": pos.next_target_rr,
                },
                "pending_entry": None if pending is None else {
                    "signal": pending.signal.value,
                    "created_at": pending.created_at,
                    "option_symbol": pending.option_symbol,
                    "quantity": pending.quantity,
                    "option_trigger_level": pending.option_trigger_level,
                    "option_stop_level": pending.option_stop_level,
                },
            }

        return {
            "trading_day": self.state.trading_day,
            "atm_locked": self.state.atm_locked,
            "atm_strike": self.state.atm_strike,
            "ce_symbol": self.state.ce_symbol,
            "pe_symbol": self.state.pe_symbol,
            "sl_hits_today": self.state.sl_hits_today,
            "day_closed": self.state.sl_hits_today >= self.risk.max_sl_per_day,
            "ce": _side_payload(self.state.ce),
            "pe": _side_payload(self.state.pe),
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl": total_pnl,
            "total_entries": self.total_entries,
            "total_hard_sl_hits": self.total_hard_sl_hits,
            "last_processed_candle_time": self.last_processed_candle_time,
        }

    # ── session / timing ────────────────────────────────────────────

    def reset_for_new_day(self, new_day: date) -> None:
        self.state = DayState(
            trading_day=new_day,
            ce=self.signal_provider.create_side_state(),
            pe=self.signal_provider.create_side_state(),
        )
        self.total_entries = 0
        reset_ts = datetime.combine(new_day, self.cfg.market_open)
        print(f"\n{'='*60}")
        print(f"  NEW SESSION: {new_day}  |  Max SL/day: {self.risk.max_sl_per_day}")
        print(f"{'='*60}")
        self._record_alert(reset_ts, "SESSION", f"Session reset for {new_day}")

    def on_day_transition_if_needed(self, ts: datetime) -> None:
        if self.state.trading_day != ts.date():
            self.reset_for_new_day(ts.date())

    def in_trade_window(self, ts: datetime) -> bool:
        return self.cfg.market_open <= ts.time() < self.cfg.market_close

    def in_signal_window(self, ts: datetime) -> bool:
        return self.cfg.market_open <= ts.time() < self.cfg.signal_cutoff

    def must_force_square_off(self, ts: datetime) -> bool:
        return ts.time() >= self.cfg.force_square_off

    def lock_atm_for_day(
        self,
        ts: datetime,
        spot_price: float,
        expiry_day_override: Optional[date] = None,
    ) -> None:
        if self.state.atm_locked:
            return
        strike = get_atm_strike(spot_price, self.cfg.strike_step)

        expiry_day: Optional[date] = expiry_day_override
        if expiry_day is None:
            expiry_day = self.broker.resolve_nearest_expiry(
                self.cfg.option_index_symbol,
                ts.date(),
                strike,
                self.cfg.strike_step,
                preferred_weekday=self.cfg.weekly_expiry_weekday,
                expiry_policy=self.cfg.expiry_policy,
            )
        if expiry_day is None:
            if self.cfg.expiry_policy == "monthly":
                expiry_day = choose_monthly_expiry_for_entry(ts.date(), self.cfg.weekly_expiry_weekday)
            else:
                expiry_day = choose_weekly_expiry_for_entry(ts.date(), self.cfg.weekly_expiry_weekday)
        expiry_code = format_expiry_code(expiry_day)

        ce_symbol = build_option_symbol(self.cfg.option_index_symbol, expiry_code, strike, "CE")
        pe_symbol = build_option_symbol(self.cfg.option_index_symbol, expiry_code, strike, "PE")
        self.state.ce_symbol = ce_symbol
        self.state.pe_symbol = pe_symbol
        self.state.atm_strike = strike
        self.state.ce.option_symbol = ce_symbol
        self.state.pe.option_symbol = pe_symbol
        self.state.atm_locked = True
        print()
        print("┌" + "─" * 60 + "┐")
        print(f"│ {'STRATEGY — STRIKES LOCKED':^58s} │")
        print("├" + "─" * 60 + "┤")
        print(f"│  Date   : {ts.date()!s:<47s} │")
        print(f"│  Spot   : {spot_price:<47.2f} │")
        print(f"│  Strike : {strike:<47d} │")
        print(f"│  Expiry : {expiry_code:<47s} │")
        print(f"│  CE     : {ce_symbol:<47s} │")
        print(f"│  PE     : {pe_symbol:<47s} │")
        print("└" + "─" * 60 + "┘")
        print()
        self._record_alert(
            ts, "ATM_LOCK", f"Strike {strike} | CE={ce_symbol} | PE={pe_symbol}",
        )

    # ── entry placement ────────────────────────────────────────────

    def _cancel_pending_entry_order(
        self,
        side: str,
        pending: PendingEntry,
        ts: datetime,
    ) -> bool:
        order_id = getattr(pending, "order_id", None)
        if self.broker.is_replay or not order_id:
            return True
        if self.broker.cancel_order(order_id):
            return True
        self._record_alert(
            ts,
            "RISK",
            f"{side} pending order {order_id} cancellation failed; keeping it tracked",
        )
        return False

    def _cancel_pending_entry_with_reason(
        self,
        side: str,
        side_state: BaseSideState,
        ts: datetime,
        reason: str,
        order_already_closed: bool = False,
    ) -> bool:
        pending = side_state.pending_entry
        if pending is None:
            return True
        if not order_already_closed and not self._cancel_pending_entry_order(side, pending, ts):
            return False
        side_state.pending_entry = None
        self.signal_provider.reset_after_entry(side_state)
        alert_time = pending.created_at.strftime("%H:%M")
        self._record_alert(
            ts,
            "CANCEL",
            f"{side} alert at {alert_time}; entry missed: {reason}. "
            "Pending order cancelled; waiting for next alert candle.",
        )
        return True

    def _clear_stale_entry_ready(
        self,
        side: str,
        side_state: BaseSideState,
        ts: datetime,
        reason: str,
    ) -> None:
        """Clear a completed setup that never got a live generate_signal() call.

        Covers the case where entry_ready/first_red_high was set by a warmup
        replay (allow_entries=False) or the setup outlived the entry/signal
        window before a real order was ever attempted - without this, the
        side would show ENTRY_READY forever with no chance to place an order.
        """
        if side_state.position is not None or side_state.pending_entry is not None:
            return
        if not getattr(side_state, "entry_ready", False):
            return
        self.signal_provider.reset_after_entry(side_state)
        self._record_alert(
            ts,
            "CANCEL",
            f"{side} entry-ready setup cleared: {reason}",
        )

    def _cancel_uncertain_entry_order(self, side: str, side_state: BaseSideState, ts: datetime) -> bool:
        if self.broker.is_replay or not side_state.order_submission_uncertain:
            return True
        try:
            open_orders = self.broker.get_open_orders()
        except Exception as exc:
            self._record_alert(ts, "RISK", f"{side} uncertain entry cancellation check failed: {exc}")
            return False
        if open_orders is None:
            self._record_alert(ts, "RISK", f"{side} uncertain entry cancellation check unavailable")
            return False
        matching_orders = [
            order for order in open_orders
            if str(order.get("symbol") or "") == str(side_state.option_symbol or "")
            and str(order.get("action") or order.get("side") or "").upper() == "BUY"
        ]
        for order in matching_orders:
            order_id = str(order.get("orderid") or order.get("order_id") or "")
            if order_id and not self.broker.cancel_order(order_id):
                self._record_alert(ts, "RISK", f"{side} uncertain BUY order cancellation failed: {order_id}")
                return False
            if order_id:
                self._record_alert(ts, "CANCEL", f"{side} cancelled uncertain BUY order order_id={order_id}")
        return True

    def place_pending_entry(
        self,
        side: str,
        side_state: BaseSideState,
        ts: datetime,
        row: pd.Series,
    ) -> None:
        pending_ema_failure = False
        if (
            side_state.position is not None
            or side_state.pending_entry is not None
            or side_state.order_submission_uncertain
        ):
            if side_state.order_submission_uncertain:
                print(
                    f"[TRADE BLOCKED] {side} entry is uncertain for "
                    f"{side_state.option_symbol}; reconcile OpenAlgo before retry"
                )
            return

        if not self.broker.is_replay and side_state.option_symbol:
            try:
                open_orders = self.broker.get_open_orders()
            except Exception as exc:
                self._record_alert(ts, "RISK", f"{side} entry blocked: order check failed: {exc}")
                return
            if open_orders is None:
                self._record_alert(ts, "RISK", f"{side} entry blocked: order check unavailable")
                return
            matching_orders = [
                order for order in open_orders
                if str(order.get("symbol") or "") == side_state.option_symbol
                and str(order.get("action") or order.get("side") or "BUY").upper() == "BUY"
            ]
            for duplicate_order in matching_orders[1:]:
                order_id = str(duplicate_order.get("orderid") or duplicate_order.get("order_id") or "")
                if order_id:
                    self.broker.cancel_order(order_id)
            if matching_orders:
                    self._record_alert(
                        ts,
                        "RISK",
                        f"{side} entry skipped: active broker order exists "
                        f"for {side_state.option_symbol}",
                    )
                    return
            try:
                broker_positions = self.broker.get_position_book()
            except Exception as exc:
                self._record_alert(ts, "RISK", f"{side} entry blocked: position check failed: {exc}")
                return
            for broker_position in broker_positions:
                symbol = str(broker_position.get("symbol") or "")
                quantity = int(float(broker_position.get("quantity") or 0))
                if symbol == side_state.option_symbol and quantity > 0:
                    self._record_alert(
                        ts,
                        "RISK",
                        f"{side} entry skipped: broker position already exists "
                        f"for {symbol} qty={quantity}",
                    )
                    return

        if self._is_ema21_strategy():
            if ts.time() < self.cfg.entry_start or ts.time() >= self.cfg.entry_cutoff:
                self._record_alert(
                    ts,
                    "RISK",
                    f"{side} entry blocked: outside EMA21 entry window",
                )
                return
            if any(
                other.position is not None or other.pending_entry is not None
                for other in (self.state.ce, self.state.pe)
                if other is not side_state
            ):
                self._record_alert(ts, "RISK", f"{side} trade skipped: another side is active")
                return
            if self.total_entries >= self.cfg.max_trades_per_day:
                side_state.entry_block_reason = "daily-filled-entry-cap"
                self._record_alert(ts, "RISK", "Trade skipped: daily filled-entry cap reached")
                return

        if self.state.sl_hits_today >= self.risk.max_sl_per_day:
            self._record_alert(
                ts, "RISK",
                f"Trade skipped: daily SL cap ({self.state.sl_hits_today}/{self.risk.max_sl_per_day})",
            )
            return

        if side_state.option_symbol is None:
            self._record_alert(ts, "RISK", f"{side} trade skipped: ATM symbol not locked yet")
            return

        risk_points = self.signal_provider.compute_risk_points(side_state, row)
        if risk_points is None:
            self._record_alert(
                ts, "RISK", f"{side} trade cancelled: missing swing reference",
            )
            return

        if not self._is_ema21_strategy() and risk_points > self.cfg.max_option_risk_points:
            self._record_alert(
                ts, "RISK",
                f"{side} trade cancelled: risk {risk_points:.2f} > {self.cfg.max_option_risk_points:.2f}",
            )
            return

        entry_level = self.signal_provider.compute_entry_trigger_level(side_state, row)
        stop_level = self.signal_provider.compute_stop_level(side_state, row)
        if self._is_ema21_strategy():
            entry_level = self._round_option_price(entry_level)
            stop_level = self._round_option_price(stop_level)
            risk_points = entry_level - stop_level
            if risk_points > self.cfg.max_option_risk_points:
                self._record_alert(
                    ts, "RISK",
                    f"{side} trade cancelled before order: entry-SL gap {risk_points:.2f} "
                    f"> {self.cfg.max_option_risk_points:.2f} points",
                )
                # This trigger/stop pair is permanently invalid (same setup_low
                # and first_red_high would keep failing), so reset the
                # confirmation candle instead of leaving the side stuck in
                # ENTRY_READY waiting for an expiry timeout.
                self.signal_provider.reset_after_entry(side_state)
                return

        # Legacy strategies retain the existing VWAP room filter.
        if self.signal_provider.applies_vwap_room_filter():
            # VWAP room filter: entry below VWAP must have at least 1.5 RR of headroom.
            vwap = float(row["vwap"]) if not pd.isna(row["vwap"]) else None
            if vwap is not None and entry_level < vwap:
                room = vwap - entry_level
                required = self.cfg.min_vwap_room_rr * risk_points
                if room < required:
                    self._record_alert(
                        ts, "RISK",
                        f"{side} trade cancelled: VWAP room {room:.2f} < {self.cfg.min_vwap_room_rr} RR ({required:.2f})",
                    )
                    return
        lots = self.signal_provider.compute_entry_lots(row, self.cfg)
        quantity = lots * self.cfg.option_lot_size

        trigger_level = entry_level

        if self.signal_provider.submit_stop_limit_on_signal():
            limit_level = trigger_level + self.signal_provider.entry_limit_buffer(self.cfg)
            print(
                f"[TRADE PREVIEW] ABOUT TO PLACE ENTRY ORDER "
                f"side={side} symbol={side_state.option_symbol} qty={quantity} "
                f"type=SL trigger={trigger_level:.2f} limit={limit_level:.2f} "
                f"stop={stop_level:.2f} time={ts}"
            )
            try:
                order_id = self.broker.place_stop_limit_order(
                    side_state.option_symbol,
                    OrderSide.BUY,
                    quantity,
                    trigger_price=trigger_level,
                    limit_price=limit_level,
                )
            except Exception as exc:
                # A timeout is ambiguous: the broker may have accepted the order.
                # Block this side rather than submitting a duplicate.
                side_state.order_submission_uncertain = True
                self._record_alert(
                    ts,
                    "RISK",
                    f"{side} entry submission uncertain for {side_state.option_symbol}; "
                    f"manual broker reconciliation required: {exc}",
                )
                self._record_alert(
                    ts,
                    "UNCERTAIN_ENTRY",
                    f"Uncertain {side} {side_state.option_symbol} qty={quantity} "
                    f"trigger={trigger_level:.2f} SL={stop_level:.2f}",
                )
                return
        else:
            order_id = None

        side_state.pending_entry = PendingEntry(
            signal=Signal.BUY_CE if side == "CE" else Signal.BUY_PE,
            created_at=ts,
            option_symbol=side_state.option_symbol,
            quantity=quantity,
            option_trigger_level=trigger_level,
            option_stop_level=stop_level,
            trigger_candle_high=float(row["high"]),
            trigger_candle_low=float(row["low"]),
            order_id=order_id,
        )

        self._record_alert(
            ts, "PENDING_ENTRY",
            f"Pending {side} {side_state.option_symbol} qty={quantity} "
            f"trigger={trigger_level:.2f} SL={stop_level:.2f} lots={lots} "
            f"option_risk={risk_points:.2f}",
        )
        print(self._fmt_candle_context(row, side_state.option_symbol, self._is_ema21_strategy()))

    def try_fill_pending_entry(
        self,
        side: str,
        side_state: BaseSideState,
        ts: datetime,
        row: pd.Series,
    ) -> None:
        if side_state.order_submission_uncertain:
            return
        pending = side_state.pending_entry
        if pending is None:
            return

        if self._is_ema21_strategy() and ts.time() >= self.cfg.entry_cutoff:
            self._cancel_pending_entry_with_reason(
                side,
                side_state,
                ts,
                f"entry cutoff reached at {self.cfg.entry_cutoff.strftime('%H:%M')}",
            )
            return

        candle_seconds = max(1, self.cfg.timeframe_minutes * 60)
        # Normalize datetimes to handle timezone-aware vs timezone-naive mismatch
        ts_normalized = ts.replace(tzinfo=None) if ts.tzinfo else ts
        created_at_normalized = pending.created_at.replace(tzinfo=None) if pending.created_at.tzinfo else pending.created_at
        elapsed_seconds = max(0.0, (ts_normalized - created_at_normalized).total_seconds())
        candles_elapsed = int(elapsed_seconds // candle_seconds)
        if candles_elapsed > self.cfg.pending_entry_expiry_candles:
            self._cancel_pending_entry_with_reason(
                side,
                side_state,
                ts,
                f"entry window expired after {candles_elapsed} candles "
                f"(limit={self.cfg.pending_entry_expiry_candles})",
            )
            return

        if float(row["low"]) <= pending.option_stop_level:
            self._cancel_pending_entry_with_reason(
                side,
                side_state,
                ts,
                f"SL breached (low={float(row['low']):.2f} <= SL={pending.option_stop_level:.2f})",
            )
            return

        if float(row["high"]) >= pending.option_trigger_level:
            limit_price = (
                pending.option_trigger_level
                + self.signal_provider.entry_limit_buffer(self.cfg)
            )
            if float(row["low"]) > limit_price:
                self._cancel_pending_entry_with_reason(
                    side,
                    side_state,
                    ts,
                    f"trigger missed in gap (low={float(row['low']):.2f} > limit={limit_price:.2f})",
                )
                return

        if self._is_ema21_strategy() and not self.broker.is_replay:
            status = self.broker.get_order_status(pending.order_id or "")
            order_status = str(status.get("order_status") or status.get("status") or "").lower()
            if order_status in {"cancelled", "rejected", "failed"}:
                self._cancel_pending_entry_with_reason(
                    side,
                    side_state,
                    ts,
                    f"broker order was {order_status}",
                    order_already_closed=True,
                )
            elif order_status in {"complete", "filled", "executed"}:
                broker_quantity = self._broker_quantity(pending.option_symbol)
                if broker_quantity == 0:
                    self._record_alert(
                        ts,
                        "RISK",
                        f"{side} completed entry order has no broker position; "
                        f"clearing stale pending state for {pending.option_symbol}",
                    )
                    side_state.pending_entry = None
                    self.signal_provider.reset_after_entry(side_state)
                    return
                if broker_quantity is not None and broker_quantity < pending.quantity:
                    side_state.order_submission_uncertain = True
                    self._record_alert(
                        ts,
                        "RISK",
                        f"{side} entry fill blocked: broker quantity for {pending.option_symbol} "
                        f"is {broker_quantity}, expected long quantity is {pending.quantity}",
                    )
                    return
                option_ltp = float(
                    status.get("average_price") or status.get("price") or pending.option_trigger_level
                )
                actual_risk = option_ltp - pending.option_stop_level
                if actual_risk > self.cfg.max_option_risk_points:
                    self._record_alert(
                        ts,
                        "RISK",
                        f"{side} fill risk {actual_risk:.2f} exceeds limit "
                        f"{self.cfg.max_option_risk_points:.2f}; exiting {pending.option_symbol}",
                    )
                    try:
                        self.broker.place_market_order(
                            pending.option_symbol,
                            OrderSide.SELL,
                            pending.quantity,
                        )
                    except Exception as exc:
                        self._record_alert(
                            ts,
                            "ERROR",
                            f"{side} risk-breach exit failed for {pending.option_symbol}: {exc}",
                        )
                        side_state.order_submission_uncertain = True
                        return
                    side_state.pending_entry = None
                    self.signal_provider.reset_after_entry(side_state)
                    return
                side_state.position = Position(
                    option_symbol=pending.option_symbol,
                    option_type=side,
                    quantity=pending.quantity,
                    initial_quantity=pending.quantity,
                    entry_price=option_ltp,
                    entry_time=ts,
                    option_stop_level=pending.option_stop_level,
                    option_entry_trigger=pending.option_trigger_level,
                    option_risk_points=abs(pending.option_trigger_level - pending.option_stop_level),
                )
                self._place_protective_stop(side, side_state.position, ts)
                side_state.pending_entry = None
                self.total_entries += 1
                self.signal_provider.reset_after_entry(side_state)
                self._record_alert(
                    ts, "ENTRY",
                    f"Entered {side} {pending.option_symbol} @ {option_ltp:.2f}, "
                    f"qty={pending.quantity}, trigger={pending.option_trigger_level:.2f}, "
                    f"SL={pending.option_stop_level:.2f}, "
                    f"option_risk={abs(pending.option_trigger_level - pending.option_stop_level):.2f}",
                )
            return

        # Cancel pending after configured number of candles from setup bar.
        if float(row["high"]) < pending.option_trigger_level:
            return

        option_symbol = pending.option_symbol
        risk_points = abs(pending.option_trigger_level - pending.option_stop_level)

        # FRD §5.1: entry via STOP_LIMIT (trigger + 0.5 limit buffer).
        simulated_fill = self.broker.simulate_stop_limit_fill(
            option_symbol,
            pending.option_trigger_level,
            limit_price,
        )
        if simulated_fill is not None:
            option_ltp = simulated_fill
        else:
            if self.broker.is_replay:
                # A stop-limit order remains working when a candle gaps above
                # its limit; expiry, EMA failure, cutoff, or stop breach owns
                # cancellation. Do not invent a fill or cancel the order here.
                return
            option_ltp = self.broker.get_ltp(option_symbol)

        try:
            print(
                f"[TRADE PREVIEW] ABOUT TO PLACE ENTRY ORDER "
                f"side={side} symbol={option_symbol} qty={pending.quantity} "
                f"type=SL trigger={pending.option_trigger_level:.2f} "
                f"limit={limit_price:.2f} stop={pending.option_stop_level:.2f} time={ts}"
            )
            self.broker.place_stop_limit_order(
                option_symbol, OrderSide.BUY, pending.quantity,
                trigger_price=pending.option_trigger_level,
                limit_price=limit_price,
            )
        except Exception as exc:
            # The request may have reached the broker even without a response.
            side_state.order_submission_uncertain = True
            self._record_alert(
                ts,
                "RISK",
                f"{side} entry submission uncertain for {option_symbol}; "
                f"manual broker reconciliation required: {exc}",
            )
            self._record_alert(
                ts,
                "UNCERTAIN_ENTRY",
                f"Uncertain {side} {option_symbol} qty={pending.quantity} "
                f"trigger={pending.option_trigger_level:.2f} SL={pending.option_stop_level:.2f}",
            )
            return

        side_state.position = Position(
            option_symbol=option_symbol,
            option_type=side,
            quantity=pending.quantity,
            initial_quantity=pending.quantity,
            entry_price=option_ltp,
            entry_time=ts,
            option_stop_level=pending.option_stop_level,
            option_entry_trigger=pending.option_trigger_level,
            option_risk_points=risk_points,
        )
        self._place_protective_stop(side, side_state.position, ts)
        side_state.pending_entry = None
        self.total_entries += 1
        self.signal_provider.reset_after_entry(side_state)

        self._record_alert(
            ts, "ENTRY",
            f"Entered {side} {option_symbol} @ {option_ltp:.2f}, "
            f"trigger={pending.option_trigger_level:.2f}, "
            f"SL={pending.option_stop_level:.2f}, option_risk={risk_points:.2f}",
        )
        print(self._fmt_candle_context(row, option_symbol, self._is_ema21_strategy()))

    # ── position monitoring ────────────────────────────────────────

    def compute_rr_progress(self, pos: Position, row: pd.Series) -> float:
        if pos.option_risk_points <= 0:
            return 0.0
        rr_entry = pos.entry_price if self._is_ema21_strategy() else pos.option_entry_trigger
        favorable_move = float(row["high"]) - rr_entry
        return favorable_move / pos.option_risk_points

    def execute_partial_exit(
        self,
        side_state: BaseSideState,
        exit_quantity: int,
        reason: str,
    ) -> None:
        pos = side_state.position
        if pos is None:
            return
        qty = min(exit_quantity, pos.quantity)
        if qty <= 0:
            return
        self._exit_position(
            side_state,
            self.last_processed_candle_time or pos.entry_time,
            qty,
            reason,
            is_hard_sl=False,
            refresh_protection=False,
        )

    def manage_targets(self, side_state: BaseSideState, row: pd.Series) -> None:
        """FRD §6: Step-trailing SL logic.

                - At 1.0 RR arm breakeven for every position size.
                - 2-lot: at 2.0 RR book 1 lot, then trail the remaining lot every
                    0.5 RR indefinitely.
                - 1-lot: keep the lot open and trail it until the trailing SL hits.
        """
        pos = side_state.position
        if pos is None:
            return

        rr = self.compute_rr_progress(pos, row)
        lot_qty = self.cfg.option_lot_size
        partial_qty = self.cfg.half_size_lots * lot_qty
        ir = pos.option_risk_points

        # At 1.0 RR — arm breakeven for both 1-lot and 2-lot positions.
        if rr >= self.cfg.t1_rr and not pos.t1_done:
            pos.breakeven_armed = True
            pos.t1_done = True
            pos.trailing_sl_level = pos.entry_price
            pos.option_stop_level = pos.entry_price
            pos.highest_rr_step = self.cfg.t1_rr
            pos.next_target_rr = self.cfg.t2_rr
            pos.progress_status = f"{self.cfg.t1_rr:.1f}R reached - looking for {self.cfg.t2_rr:.1f}R"
            if rr < self.cfg.t2_rr:
                self._refresh_protective_stop(pos.option_type, pos, self.last_processed_candle_time or pos.entry_time)
            self._record_alert(
                self.last_processed_candle_time or pos.entry_time,
                "TARGET",
                f"{pos.option_type} {self.cfg.t1_rr:.1f} RR hit — SL moved to entry (breakeven)",
            )

        # Phase 3: At 2.0 RR — partial exit 1 lot.
        if (
            not self._is_ema21_strategy()
            and pos.initial_quantity > partial_qty
            and rr >= self.cfg.t2_rr
            and not pos.t2_done
        ):
            self.execute_partial_exit(
                side_state, partial_qty,
                f"2.0 RR hit — booked 1 lot",
            )
            if side_state.position is None:
                return
            side_state.position.t2_done = True
            side_state.position.next_target_rr = self.cfg.t2_rr + self.cfg.trailing_step_rr
            side_state.position.progress_status = (
                f"{self.cfg.t2_rr:.1f}R reached - half lot booked; "
                f"looking for {side_state.position.next_target_rr:.1f}R"
            )

        # Step-trailing: at 1.5R protect 0.5R, then advance by 0.5R.
        if pos.breakeven_armed and ir > 0:
            step = max(self.cfg.trailing_step_rr, 0.01)
            current_step = int(rr / step) * step  # floor to the configured step
            if current_step > pos.highest_rr_step:
                trail_offset = self.cfg.t1_rr if self._is_ema21_strategy() else 1.5
                new_sl = pos.entry_price + (current_step - trail_offset) * ir
                if pos.trailing_sl_level is None or new_sl > pos.trailing_sl_level:
                    pos.trailing_sl_level = new_sl
                    pos.option_stop_level = new_sl
                    pos.highest_rr_step = current_step
                    self._refresh_protective_stop(pos.option_type, pos, self.last_processed_candle_time or pos.entry_time)
                    pos.next_target_rr = current_step + step
                    pos.progress_status = (
                        f"{current_step:.1f}R reached - SL shifted to {new_sl:.2f}; "
                        f"looking for {pos.next_target_rr:.1f}R"
                    )
                    self._record_alert(
                        self.last_processed_candle_time or pos.entry_time,
                        "TSL",
                        f"{pos.option_type} {current_step:.1f} RR — TSL raised to {new_sl:.2f}",
                    )

    def check_trailing_stop(self, side_state: BaseSideState, row: Optional[pd.Series] = None) -> None:
        """Exit if the candle low or live LTP drops to the trailing SL level."""
        pos = side_state.position
        if pos is None or not pos.breakeven_armed:
            return
        sl_level = pos.trailing_sl_level if pos.trailing_sl_level is not None else pos.entry_price
        if row is not None:
            observed_price = float(row["low"])
            if observed_price > sl_level:
                return
            reason = f"Trailing stop hit: candle low {observed_price:.2f} <= TSL {sl_level:.2f}"
        else:
            observed_price = self.broker.get_ltp(pos.option_symbol)
            if observed_price <= 0 or observed_price > sl_level:
                return
            reason = f"Trailing stop hit: LTP {observed_price:.2f} <= TSL {sl_level:.2f}"
        if observed_price <= sl_level:
            self._exit_position(
                side_state,
                self.last_processed_candle_time or pos.entry_time,
                pos.quantity,
                reason,
                is_hard_sl=False,
                row=row,
            )

    def monitor_open_position(self, side_state: BaseSideState, row: pd.Series) -> None:
        pos = side_state.position
        if pos is None:
            return

        option_low = float(row["low"])

        if option_low <= pos.option_stop_level:
            self._exit_position(
                side_state,
                self.last_processed_candle_time or pos.entry_time,
                pos.quantity,
                f"Catastrophic stop hit: option low {option_low:.2f} <= SL {pos.option_stop_level:.2f}",
                is_hard_sl=True,
                row=row,
            )
            return

        self.manage_targets(side_state, row)
        self.check_trailing_stop(side_state, row=row)

    def force_square_off_side(self, side_state: BaseSideState, ts: datetime) -> None:
        pending = side_state.pending_entry
        if pending is not None:
            side = "CE" if side_state is self.state.ce else "PE"
            if self._cancel_pending_entry_order(side, pending, ts):
                side_state.pending_entry = None
                self._record_alert(
                    ts,
                    "CANCEL",
                    f"{side} pending entry cancelled at replay end: trigger/fill not reached "
                    f"for {pending.option_symbol} (trigger={pending.option_trigger_level:.2f})",
                )
        pos = side_state.position
        if pos is None:
            return
        self._exit_position(
            side_state, ts, pos.quantity,
            f"Forced square-off at {ts.time()} for {pos.option_symbol}",
            is_hard_sl=False,
        )

    # ── tick-level monitoring (FRD §5.2 / §6) ──────────────────────

    def process_setup_tick(self, side: str, ltp: float, ts: datetime) -> bool:
        """Process a setup tick; EMA21 entries are confirmed on closed candles only."""
        side_state = self._side_state(side)
        process_setup_tick = getattr(self.signal_provider, "process_setup_tick", None)
        if (
            not callable(process_setup_tick)
            or side_state.position is not None
            or side_state.pending_entry is not None
            or not getattr(side_state, "setup_active", False)
        ):
            return False

        armed = bool(process_setup_tick(side_state, float(ltp), ts))
        if not armed:
            return False

        live_high = float(side_state.live_confirmation_high or ltp)
        live_low = float(side_state.live_confirmation_low or ltp)
        row = pd.Series(
            {
                "datetime": ts,
                "open": float(side_state.live_confirmation_open or ltp),
                "high": live_high,
                "low": live_low,
                "close": float(ltp),
                "ema21": side_state.last_ema21,
            }
        )
        signal = self.signal_provider.generate_signal(side, side_state, row, None)
        if signal not in (Signal.BUY_CE, Signal.BUY_PE):
            return False

        self._record_alert(
            ts,
            "SIGNAL",
            f"{side} {signal.value} signal during live red confirmation "
            f"at LTP={float(ltp):.2f} symbol={side_state.option_symbol or '-'}",
        )
        had_pending = side_state.pending_entry is not None
        self.place_pending_entry(side, side_state, ts, row)
        return not had_pending and side_state.pending_entry is not None

    def process_tick(self, side: str, ltp: float, ts: datetime) -> None:
        """Called on every WebSocket tick for a side with an active position.

        Handles:
        - Hard SL exit
        - Step-trailing SL advancement + exit
        - Partial exit at 2.0 RR for multi-lot positions
        - Breakeven at 1.5 RR and trailing for every position size
        """
        self._sync_shared_sl_count(self.state.trading_day or ts.date())
        side_state = self._side_state(side)
        pos = side_state.position
        if pos is None:
            return

        self.last_processed_candle_time = ts
        pos.current_price = float(ltp)
        ir = pos.option_risk_points
        if ir <= 0:
            return

        # Hard SL check.
        if ltp <= pos.option_stop_level:
            self._exit_position(
                side_state, ts, pos.quantity,
                f"Hard SL hit (tick): LTP {ltp:.2f} <= SL {pos.option_stop_level:.2f}",
                is_hard_sl=True,
            )
            return

        # Compute current RR from tick LTP.
        rr_entry = pos.entry_price if self._is_ema21_strategy() else pos.option_entry_trigger
        rr = (ltp - rr_entry) / ir
        lot_qty = self.cfg.option_lot_size

        # At 1.0 RR — arm breakeven for both 1-lot and 2-lot positions.
        if rr >= self.cfg.t1_rr and not pos.t1_done:
            pos.breakeven_armed = True
            pos.t1_done = True
            pos.trailing_sl_level = pos.entry_price
            pos.option_stop_level = pos.entry_price
            pos.highest_rr_step = self.cfg.t1_rr
            pos.next_target_rr = self.cfg.t2_rr
            pos.progress_status = f"{self.cfg.t1_rr:.1f}R reached - looking for {self.cfg.t2_rr:.1f}R"
            if rr < self.cfg.t2_rr:
                self._refresh_protective_stop(pos.option_type, pos, ts)
                self._record_alert(
                    ts,
                    "TSL",
                    f"{pos.option_type} {self.cfg.t1_rr:.1f} RR (tick) — SL to entry",
                )

        # Phase 3: 2.0 RR — partial exit.
        if (
            not self._is_ema21_strategy()
            and pos.initial_quantity > lot_qty
            and rr >= self.cfg.t2_rr
            and not pos.t2_done
        ):
            self.execute_partial_exit(side_state, lot_qty, f"2.0 RR (tick) — booked 1 lot")
            if side_state.position is None:
                return
            side_state.position.t2_done = True
            side_state.position.next_target_rr = self.cfg.t2_rr + self.cfg.trailing_step_rr
            side_state.position.progress_status = (
                f"{self.cfg.t2_rr:.1f}R reached - half lot booked; "
                f"looking for {side_state.position.next_target_rr:.1f}R"
            )
            pos = side_state.position

        # Step-trailing: at 1.5R protect 0.5R, then advance by 0.5R.
        if pos.breakeven_armed and ir > 0:
            step = max(self.cfg.trailing_step_rr, 0.01)
            current_step = int(rr / step) * step
            if current_step > pos.highest_rr_step:
                trail_offset = self.cfg.t1_rr if self._is_ema21_strategy() else 1.5
                new_sl = pos.entry_price + (current_step - trail_offset) * ir
                if pos.trailing_sl_level is None or new_sl > pos.trailing_sl_level:
                    pos.trailing_sl_level = new_sl
                    pos.option_stop_level = new_sl
                    pos.highest_rr_step = current_step
                    self._refresh_protective_stop(pos.option_type, pos, ts)
                    pos.next_target_rr = current_step + step
                    pos.progress_status = (
                        f"{current_step:.1f}R reached - SL shifted to {new_sl:.2f}; "
                        f"looking for {pos.next_target_rr:.1f}R"
                    )
                    self._record_alert(ts, "TSL", f"{pos.option_type} {current_step:.1f} RR (tick) — TSL={new_sl:.2f}")

        # Check trailing stop on this tick.
        if pos.breakeven_armed:
            sl_level = pos.trailing_sl_level if pos.trailing_sl_level is not None else pos.entry_price
            if ltp <= sl_level:
                self._exit_position(
                    side_state, ts, pos.quantity,
                    f"TSL hit (tick): LTP {ltp:.2f} <= TSL {sl_level:.2f}",
                    is_hard_sl=False,
                )

    # ── main per-bar entry point ────────────────────────────────────

    def process_option_candle(
        self,
        side: str,
        row: pd.Series,
        prev_row: Optional[pd.Series],
        allow_entries: bool = True,
        preserve_setup_state: bool = False,
    ) -> None:
        ts = row["datetime"]
        self.last_processed_candle_time = ts
        self.on_day_transition_if_needed(ts)
        self._sync_shared_sl_count(ts.date())

        side_state = self._side_state(side)
        signal: Signal = Signal.NONE
        remark = "NO_ENTRY"
        trade_initiated = False
        state_updated = False
        had_pending_before = side_state.pending_entry is not None
        had_position_before = side_state.position is not None

        # Update indicator cache for status display.
        side_state.last_close = float(row["close"])
        ema21_val = row.get("ema21")
        side_state.last_ema21 = None if (ema21_val is None or pd.isna(ema21_val)) else float(ema21_val)
        rsi_val = row.get("rsi3")
        side_state.last_rsi = None if (rsi_val is None or pd.isna(rsi_val)) else float(rsi_val)
        for attr, col in (("last_ema13", "ema13"), ("last_ema20", "ema20"), ("last_ema50", "ema50")):
            v = row.get(col)
            setattr(side_state, attr, None if (v is None or pd.isna(v)) else float(v))

        if self.must_force_square_off(ts):
            self.force_square_off_side(side_state, ts)
            remark = "FORCE_SQUARE_OFF"
            self._record_trace_row(side, side_state, row, signal, False, remark)
            return

        if not self.in_trade_window(ts):
            remark = "OUTSIDE_TRADE_WINDOW"
            self._record_trace_row(side, side_state, row, signal, False, remark)
            return

        if side_state.option_symbol is None:
            remark = "ATM_NOT_LOCKED"
            self._record_trace_row(side, side_state, row, signal, False, remark)
            return

        if self._is_ema21_strategy() and ts.time() >= self.cfg.entry_cutoff:
            if side_state.pending_entry is not None:
                self._cancel_pending_entry_with_reason(
                    side,
                    side_state,
                    ts,
                    f"entry cutoff reached at {self.cfg.entry_cutoff.strftime('%H:%M')}",
                )
            else:
                self._clear_stale_entry_ready(
                    side, side_state, ts,
                    f"entry cutoff reached at {self.cfg.entry_cutoff.strftime('%H:%M')}",
                )
            self.monitor_open_position(side_state, row)
            remark = "OUTSIDE_ENTRY_WINDOW"
            self._record_trace_row(side, side_state, row, signal, False, remark)
            return

        if not self.in_signal_window(ts):
            if side_state.pending_entry is not None:
                self._cancel_pending_entry_with_reason(
                    side,
                    side_state,
                    ts,
                    f"entry cutoff reached at {self.cfg.signal_cutoff.strftime('%H:%M')}",
                )
            else:
                self._clear_stale_entry_ready(
                    side, side_state, ts,
                    f"entry cutoff reached at {self.cfg.signal_cutoff.strftime('%H:%M')}",
                )
            self.monitor_open_position(side_state, row)
            remark = "OUTSIDE_SIGNAL_WINDOW"
            self._record_trace_row(side, side_state, row, signal, False, remark)
            return

        if not allow_entries:
            if preserve_setup_state:
                self.signal_provider.update_state(side_state, row, prev_row)
                state_updated = True
            self.monitor_open_position(side_state, row)
            if (
                self._is_ema21_strategy()
                and side_state.position is not None
                and float(row["close"]) < float(row["ema21"])
            ):
                self._exit_position(
                    side_state,
                    ts,
                    side_state.position.quantity,
                    "EMA-21 close exit",
                    is_hard_sl=False,
                    row=row,
                )
            if not preserve_setup_state:
                self.signal_provider.reset_after_entry(side_state)
            self._record_trace_row(side, side_state, row, signal, False, "STATE_WARMUP")
            return

        if (
            self._is_ema21_strategy()
            and side_state.pending_entry is not None
            and row.get("ema21") is not None
            and not pd.isna(row.get("ema21"))
            and float(row["close"]) <= float(row["ema21"])
        ):
            self._cancel_pending_entry_with_reason(
                side,
                side_state,
                ts,
                f"EMA21 close failure (close={float(row['close']):.2f} <= EMA21={float(row['ema21']):.2f})",
            )
        if (
            self._is_ema21_strategy()
            and side_state.order_submission_uncertain
            and side_state.option_symbol
            and row.get("ema21") is not None
            and not pd.isna(row.get("ema21"))
            and float(row["close"]) <= float(row["ema21"])
        ):
            if self._cancel_uncertain_entry_order(side, side_state, ts):
                side_state.order_submission_uncertain = False
                self.signal_provider.reset_after_entry(side_state)
                self._record_alert(
                    ts,
                    "CANCEL",
                    f"{side} uncertain entry cancelled: EMA21 close failure "
                    f"(close={float(row['close']):.2f} <= EMA21={float(row['ema21']):.2f})",
                )
                return
        if side_state.pending_entry is not None:
            self.try_fill_pending_entry(side, side_state, ts, row)
        self.monitor_open_position(side_state, row)

        if had_position_before and side_state.position is None:
            self.signal_provider.reset_after_entry(side_state)
            self._record_trace_row(side, side_state, row, signal, False, "POSITION_EXITED_NO_REENTRY")
            return

        # Delegate signal generation to the strategy provider.
        setup_was_active = getattr(side_state, "setup_active", False)
        if not state_updated:
            self.signal_provider.update_state(side_state, row, prev_row)
        if side_state.pending_entry is not None:
            cancellation_reason = self.signal_provider.pending_entry_cancellation_reason(
                side, side_state, row, prev_row
            )
            if cancellation_reason:
                self._cancel_pending_entry_with_reason(
                    side, side_state, ts, cancellation_reason
                )
                self._record_trace_row(
                    side, side_state, row, signal, False, "PENDING_ENTRY_CANCELLED"
                )
                return
        if (
            self._is_ema21_strategy()
            and not setup_was_active
            and getattr(side_state, "setup_active", False)
        ):
            ema21 = row.get("ema21")
            ema_text = "NA" if ema21 is None or pd.isna(ema21) else f"{float(ema21):.2f}"
            self._record_alert(
                ts,
                "SIGNAL",
                f"{side} EMA21 green candle crossed above EMA21: "
                f"symbol={side_state.option_symbol or '-'} "
                f"close={float(row['close']):.2f} EMA21={ema_text}; "
                "looking for red confirmation candle",
            )
        if self._is_ema21_strategy() and getattr(side_state, "ema_failure", False):
            if side_state.pending_entry is not None:
                pending = side_state.pending_entry
                if self._cancel_pending_entry_order(side, pending, ts):
                    side_state.pending_entry = None
                    self._record_alert(ts, "CANCEL", f"{side} pending entry cancelled: confirmation EMA failure")
            if side_state.position is not None:
                self._exit_position(
                    side_state,
                    ts,
                    side_state.position.quantity,
                    "Confirmation EMA failure",
                    is_hard_sl=False,
                    row=row,
                )
            remark = "EMA_FAILURE_CLEANUP"
            self._record_trace_row(side, side_state, row, signal, False, remark)
            return

        if (
            self._is_ema21_strategy()
            and side_state.position is not None
            and float(row["close"]) < float(row["ema21"])
        ):
            self._exit_position(
                side_state,
                ts,
                side_state.position.quantity,
                "EMA-21 close exit",
                is_hard_sl=False,
                row=row,
            )
            remark = "EMA_CLOSE_EXIT"
            self._record_trace_row(side, side_state, row, signal, False, remark)
            return

        first_red_time = getattr(side_state, "first_red_time", None)
        if (
            self._is_ema21_strategy()
            and side_state.position is None
            and side_state.pending_entry is None
            and getattr(side_state, "entry_ready", False)
            and first_red_time is not None
        ):
            # A restart's warmup replay runs with entries disabled, so a setup
            # that completes there freezes first_red_time on a stale candle
            # that never got a live generate_signal() call - it would
            # otherwise sit in ENTRY_READY forever. Expire it like a normal
            # pending order instead of leaving the side permanently stuck.
            candle_seconds = max(1, self.cfg.timeframe_minutes * 60)
            # Normalize datetimes to handle timezone-aware vs timezone-naive mismatch
            row_datetime_normalized = row["datetime"].replace(tzinfo=None) if row["datetime"].tzinfo else row["datetime"]
            first_red_time_normalized = first_red_time.replace(tzinfo=None) if first_red_time.tzinfo else first_red_time
            elapsed_seconds = max(0.0, (row_datetime_normalized - first_red_time_normalized).total_seconds())
            if elapsed_seconds // candle_seconds > self.cfg.pending_entry_expiry_candles:
                self._clear_stale_entry_ready(
                    side, side_state, ts,
                    f"entry window expired ({int(elapsed_seconds // candle_seconds)} candles "
                    f"since first_red={first_red_time.strftime('%H:%M')})",
                )
                remark = "ENTRY_READY_EXPIRED"
                self._record_trace_row(side, side_state, row, signal, False, remark)
                return

        signal = self.signal_provider.generate_signal(side, side_state, row, prev_row)

        if signal in (Signal.BUY_CE, Signal.BUY_PE):
            # Log signal for dashboard display
            if self.signal_provider.strategy_key == "ema21":
                try:
                    symbol = side_state.option_symbol or side
                    ts = pd.to_datetime(row.get("datetime", datetime.now()))
                    SignalLogger.log_signal(
                        strategy="EMA21",
                        side=side,
                        signal_type="setup",
                        symbol=symbol,
                        message=f"EMA21 Strategy: {side} setup detected - {symbol}",
                        level="INFO",
                        timestamp=ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts,
                    )
                except Exception as e:
                    logger.warning(f"Could not log signal: {e}")
            
            self._record_alert(
                ts,
                "SIGNAL",
                f"{side} {signal.value} signal at close={float(row['close']):.2f} "
                f"symbol={side_state.option_symbol or '-'} "
                f"EMA21={float(row['ema21']):.2f}" if row.get("ema21") is not None and not pd.isna(row.get("ema21"))
                else f"{side} {signal.value} signal at close={float(row['close']):.2f} "
                f"symbol={side_state.option_symbol or '-'} EMA21=NA",
            )
            had_pending_after_pre_checks = side_state.pending_entry is not None
            self.place_pending_entry(side, side_state, ts, row)
            if side_state.pending_entry is not None and not had_pending_after_pre_checks:
                trade_initiated = True
                remark = "PENDING_ENTRY_CREATED"
            elif side_state.position is not None and not had_position_before:
                trade_initiated = True
                remark = "POSITION_OPENED"
            else:
                remark = "SIGNAL_REJECTED_BY_RISK_OR_STATE"
                if self._is_ema21_strategy() and not side_state.order_submission_uncertain:
                    if getattr(side_state, "entry_ready", False):
                        self._record_alert(
                            ts,
                            "CANCEL",
                            f"{side} EMA21 entry rejected; preserving setup state for visibility",
                        )
                    else:
                        self._record_alert(
                            ts,
                            "CANCEL",
                            f"{side} EMA21 entry rejected; confirmation candle reset",
                        )
        elif self.diagnose:
            self._diagnose_side(side, side_state, ts, row, prev_row)
            reason = self.signal_provider.diagnose_no_signal(side, side_state, row, prev_row)
            remark = f"NO_ENTRY: {reason}" if reason else "NO_ENTRY: SIGNAL_NONE"
        elif side_state.position is not None:
            remark = "POSITION_MANAGEMENT"
        elif side_state.pending_entry is not None:
            remark = "PENDING_ENTRY_WAITING_TRIGGER"
        else:
            reason = self.signal_provider.diagnose_no_signal(side, side_state, row, prev_row)
            remark = f"NO_ENTRY: {reason}" if reason else "NO_ENTRY: SIGNAL_NONE"

        if self.verbose:
            self._print_candle_summary(side, side_state, ts, row)

        self._record_trace_row(side, side_state, row, signal, trade_initiated, remark)

    def process_candle(self, row: pd.Series, prev_row: Optional[pd.Series]) -> None:
        """Feed a single bar to both CE and PE sides."""
        self.process_option_candle("CE", row, prev_row)
        self.process_option_candle("PE", row, prev_row)

    # ── diagnostics / verbose output ────────────────────────────────

    def _diagnose_side(
        self,
        side: str,
        side_state: BaseSideState,
        ts: datetime,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        if self._is_ema21_strategy():
            ema21 = row.get("ema21")
            ema21_text = "NA" if ema21 is None or pd.isna(ema21) else f"{ema21:.2f}"
            base = (
                f"[DIAG] {ts.time()} {side} "
                f"O={row['open']:.2f} H={row['high']:.2f} L={row['low']:.2f} C={row['close']:.2f} "
                f"EMA21={ema21_text}"
            )
        else:
            rsi = row.get("rsi3")
            ema13, ema20, ema50 = row.get("ema13"), row.get("ema20"), row.get("ema50")
            base = (
                f"[DIAG] {ts.time()} {side} "
                f"O={row['open']:.2f} H={row['high']:.2f} L={row['low']:.2f} C={row['close']:.2f} "
                f"rsi={'NA' if pd.isna(rsi) else f'{rsi:.1f}'} "
                f"e13={'NA' if pd.isna(ema13) else f'{ema13:.2f}'} "
                f"e20={'NA' if pd.isna(ema20) else f'{ema20:.2f}'} "
                f"e50={'NA' if pd.isna(ema50) else f'{ema50:.2f}'}"
            )

        # Check generic gates first.
        if self.state.sl_hits_today >= self.risk.max_sl_per_day:
            print(f"{base} -> DAILY_SL_CAP ({self.state.sl_hits_today}/{self.risk.max_sl_per_day})")
            return
        if side_state.position is not None:
            rr = self.compute_rr_progress(side_state.position, row)
            print(f"{base} -> HAS_POSITION qty={side_state.position.quantity} RR={rr:.2f}")
            return
        if side_state.pending_entry is not None:
            pend = side_state.pending_entry
            gap = pend.option_trigger_level - float(row["high"])
            print(f"{base} -> HAS_PENDING trigger={pend.option_trigger_level:.2f} gap={gap:+.2f}")
            return

        # Delegate strategy-specific diagnosis.
        reason = self.signal_provider.diagnose_no_signal(side, side_state, row, prev_row)
        if reason:
            print(f"{base} -> {reason}")

    def _print_candle_summary(
        self,
        side: str,
        side_state: BaseSideState,
        ts: datetime,
        row: pd.Series,
    ) -> None:
        from core.indicators import is_hammer_candle, is_strong_green_candle

        ema21_only = self._is_ema21_strategy()
        if not self._verbose_header_printed:
            indicator_header = "EMA21" if ema21_only else "PATTERN / RSI / TREND"
            print(f"  {'TIME':<5s} │ {'SYMBOL':<22s} │ {'OHLC':<42s} │ {indicator_header}")
            print("  ─────┼" + "─" * 24 + "┼" + "─" * 44 + "┼" + "─" * 30)
            self._verbose_header_printed = True

        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        if ema21_only:
            ema21 = row.get("ema21")
            ema21_str = f"{ema21:.2f}" if ema21 is not None and not pd.isna(ema21) else "--"
            symbol = side_state.option_symbol or side
            print(
                f"  {ts.strftime('%H:%M')} │ {symbol:<22s} │ "
                f"O={o:<7.1f} H={h:<7.1f} L={l:<7.1f} C={c:<7.1f} │ EMA21={ema21_str}"
            )
            if side_state.position is not None:
                pos = side_state.position
                rr = self.compute_rr_progress(pos, row)
                print(f"       │ {'':22s} │ {'':42s} │ IN TRADE entry={pos.entry_price:.1f} SL={pos.option_stop_level:.1f} qty={pos.quantity} RR={rr:.1f}")
            elif side_state.pending_entry is not None:
                pend = side_state.pending_entry
                print(f"       │ {'':22s} │ {'':42s} │ PENDING trigger={pend.option_trigger_level:.1f} SL={pend.option_stop_level:.1f}")
            print("  ─────┼" + "─" * 24 + "┼" + "─" * 44 + "┼" + "─" * 30)
            return

        rsi = row.get("rsi3")
        ema13, ema20, ema50 = row.get("ema13"), row.get("ema20"), row.get("ema50")
        vwap = row.get("vwap")

        total_range = h - l
        body = c - o
        body_pct = (abs(body) / total_range * 100) if total_range > 0 else 0.0

        if is_strong_green_candle(row, 0.85):
            candle_type = "⬆ STRONG_GREEN"
        elif is_hammer_candle(row):
            candle_type = "🔨 HAMMER"
        elif abs(body) <= total_range * 0.1:
            candle_type = "➖ DOJI"
        elif body > 0:
            candle_type = "🟢 GREEN"
        else:
            candle_type = "🔴 RED"

        na = lambda v: "NA" if v is None or (isinstance(v, float) and pd.isna(v)) else v
        ema13_v, ema20_v, ema50_v = na(ema13), na(ema20), na(ema50)
        if ema13_v != "NA" and ema20_v != "NA" and ema50_v != "NA":
            trend = "📈 BULL" if (ema13 > ema20 or ema20 > ema50) else "📉 BEAR"
        else:
            trend = "--"

        div_state = self.signal_provider.format_setup_status(side_state)

        if side_state.position is not None:
            pos = side_state.position
            rr = self.compute_rr_progress(pos, row)
            pos_info = f"🟡 IN TRADE  entry={pos.entry_price:.1f}  SL={pos.option_stop_level:.1f}  qty={pos.quantity}  RR={rr:.1f}"
        elif side_state.pending_entry is not None:
            pend = side_state.pending_entry
            pos_info = f"⏫ PENDING  trigger={pend.option_trigger_level:.1f}  SL={pend.option_stop_level:.1f}"
        else:
            pos_info = "FLAT"

        rsi_str = f"{rsi:.1f}" if rsi is not None and not pd.isna(rsi) else "--"
        vwap_str = f"{vwap:.1f}" if vwap is not None and not pd.isna(vwap) else "--"
        symbol = side_state.option_symbol or side

        print(
            f"  {ts.strftime('%H:%M')} │ {symbol:<22s} │ "
            f"O={o:<7.1f} H={h:<7.1f} L={l:<7.1f} C={c:<7.1f} │ "
            f"{candle_type:<14s} body {body_pct:>3.0f}% │ RSI {rsi_str:>5s}  {trend}"
        )
        print(
            f"       │ {'':22s} │ "
            f"VWAP={vwap_str:<8s} SL_hits={self.state.sl_hits_today}/{self.risk.max_sl_per_day}{'':9s} │ "
            f"{div_state}"
        )
        if pos_info != "FLAT":
            print(f"       │ {'':22s} │ {'':42s} │ {pos_info}")
        print("  ─────┼" + "─" * 24 + "┼" + "─" * 44 + "┼" + "─" * 30)
