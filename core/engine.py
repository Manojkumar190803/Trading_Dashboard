from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

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
from strategies.base import SignalProvider

logger = logging.getLogger("core.engine")


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

    # ── helpers ──────────────────────────────────────────────────────

    def _record_alert(self, ts: datetime, category: str, message: str) -> None:
        self.alerts.append(StrategyAlert(timestamp=ts, category=category, message=message))
        if len(self.alerts) > 500:
            self.alerts = self.alerts[-500:]
        print(f"[ENGINE][{category}] {message}")

    @staticmethod
    def _fmt_candle_context(row: pd.Series, symbol: str) -> str:
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

    def _get_unrealized_pnl(self) -> float:
        pnl = 0.0
        for side_state in (self.state.ce, self.state.pe):
            pos = side_state.position
            if pos is None:
                continue
            option_ltp = self.broker.get_ltp(pos.option_symbol)
            pnl += (option_ltp - pos.entry_price) * pos.quantity
        return pnl

    def _exit_position(
        self,
        side_state: BaseSideState,
        ts: datetime,
        quantity: int,
        reason: str,
        is_hard_sl: bool = False,
        row: Optional[pd.Series] = None,
    ) -> None:
        pos = side_state.position
        if pos is None:
            return

        qty = min(quantity, pos.quantity)
        if qty <= 0:
            return

        exit_ltp = self.broker.get_ltp(pos.option_symbol)
        self.broker.place_market_order(pos.option_symbol, OrderSide.SELL, qty)

        trade_pnl = (exit_ltp - pos.entry_price) * qty
        self.realized_pnl += trade_pnl

        pos.quantity -= qty
        self._record_alert(
            ts,
            "EXIT",
            f"{reason}: exited qty={qty} at {exit_ltp:.2f}, "
            f"trade_pnl={trade_pnl:.2f}, remaining={pos.quantity}",
        )
        if row is not None:
            print(self._fmt_candle_context(row, pos.option_symbol))

        if pos.quantity <= 0:
            side_state.position = None

        if is_hard_sl:
            self.state.sl_hits_today += 1
            self.total_hard_sl_hits += 1
            if self.state.sl_hits_today >= self.risk.max_sl_per_day:
                self._record_alert(
                    ts,
                    "RISK",
                    f"Daily SL cap reached ({self.state.sl_hits_today}/"
                    f"{self.risk.max_sl_per_day}) — no new entries today",
                )

    def get_status_snapshot(self) -> dict:
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

    def lock_atm_for_day(self, ts: datetime, spot_price: float) -> None:
        if self.state.atm_locked:
            return
        expiry_day = choose_weekly_expiry_for_entry(ts.date(), self.cfg.weekly_expiry_weekday)
        expiry_code = format_expiry_code(expiry_day)
        strike = get_atm_strike(spot_price, self.cfg.strike_step)
        ce_symbol = build_option_symbol(self.cfg.option_index_symbol, expiry_code, strike, "CE")
        pe_symbol = build_option_symbol(self.cfg.option_index_symbol, expiry_code, strike, "PE")
        self.state.ce_symbol = ce_symbol
        self.state.pe_symbol = pe_symbol
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

    def place_pending_entry(
        self,
        side: str,
        side_state: BaseSideState,
        ts: datetime,
        row: pd.Series,
    ) -> None:
        if side_state.position is not None or side_state.pending_entry is not None:
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

        if risk_points > self.cfg.max_option_risk_points:
            self._record_alert(
                ts, "RISK",
                f"{side} trade cancelled: risk {risk_points:.2f} > {self.cfg.max_option_risk_points:.2f}",
            )
            return

        # VWAP room filter: entry below VWAP must have at least 1.5 RR of headroom.
        entry_level = float(row["high"] + 1.0)
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

        trigger_level = float(row["high"] + 1.0)
        stop_level = self.signal_provider.compute_stop_level(side_state, row)

        side_state.pending_entry = PendingEntry(
            signal=Signal.BUY_CE if side == "CE" else Signal.BUY_PE,
            created_at=ts,
            option_symbol=side_state.option_symbol,
            quantity=quantity,
            option_trigger_level=trigger_level,
            option_stop_level=stop_level,
            trigger_candle_high=float(row["high"]),
            trigger_candle_low=float(row["low"]),
        )

        self._record_alert(
            ts, "PENDING_ENTRY",
            f"Pending {side} {side_state.option_symbol} qty={quantity} "
            f"trigger={trigger_level:.2f} SL={stop_level:.2f} lots={lots} "
            f"option_risk={risk_points:.2f}",
        )
        print(self._fmt_candle_context(row, side_state.option_symbol))

    def try_fill_pending_entry(
        self,
        side: str,
        side_state: BaseSideState,
        ts: datetime,
        row: pd.Series,
    ) -> None:
        pending = side_state.pending_entry
        if pending is None:
            return

        # Cancel pending if SL level is breached before entry triggers.
        if float(row["low"]) <= pending.option_stop_level:
            self._record_alert(
                ts, "CANCEL",
                f"{side} pending cancelled: SL breached (low={row['low']:.2f} <= SL={pending.option_stop_level:.2f})",
            )
            side_state.pending_entry = None
            return

        if float(row["high"]) < pending.option_trigger_level:
            return

        option_symbol = pending.option_symbol
        option_ltp = self.broker.get_ltp(option_symbol)
        risk_points = abs(pending.option_trigger_level - pending.option_stop_level)

        # FRD §5.1: entry via STOP_LIMIT (trigger + 0.5 limit buffer).
        limit_price = pending.option_trigger_level + 0.5
        self.broker.place_stop_limit_order(
            option_symbol, OrderSide.BUY, pending.quantity,
            trigger_price=pending.option_trigger_level,
            limit_price=limit_price,
        )

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
        side_state.pending_entry = None
        self.total_entries += 1
        self.signal_provider.reset_after_entry(side_state)

        self._record_alert(
            ts, "ENTRY",
            f"Entered {side} {option_symbol} @ {option_ltp:.2f}, "
            f"trigger={pending.option_trigger_level:.2f}, "
            f"SL={pending.option_stop_level:.2f}, option_risk={risk_points:.2f}",
        )
        print(self._fmt_candle_context(row, option_symbol))

    # ── position monitoring ────────────────────────────────────────

    @staticmethod
    def compute_rr_progress(pos: Position, row: pd.Series) -> float:
        if pos.option_risk_points <= 0:
            return 0.0
        favorable_move = float(row["high"]) - pos.option_entry_trigger
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
        )

    def manage_targets(self, side_state: BaseSideState, row: pd.Series) -> None:
        """FRD §6: Step-trailing SL logic.

        - 1-lot: full exit at 1.5 RR.
        - 2-lot: at 1.5 RR arm BE, at 2.0 RR book 1 lot + start trailing,
          then trail remaining lot every 0.5 RR indefinitely.
        """
        pos = side_state.position
        if pos is None:
            return

        rr = self.compute_rr_progress(pos, row)
        lot_qty = self.cfg.option_lot_size
        ir = pos.option_risk_points

        # 1-lot path: full exit at 1.5 RR.
        if pos.initial_quantity == lot_qty:
            if rr >= self.cfg.t1_rr and not pos.t1_done:
                self.execute_partial_exit(
                    side_state, pos.quantity,
                    f"Target hit (1:{self.cfg.t1_rr} RR) - full exit (1-lot)",
                )
                pos.t1_done = True
            return

        # 2-lot path with step-trailing.
        # Phase 2: At 1.5 RR — arm breakeven.
        if rr >= self.cfg.t1_rr and not pos.t1_done:
            pos.breakeven_armed = True
            pos.t1_done = True
            pos.trailing_sl_level = pos.entry_price
            pos.highest_rr_step = 1.5
            self._record_alert(
                self.last_processed_candle_time or pos.entry_time,
                "TARGET",
                f"{pos.option_type} 1.5 RR hit — SL moved to entry (breakeven)",
            )

        # Phase 3: At 2.0 RR — partial exit 1 lot.
        if rr >= self.cfg.t2_rr and not pos.t2_done:
            self.execute_partial_exit(
                side_state, lot_qty,
                f"2.0 RR hit — booked 1 lot",
            )
            if side_state.position is None:
                return
            side_state.position.t2_done = True

        # Step-trailing: advance SL every 0.5 RR above 1.5.
        if pos.breakeven_armed and ir > 0:
            current_step = int(rr / 0.5) * 0.5  # floor to nearest 0.5
            if current_step > pos.highest_rr_step:
                # SL trails 1.5 RR behind the current step.
                new_sl = pos.entry_price + (current_step - 1.5) * ir
                if pos.trailing_sl_level is None or new_sl > pos.trailing_sl_level:
                    pos.trailing_sl_level = new_sl
                    pos.highest_rr_step = current_step
                    self._record_alert(
                        self.last_processed_candle_time or pos.entry_time,
                        "TSL",
                        f"{pos.option_type} {current_step:.1f} RR — TSL raised to {new_sl:.2f}",
                    )

    def check_trailing_stop(self, side_state: BaseSideState, row: Optional[pd.Series] = None) -> None:
        """Exit if LTP drops to or below the trailing SL level."""
        pos = side_state.position
        if pos is None or not pos.breakeven_armed:
            return
        sl_level = pos.trailing_sl_level if pos.trailing_sl_level is not None else pos.entry_price
        option_ltp = self.broker.get_ltp(pos.option_symbol)
        if option_ltp <= sl_level:
            self._exit_position(
                side_state,
                self.last_processed_candle_time or pos.entry_time,
                pos.quantity,
                f"Trailing stop hit: LTP {option_ltp:.2f} <= TSL {sl_level:.2f}",
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
        side_state.pending_entry = None
        pos = side_state.position
        if pos is None:
            return
        self._exit_position(
            side_state, ts, pos.quantity,
            f"Forced square-off at {ts.time()} for {pos.option_symbol}",
            is_hard_sl=False,
        )

    # ── tick-level monitoring (FRD §5.2 / §6) ──────────────────────

    def process_tick(self, side: str, ltp: float, ts: datetime) -> None:
        """Called on every WebSocket tick for a side with an active position.

        Handles:
        - Hard SL exit
        - Step-trailing SL advancement + exit
        - Partial exit at 2.0 RR
        - 1-lot full exit at 1.5 RR
        """
        side_state = self._side_state(side)
        pos = side_state.position
        if pos is None:
            return

        self.last_processed_candle_time = ts
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
        rr = (ltp - pos.option_entry_trigger) / ir
        lot_qty = self.cfg.option_lot_size

        # 1-lot: full exit at 1.5 RR.
        if pos.initial_quantity == lot_qty:
            if rr >= self.cfg.t1_rr and not pos.t1_done:
                pos.t1_done = True
                self._exit_position(
                    side_state, ts, pos.quantity,
                    f"Target hit (tick): {self.cfg.t1_rr} RR — full exit (1-lot)",
                    is_hard_sl=False,
                )
            return

        # 2-lot path.
        # Phase 2: 1.5 RR — arm breakeven.
        if rr >= self.cfg.t1_rr and not pos.t1_done:
            pos.breakeven_armed = True
            pos.t1_done = True
            pos.trailing_sl_level = pos.entry_price
            pos.highest_rr_step = 1.5
            self._record_alert(ts, "TSL", f"{pos.option_type} 1.5 RR (tick) — SL to entry")

        # Phase 3: 2.0 RR — partial exit.
        if rr >= self.cfg.t2_rr and not pos.t2_done:
            self.execute_partial_exit(side_state, lot_qty, f"2.0 RR (tick) — booked 1 lot")
            if side_state.position is None:
                return
            side_state.position.t2_done = True
            pos = side_state.position

        # Step-trailing SL advancement.
        if pos.breakeven_armed and ir > 0:
            current_step = int(rr / 0.5) * 0.5
            if current_step > pos.highest_rr_step:
                new_sl = pos.entry_price + (current_step - 1.5) * ir
                if pos.trailing_sl_level is None or new_sl > pos.trailing_sl_level:
                    pos.trailing_sl_level = new_sl
                    pos.highest_rr_step = current_step
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
    ) -> None:
        ts = row["datetime"]
        self.last_processed_candle_time = ts
        self.on_day_transition_if_needed(ts)

        side_state = self._side_state(side)

        # Update indicator cache for status display.
        side_state.last_close = float(row["close"])
        rsi_val = row.get("rsi3")
        side_state.last_rsi = None if (rsi_val is None or pd.isna(rsi_val)) else float(rsi_val)
        for attr, col in (("last_ema13", "ema13"), ("last_ema20", "ema20"), ("last_ema50", "ema50")):
            v = row.get(col)
            setattr(side_state, attr, None if (v is None or pd.isna(v)) else float(v))

        if self.must_force_square_off(ts):
            self.force_square_off_side(side_state, ts)
            return

        if not self.in_trade_window(ts):
            return

        if side_state.option_symbol is None:
            return

        if not self.in_signal_window(ts):
            if side_state.pending_entry is not None:
                side_state.pending_entry = None
                self._record_alert(ts, "SESSION", f"{side} pending entry cancelled at signal cutoff")
            self.monitor_open_position(side_state, row)
            return

        self.try_fill_pending_entry(side, side_state, ts, row)
        self.monitor_open_position(side_state, row)

        # Delegate signal generation to the strategy provider.
        self.signal_provider.update_state(side_state, row, prev_row)
        signal = self.signal_provider.generate_signal(side, side_state, row, prev_row)

        if signal in (Signal.BUY_CE, Signal.BUY_PE):
            self.place_pending_entry(side, side_state, ts, row)
        elif self.diagnose:
            self._diagnose_side(side, side_state, ts, row, prev_row)

        if self.verbose:
            self._print_candle_summary(side, side_state, ts, row)

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

        if not self._verbose_header_printed:
            print(f"  {'TIME':<5s} │ {'SYMBOL':<22s} │ {'OHLC':<42s} │ {'PATTERN / RSI / TREND'}")
            print("  ─────┼" + "─" * 24 + "┼" + "─" * 44 + "┼" + "─" * 30)
            self._verbose_header_printed = True

        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
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
