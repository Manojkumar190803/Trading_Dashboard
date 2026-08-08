from __future__ import annotations

import argparse
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

import pandas as pd
import re

logger = logging.getLogger("hd_strategy")


class Signal(str, Enum):
    NONE = "NONE"
    BUY_CE = "BUY_CE"
    BUY_PE = "BUY_PE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class StrategyConfig:
    # ── Spot (used only to pick the ATM strike at 09:20) ─────────────
    spot_symbol: str = "NIFTY"
    exchange_spot: str = "NSE_INDEX"

    # ── Option instrument ────────────────────────────────────────────
    exchange_options: str = "NFO"
    option_index_symbol: str = "NIFTY"
    strike_step: int = 50
    option_lot_size: int = 65
    full_size_lots: int = 2
    half_size_lots: int = 1
    weekly_expiry_weekday: int = 1  # Monday=0 ... Tuesday=1

    # ── Timing (all in IST) ──────────────────────────────────────────
    timeframe_minutes: int = 3
    market_open: time = time(9, 20)
    market_close: time = time(15, 15)
    force_square_off: time = time(15, 15)
    # No new signals or pending entries after this time; open positions still managed.
    signal_cutoff: time = time(15, 0)
    atm_lock_time: time = time(9, 20)  # ATM strike is anchored at this timestamp

    # ── Indicators (applied to the option premium chart) ─────────────
    ema_fast: int = 13
    ema_mid: int = 20
    ema_slow: int = 50
    rsi_length: int = 3

    # Minimum body/range ratio to qualify as a "strong green" trigger candle.
    strong_body_threshold: float = 0.85

    # ── Risk (all on option premium points) ──────────────────────────
    # If the pre-entry swing-to-high range on the option premium exceeds
    # this, the signal is skipped.
    max_option_risk_points: float = 20.0

    enable_default_signal_rules: bool = True


@dataclass
class RiskConfig:
    # Trading closes for the day once this many hard-SL exits have fired.
    max_sl_per_day: int = 3


@dataclass
class Position:
    option_symbol: str
    option_type: str  # CE or PE
    quantity: int
    initial_quantity: int
    entry_price: float
    entry_time: datetime
    option_stop_level: float
    option_entry_trigger: float
    option_risk_points: float
    t1_done: bool = False
    t2_done: bool = False
    t3_done: bool = False
    breakeven_armed: bool = False


@dataclass
class PendingEntry:
    signal: Signal
    created_at: datetime
    option_symbol: str
    quantity: int
    option_trigger_level: float
    option_stop_level: float
    trigger_candle_high: float
    trigger_candle_low: float


@dataclass
class StrategyAlert:
    timestamp: datetime
    category: str
    message: str


@dataclass
class SideState:
    """Per-option-side (CE or PE) divergence tracker + position + pending.

    A 'bullish' RSI-divergence setup on the option's own premium chart
    generates a BUY signal (for the CE side that's a BUY_CE, for the PE
    side that's a BUY_PE — bearish setups don't exist because buying
    a PE when the PE premium is rising is already the bearish view).
    """

    option_symbol: Optional[str] = None  # locked at 09:20
    position: Optional[Position] = None
    pending_entry: Optional[PendingEntry] = None
    # RSI-divergence trackers on the option premium.
    swing_low_active: bool = False
    swing_low: Optional[float] = None
    pullback_active: bool = False
    pullback_low_price: Optional[float] = None
    pullback_low_rsi: Optional[float] = None
    p1_price: Optional[float] = None
    p1_rsi: Optional[float] = None
    p2_price: Optional[float] = None
    p2_rsi: Optional[float] = None
    divergence_ready: bool = False
    # Last candle indicators (updated every bar for status display).
    last_close: Optional[float] = None
    last_rsi: Optional[float] = None
    last_ema13: Optional[float] = None
    last_ema20: Optional[float] = None
    last_ema50: Optional[float] = None


@dataclass
class DayState:
    trading_day: Optional[date] = None
    atm_locked: bool = False
    ce_symbol: Optional[str] = None
    pe_symbol: Optional[str] = None
    sl_hits_today: int = 0
    ce: SideState = field(default_factory=SideState)
    pe: SideState = field(default_factory=SideState)


class BrokerInterface:
    """Replace these methods with your broker API implementation."""

    def get_ltp(self, symbol: str) -> float:
        raise NotImplementedError

    def place_stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        trigger_price: float,
        limit_price: float,
    ) -> str:
        raise NotImplementedError

    def place_market_order(self, symbol: str, side: OrderSide, quantity: int) -> str:
        raise NotImplementedError


class ConsoleBroker(BrokerInterface):
    """Simple console broker to verify the control flow before live API wiring."""

    def __init__(self, ltp_fallback: float = 100.0) -> None:
        self.ltp_fallback = ltp_fallback

    def get_ltp(self, symbol: str) -> float:
        print(f"[BROKER] get_ltp {symbol} -> {self.ltp_fallback}")
        return self.ltp_fallback

    def place_stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        trigger_price: float,
        limit_price: float,
    ) -> str:
        oid = f"SL-L-{symbol}-{side}-{quantity}"
        print(
            "[BROKER] place_stop_limit_order "
            f"symbol={symbol} side={side} qty={quantity} trigger={trigger_price:.2f} limit={limit_price:.2f} id={oid}"
        )
        return oid

    def place_market_order(self, symbol: str, side: OrderSide, quantity: int) -> str:
        oid = f"MKT-{symbol}-{side}-{quantity}"
        print(f"[BROKER] place_market_order symbol={symbol} side={side} qty={quantity} id={oid}")
        return oid


def load_spot_ohlcv_csv(csv_path: Path) -> pd.DataFrame:
    """Load OHLCV data from a CSV file.
    
    Expected columns: index, datetime (ISO), open, high, low, close, volume
    Returns a DataFrame with 'datetime' parsed to pandas datetime and 'volume' as numeric.
    """
    df = pd.read_csv(csv_path, index_col=0)
    df.columns = ["datetime", "open", "high", "low", "close", "volume"]
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    return df


def compute_rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def add_indicators(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    data = df.copy()
    data["ema13"] = data["close"].ewm(span=cfg.ema_fast, adjust=False).mean()
    data["ema20"] = data["close"].ewm(span=cfg.ema_mid, adjust=False).mean()
    data["ema50"] = data["close"].ewm(span=cfg.ema_slow, adjust=False).mean()

    # Intraday VWAP resets daily by grouping on session date.
    data["session_date"] = data["datetime"].dt.date
    pv = data["close"] * data["volume"]
    data["vwap"] = pv.groupby(data["session_date"]).cumsum() / data["volume"].groupby(data["session_date"]).cumsum()

    data["rsi3"] = compute_rsi(data["close"], cfg.rsi_length)
    return data


def get_atm_strike(spot_price: float, strike_step: int) -> int:
    return int(round(spot_price / strike_step) * strike_step)


def build_option_symbol(index_name: str, expiry_code: str, strike: int, option_type: str) -> str:
    # Example: NIFTY04AUG2624050CE  (DD MMM YY STRIKE CE/PE)
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
    # OpenAlgo NFO symbols use DD MMM YY (e.g. 04AUG26).
    return expiry_day.strftime("%d%b%y").upper()


class HDStrategyEngine:
    def __init__(self, cfg: StrategyConfig, risk: RiskConfig, broker: BrokerInterface) -> None:
        self.cfg = cfg
        self.risk = risk
        self.broker = broker
        self.state = DayState()
        self.alerts: list[StrategyAlert] = []
        self.realized_pnl: float = 0.0
        self.last_processed_candle_time: Optional[datetime] = None
        self.total_entries: int = 0  # lifetime counter across sides & days
        self.total_hard_sl_hits: int = 0  # lifetime counter across sides & days
        self.diagnose: bool = False  # when True, prints per-candle signal-gate reason
        self.verbose: bool = False  # when True, prints a full candle summary every bar
        self._verbose_header_printed: bool = False

    # ── helpers ──────────────────────────────────────────────────────

    def _record_alert(self, ts: datetime, category: str, message: str) -> None:
        self.alerts.append(StrategyAlert(timestamp=ts, category=category, message=message))
        if len(self.alerts) > 500:
            self.alerts = self.alerts[-500:]
        print(f"[ENGINE][{category}] {message}")

    def _side_state(self, side: str) -> SideState:
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
        side_state: SideState,
        ts: datetime,
        quantity: int,
        reason: str,
        is_hard_sl: bool = False,
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
            (
                f"{reason}: exited qty={qty} at {exit_ltp:.2f}, "
                f"trade_pnl={trade_pnl:.2f}, remaining={pos.quantity}"
            ),
        )

        if pos.quantity <= 0:
            side_state.position = None

        # Only hard SL hits contribute to the daily-SL cutoff.
        if is_hard_sl:
            self.state.sl_hits_today += 1
            self.total_hard_sl_hits += 1
            if self.state.sl_hits_today >= self.risk.max_sl_per_day:
                self._record_alert(
                    ts,
                    "RISK",
                    (
                        f"Daily SL cap reached ({self.state.sl_hits_today}/"
                        f"{self.risk.max_sl_per_day}) — no new entries today"
                    ),
                )

    def get_status_snapshot(self) -> dict:
        unrealized_pnl = self._get_unrealized_pnl()
        total_pnl = self.realized_pnl + unrealized_pnl

        def _side_payload(side_state: SideState) -> dict:
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
        self.state = DayState(trading_day=new_day)
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
        """Called once per day (at/after 09:20) to fix the CE and PE we watch."""
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
        print(f"│ {'HD STRATEGY — STRIKES LOCKED':^58s} │")
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
            ts,
            "ATM_LOCK",
            f"Strike {strike} | CE={ce_symbol} | PE={pe_symbol}",
        )

    # ── candle pattern helpers ──────────────────────────────────────

    @staticmethod
    def is_strong_green_candle(row: pd.Series, threshold: float = 0.9) -> bool:
        total_range = row["high"] - row["low"]
        if total_range <= 0:
            return False
        body = row["close"] - row["open"]
        return body > 0 and (body / total_range) >= threshold

    @staticmethod
    def is_hammer_candle(row: pd.Series) -> bool:
        total_range = row["high"] - row["low"]
        if total_range <= 0:
            return False
        body = abs(row["close"] - row["open"])
        if body == 0:
            return False
        lower_wick = min(row["open"], row["close"]) - row["low"]
        upper_wick = row["high"] - max(row["open"], row["close"])
        return lower_wick >= 2 * body and upper_wick <= body

    # ── divergence state machine (per side, on option premium) ─────

    def update_bullish_setup_state(
        self,
        side_state: SideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        rsi = row["rsi3"]
        if pd.isna(rsi):
            return
        prev_rsi = prev_row["rsi3"] if prev_row is not None else None
        prev_rsi_valid = prev_rsi is not None and not pd.isna(prev_rsi)

        crossed_below_20 = prev_rsi_valid and prev_rsi >= 20 and rsi < 20
        crossed_above_20 = prev_rsi_valid and prev_rsi <= 20 and rsi > 20

        if crossed_below_20:
            side_state.swing_low_active = True
            side_state.swing_low = row["low"]
            side_state.pullback_active = True
            side_state.pullback_low_price = row["low"]
            side_state.pullback_low_rsi = rsi
            side_state.divergence_ready = False

        if side_state.swing_low_active:
            if side_state.swing_low is None:
                side_state.swing_low = row["low"]
            else:
                side_state.swing_low = min(side_state.swing_low, row["low"])

        if side_state.pullback_active and rsi < 20:
            if side_state.pullback_low_price is None:
                side_state.pullback_low_price = row["low"]
            else:
                side_state.pullback_low_price = min(side_state.pullback_low_price, row["low"])
            if side_state.pullback_low_rsi is None:
                side_state.pullback_low_rsi = rsi
            else:
                side_state.pullback_low_rsi = min(side_state.pullback_low_rsi, rsi)

        if side_state.pullback_active and crossed_above_20:
            finished_price = side_state.pullback_low_price
            finished_rsi = side_state.pullback_low_rsi
            if finished_price is not None and finished_rsi is not None:
                if side_state.p1_price is None or side_state.p1_rsi is None:
                    side_state.p1_price = finished_price
                    side_state.p1_rsi = finished_rsi
                    side_state.p2_price = None
                    side_state.p2_rsi = None
                    side_state.divergence_ready = False
                else:
                    side_state.p2_price = finished_price
                    side_state.p2_rsi = finished_rsi
                    side_state.divergence_ready = (
                        side_state.p2_price > side_state.p1_price
                        and side_state.p2_rsi < side_state.p1_rsi
                    )
            side_state.pullback_active = False
            side_state.pullback_low_price = None
            side_state.pullback_low_rsi = None

    @staticmethod
    def reset_setup_after_entry(side_state: SideState) -> None:
        side_state.swing_low_active = False
        side_state.swing_low = None
        side_state.pullback_active = False
        side_state.pullback_low_price = None
        side_state.pullback_low_rsi = None
        side_state.p1_price = None
        side_state.p1_rsi = None
        side_state.p2_price = None
        side_state.p2_rsi = None
        side_state.divergence_ready = False

    # ── signal generation ──────────────────────────────────────────

    def generate_signal(
        self,
        side: str,
        side_state: SideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Signal:
        if not self.cfg.enable_default_signal_rules:
            return Signal.NONE

        self.update_bullish_setup_state(side_state, row, prev_row)

        # Never generate a fresh signal while the same side already has a position or pending fill.
        if side_state.position is not None or side_state.pending_entry is not None:
            return Signal.NONE

        bullish_trend = (row["ema13"] > row["ema20"]) or (row["ema20"] > row["ema50"])
        trigger_ok = (
            self.is_strong_green_candle(row, self.cfg.strong_body_threshold)
            or self.is_hammer_candle(row)
        )
        if (
            side_state.p1_price is not None
            and side_state.p2_price is not None
            and bullish_trend
            and side_state.divergence_ready
            and trigger_ok
        ):
            return Signal.BUY_CE if side == "CE" else Signal.BUY_PE

        return Signal.NONE

    def compute_option_risk_points(self, side_state: SideState, row: pd.Series) -> Optional[float]:
        if side_state.swing_low is None:
            return None
        return float(row["high"] - side_state.swing_low)

    def _diagnose_side_gate(self, side: str, side_state: SideState, ts: datetime, row: pd.Series) -> None:
        """Print a one-line explanation of why `side` did not open a new
        pending entry on this candle. Only called when `self.diagnose` is True.
        """
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

        def emit(reason: str) -> None:
            print(f"{base} -> {reason}")

        # 1. Daily SL cap already tripped.
        if self.state.sl_hits_today >= self.risk.max_sl_per_day:
            emit(f"DAILY_SL_CAP ({self.state.sl_hits_today}/{self.risk.max_sl_per_day})")
            return

        # 2. Side already has an open position — show RR progress.
        if side_state.position is not None:
            rr = self.compute_rr_progress(side_state.position, row)
            emit(
                f"HAS_POSITION qty={side_state.position.quantity} "
                f"entry_trigger={side_state.position.option_entry_trigger:.2f} "
                f"SL={side_state.position.option_stop_level:.2f} rr={rr:.2f}"
            )
            return

        # 3. Side has a pending stop-buy — show trigger gap.
        if side_state.pending_entry is not None:
            pend = side_state.pending_entry
            gap = pend.option_trigger_level - float(row["high"])
            emit(
                f"HAS_PENDING trigger={pend.option_trigger_level:.2f} "
                f"SL={pend.option_stop_level:.2f} gap_to_trigger={gap:+.2f}"
            )
            return

        # 4. Divergence not yet formed.
        if side_state.p1_price is None:
            state = "swing_low_active" if side_state.swing_low_active else "waiting_for_rsi<20"
            pull = "pullback_active" if side_state.pullback_active else "no_pullback"
            emit(f"NO_P1 ({state}, {pull})")
            return
        if side_state.p2_price is None:
            emit(
                f"NO_P2 (have p1: price={side_state.p1_price:.2f} rsi={side_state.p1_rsi:.1f}; "
                f"waiting for second pullback cross-above-20)"
            )
            return
        if not side_state.divergence_ready:
            emit(
                f"DIV_NOT_ARMED (p1={side_state.p1_price:.2f}/{side_state.p1_rsi:.1f}, "
                f"p2={side_state.p2_price:.2f}/{side_state.p2_rsi:.1f}; "
                f"need p2_price>p1_price AND p2_rsi<p1_rsi)"
            )
            return

        # 5. Divergence armed — check trend + trigger candle.
        bullish_trend = (ema13 > ema20) or (ema20 > ema50)
        if not bullish_trend:
            emit(
                f"EMA_TREND_FAIL (need ema13>ema20 OR ema20>ema50; got "
                f"{ema13:.2f} vs {ema20:.2f} vs {ema50:.2f})"
            )
            return

        strong_green = self.is_strong_green_candle(row, self.cfg.strong_body_threshold)
        hammer = self.is_hammer_candle(row)
        if not (strong_green or hammer):
            total = row["high"] - row["low"]
            body = row["close"] - row["open"]
            body_pct = (body / total * 100) if total > 0 else 0.0
            emit(
                f"NO_TRIGGER_CANDLE (need body >= {self.cfg.strong_body_threshold*100:.0f}% of range OR hammer; "
                f"body={body:+.2f}={body_pct:.0f}% of range={total:.2f})"
            )
            return

        # 6. All gates passed but this was called after generate_signal returned NONE,
        #    which shouldn't happen — leave a marker so we can spot logic drift.
        emit("SIGNAL_OK (unexpected — signal should have fired)")

    def compute_lots_from_vwap(self, row: pd.Series) -> int:
        premium = float(row["close"])
        vwap = float(row["vwap"])
        if pd.isna(vwap):
            return self.cfg.half_size_lots
        return self.cfg.full_size_lots if premium > vwap else self.cfg.half_size_lots

    def place_pending_entry(
        self,
        side: str,
        side_state: SideState,
        ts: datetime,
        row: pd.Series,
    ) -> None:
        if side_state.position is not None or side_state.pending_entry is not None:
            return

        if self.state.sl_hits_today >= self.risk.max_sl_per_day:
            self._record_alert(
                ts,
                "RISK",
                f"Trade skipped: daily SL cap reached ({self.state.sl_hits_today}/{self.risk.max_sl_per_day})",
            )
            return

        if side_state.option_symbol is None:
            self._record_alert(ts, "RISK", f"{side} trade skipped: ATM symbol not locked yet")
            return

        risk_points = self.compute_option_risk_points(side_state, row)
        if risk_points is None:
            self._record_alert(
                ts,
                "RISK",
                f"{side} trade cancelled: missing swing reference for risk calculation",
            )
            return

        if risk_points > self.cfg.max_option_risk_points:
            self._record_alert(
                ts,
                "RISK",
                (
                    f"{side} trade cancelled: option risk {risk_points:.2f} > "
                    f"{self.cfg.max_option_risk_points:.2f}"
                ),
            )
            return

        lots = self.compute_lots_from_vwap(row)
        quantity = lots * self.cfg.option_lot_size

        trigger_level = float(row["high"] + 1.0)
        stop_level = float((side_state.swing_low or row["low"]) - 1.0)

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
            ts,
            "PENDING_ENTRY",
            (
                f"Pending {side} {side_state.option_symbol} qty={quantity} "
                f"trigger={trigger_level:.2f} SL={stop_level:.2f} lots={lots} "
                f"option_risk={risk_points:.2f}"
            ),
        )

    def try_fill_pending_entry(
        self,
        side: str,
        side_state: SideState,
        ts: datetime,
        row: pd.Series,
    ) -> None:
        pending = side_state.pending_entry
        if pending is None:
            return

        # Both sides use an upward break on the option premium.
        if float(row["high"]) < pending.option_trigger_level:
            return

        option_symbol = pending.option_symbol
        option_ltp = self.broker.get_ltp(option_symbol)
        risk_points = abs(pending.option_trigger_level - pending.option_stop_level)

        self.broker.place_market_order(option_symbol, OrderSide.BUY, pending.quantity)

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
        self.reset_setup_after_entry(side_state)

        self._record_alert(
            ts,
            "ENTRY",
            (
                f"Entered {side} {option_symbol} @ {option_ltp:.2f}, "
                f"trigger={pending.option_trigger_level:.2f}, "
                f"SL={pending.option_stop_level:.2f}, option_risk={risk_points:.2f}"
            ),
        )

    # ── position monitoring ────────────────────────────────────────

    @staticmethod
    def compute_rr_progress(pos: Position, row: pd.Series) -> float:
        if pos.option_risk_points <= 0:
            return 0.0
        favorable_move = float(row["high"]) - pos.option_entry_trigger
        return favorable_move / pos.option_risk_points

    def execute_partial_exit(
        self,
        side_state: SideState,
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

    def manage_targets(self, side_state: SideState, row: pd.Series) -> None:
        pos = side_state.position
        if pos is None:
            return

        rr = self.compute_rr_progress(pos, row)
        lot_qty = self.cfg.option_lot_size

        # 1-lot path: full exit at 1:1.5 RR.
        if pos.initial_quantity == lot_qty:
            if rr >= 1.5:
                self.execute_partial_exit(side_state, pos.quantity, "Target 1 hit (1:1.5 RR) - full exit")
            return

        # 2-lot path: T1 arms BE → T2 books 1 lot → T3 books remainder.
        if pos.initial_quantity == 2 * lot_qty:
            if rr >= 1.5 and not pos.t1_done:
                pos.breakeven_armed = True
                pos.t1_done = True
                self._record_alert(
                    self.last_processed_candle_time or pos.entry_time,
                    "TARGET",
                    f"{pos.option_type} Target 1 hit (1:1.5 RR) - breakeven armed",
                )

            if rr >= 2.0 and not pos.t2_done:
                self.execute_partial_exit(side_state, lot_qty, "Target 2 hit (1:2.0 RR) - booked 1 lot")
                if side_state.position is None:
                    return
                side_state.position.t2_done = True

            if rr >= 2.5 and side_state.position is not None and not side_state.position.t3_done:
                self.execute_partial_exit(
                    side_state,
                    side_state.position.quantity,
                    "Target 3 hit (1:2.5 RR)",
                )
                if side_state.position is not None:
                    side_state.position.t3_done = True

    def check_trailing_stop(self, side_state: SideState) -> None:
        """BE stop acts as a trailing stop — exits when LTP drops to entry after Target 1 (1:1.5 RR)."""
        pos = side_state.position
        if pos is None or not pos.breakeven_armed:
            return
        option_ltp = self.broker.get_ltp(pos.option_symbol)
        if option_ltp <= pos.entry_price:
            self._exit_position(
                side_state,
                self.last_processed_candle_time or pos.entry_time,
                pos.quantity,
                (
                    f"Trailing stop hit: LTP {option_ltp:.2f} <= entry {pos.entry_price:.2f}; exited remaining"
                ),
                is_hard_sl=False,
            )

    def monitor_open_position(self, side_state: SideState, row: pd.Series) -> None:
        pos = side_state.position
        if pos is None:
            return

        option_low = float(row["low"])

        # Catastrophic stop (safety net only): fires when premium drops well below entry — 
        # this is a dead trigger in practice since trailing stop already exits at entry level.
        if option_low <= pos.option_stop_level:
            self._exit_position(
                side_state,
                self.last_processed_candle_time or pos.entry_time,
                pos.quantity,
                f"Catastrophic stop hit: option low {option_low:.2f} <= SL {pos.option_stop_level:.2f}",
                is_hard_sl=True,
            )
            return

        self.manage_targets(side_state, row)
        self.check_trailing_stop(side_state)



    def monitor_open_position(self, side_state: SideState, row: pd.Series) -> None:
        pos = side_state.position
        if pos is None:
            return

        option_low = float(row["low"])

        # Catastrophic stop (safety net only): fires when premium drops well below entry — 
        # this is a dead trigger in practice since trailing stop already exits at entry level.
        if option_low <= pos.option_stop_level:
            self._exit_position(
                side_state,
                self.last_processed_candle_time or pos.entry_time,
                pos.quantity,
                f"Catastrophic stop hit: option low {option_low:.2f} <= SL {pos.option_stop_level:.2f}",
                is_hard_sl=True,
            )
            return

        self.manage_targets(side_state, row)
        self.check_trailing_stop(side_state)

    def force_square_off_side(self, side_state: SideState, ts: datetime) -> None:
        side_state.pending_entry = None
        pos = side_state.position
        if pos is None:
            return
        self._exit_position(
            side_state,
            ts,
            pos.quantity,
            f"Forced square-off at {ts.time()} for {pos.option_symbol}",
            is_hard_sl=False,
        )

    def process_option_candle(
        self,
        side: str,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        """Feed a single option candle (CE or PE) through the engine.

        The caller is responsible for having already locked the ATM at
        09:20 via ``lock_atm_for_day``. Bars that arrive before 09:20 or
        after 15:15 are ignored (aside from the forced square-off).
        """
        ts = row["datetime"]
        self.last_processed_candle_time = ts
        self.on_day_transition_if_needed(ts)

        side_state = self._side_state(side)

        # Update last-bar indicators for status display.
        side_state.last_close = float(row["close"])
        rsi_val = row.get("rsi3")
        side_state.last_rsi = None if (rsi_val is None or pd.isna(rsi_val)) else float(rsi_val)
        for attr, col in (("last_ema13", "ema13"), ("last_ema20", "ema20"), ("last_ema50", "ema50")):
            v = row.get(col)
            setattr(side_state, attr, None if (v is None or pd.isna(v)) else float(v))

        # Force square-off at 15:15 applies even outside the entry window.
        if self.must_force_square_off(ts):
            self.force_square_off_side(side_state, ts)
            return

        if not self.in_trade_window(ts):
            return

        if side_state.option_symbol is None:
            # ATM not locked yet — cannot trade this side.
            return

        # After 15:00: cancel any pending entry and only monitor the open position.
        if not self.in_signal_window(ts):
            if side_state.pending_entry is not None:
                side_state.pending_entry = None
                self._record_alert(ts, "SESSION", f"{side} pending entry cancelled at signal cutoff (15:00)")
            self.monitor_open_position(side_state, row)
            return

        # Always try to fill and monitor first; new signals only if flat on this side.
        self.try_fill_pending_entry(side, side_state, ts, row)
        self.monitor_open_position(side_state, row)

        signal = self.generate_signal(side, side_state, row, prev_row)
        if signal in (Signal.BUY_CE, Signal.BUY_PE):
            self.place_pending_entry(side, side_state, ts, row)
        elif self.diagnose:
            self._diagnose_side_gate(side, side_state, ts, row)

        if self.verbose:
            self._print_candle_summary(side, side_state, ts, row)


    def process_candle(self, row: pd.Series, prev_row: Optional[pd.Series]) -> None:
        """Feed a single spot candle to both CE and PE sides (used by the dashboard simulation)."""
        self.process_option_candle("CE", row, prev_row)
        self.process_option_candle("PE", row, prev_row)

    def _print_candle_summary(self, side: str, side_state: SideState, ts: datetime, row: pd.Series) -> None:
        if not self._verbose_header_printed:
            print(f"  {'TIME':<5s} \u2502 {'SYMBOL':<22s} \u2502 {'OHLC':<42s} \u2502 {'PATTERN / RSI / TREND'}")
            print("  \u2500\u2500\u2500\u2500\u2500\u253c" + "\u2500" * 24 + "\u253c" + "\u2500" * 44 + "\u253c" + "\u2500" * 30)
            self._verbose_header_printed = True
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        rsi = row.get("rsi3")
        ema13, ema20, ema50 = row.get("ema13"), row.get("ema20"), row.get("ema50")
        vwap = row.get("vwap")

        total_range = h - l
        body = c - o
        body_pct = (abs(body) / total_range * 100) if total_range > 0 else 0.0

        if self.is_strong_green_candle(row, self.cfg.strong_body_threshold):
            candle_type = "⬆ STRONG_GREEN"
        elif self.is_hammer_candle(row):
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

        # Divergence state (compact)
        if side_state.divergence_ready:
            div_state = f"✅ DIV ARMED  p1={side_state.p1_price:.1f}(rsi {side_state.p1_rsi:.0f})  p2={side_state.p2_price:.1f}(rsi {side_state.p2_rsi:.0f})"
        elif side_state.p2_price is not None:
            div_state = f"⏳ P2 found but not divergent  p1={side_state.p1_price:.1f}/{side_state.p1_rsi:.0f}  p2={side_state.p2_price:.1f}/{side_state.p2_rsi:.0f}"
        elif side_state.p1_price is not None:
            div_state = f"⏳ Waiting for P2  (p1={side_state.p1_price:.1f}, rsi={side_state.p1_rsi:.0f})"
        elif side_state.pullback_active:
            div_state = f"⏳ Pullback active  low={side_state.pullback_low_price:.1f} rsi={side_state.pullback_low_rsi:.0f}"
        elif side_state.swing_low_active:
            div_state = f"⏳ Swing low = {side_state.swing_low:.1f}"
        else:
            div_state = "⏸  Waiting for RSI < 20"

        # Position state
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
            f"{candle_type:<14s} body {body_pct:>3.0f}% │ "
            f"RSI {rsi_str:>5s}  {trend}"
        )
        print(
            f"       │ {'':22s} │ "
            f"VWAP={vwap_str:<8s} SL_hits={self.state.sl_hits_today}/{self.risk.max_sl_per_day}{'':9s} │ "
            f"{div_state}"
        )
        if pos_info != "FLAT":
            print(f"       │ {'':22s} │ {'':42s} │ {pos_info}")
        print("  ─────┼" + "─" * 24 + "┼" + "─" * 44 + "┼" + "─" * 30)


# ===============================================================
#  OpenAlgo broker (live quotes + real order placement)
# ===============================================================


class OpenAlgoBroker(BrokerInterface):
    """BrokerInterface implementation backed by the OpenAlgo REST/WS client.

    - ``get_ltp``            -> ``client.quotes``
    - ``place_market_order`` -> ``client.placeorder(price_type='MARKET')``
    - ``place_stop_limit_order`` -> ``client.placeorder(price_type='SL')``
    """

    def __init__(
        self,
        api_key: str,
        host: str,
        ws_url: Optional[str] = None,
        strategy_tag: str = "HD_Strategy",
        product: str = "MIS",
        exchange_options: str = "NFO",
        dry_run: bool = True,
    ) -> None:
        try:
            from openalgo import api  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "openalgo package not installed. Install with `pip install openalgo`."
            ) from exc

        kwargs = {"api_key": api_key, "host": host}
        if ws_url:
            kwargs["ws_url"] = ws_url
        self.client = api(**kwargs)
        self.strategy_tag = strategy_tag
        self.product = product
        self.exchange_options = exchange_options
        self.dry_run = dry_run
        logger.info(
            "OpenAlgoBroker initialized host=%s ws_url=%s product=%s dry_run=%s",
            host, ws_url, product, dry_run,
        )

    def get_ltp(self, symbol: str) -> float:
        exchange = self._infer_exchange(symbol)
        try:
            resp = self.client.quotes(symbol=symbol, exchange=exchange)
        except Exception as exc:
            logger.warning("quotes(%s) error: %s", symbol, exc)
            return 0.0

        if isinstance(resp, dict) and resp.get("status") == "success":
            data = resp.get("data") or {}
            ltp = data.get("ltp") or resp.get("ltp")
            if ltp is not None:
                return round(float(ltp), 2)
        logger.warning("quotes(%s) unexpected response: %s", symbol, resp)
        return 0.0

    def place_stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        trigger_price: float,
        limit_price: float,
    ) -> str:
        exchange = self._infer_exchange(symbol)
        if self.dry_run:
            oid = f"DRY-SL-L-{symbol}-{side.value}-{quantity}"
            logger.info(
                "[DRY_RUN] place_stop_limit_order %s %s qty=%s trigger=%.2f limit=%.2f -> %s",
                symbol, side.value, quantity, trigger_price, limit_price, oid,
            )
            return oid
        try:
            resp = self.client.placeorder(
                strategy=self.strategy_tag,
                symbol=symbol,
                action=side.value,
                exchange=exchange,
                price_type="SL",
                product=self.product,
                quantity=int(quantity),
                price=round(float(limit_price), 2),
                trigger_price=round(float(trigger_price), 2),
            )
        except Exception as exc:
            logger.error("placeorder SL error for %s: %s", symbol, exc)
            raise
        return self._extract_order_id(resp)

    def place_market_order(self, symbol: str, side: OrderSide, quantity: int) -> str:
        exchange = self._infer_exchange(symbol)
        if self.dry_run:
            oid = f"DRY-MKT-{symbol}-{side.value}-{quantity}"
            logger.info(
                "[DRY_RUN] place_market_order %s %s qty=%s -> %s",
                symbol, side.value, quantity, oid,
            )
            return oid
        try:
            resp = self.client.placeorder(
                strategy=self.strategy_tag,
                symbol=symbol,
                action=side.value,
                exchange=exchange,
                price_type="MARKET",
                product=self.product,
                quantity=int(quantity),
            )
        except Exception as exc:
            logger.error("placeorder MARKET error for %s: %s", symbol, exc)
            raise
        return self._extract_order_id(resp)

    # ── History helper used by the live runner ──────────────────────

    def fetch_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        df = self.client.history(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )
        if isinstance(df, dict):
            raise RuntimeError(f"history returned error for {symbol}: {df}")
        if df is None or df.empty:
            raise RuntimeError(f"No history data for {symbol}")
        return df

    # ── Internal helpers ─────────────────────────────────────────────

    def _infer_exchange(self, symbol: str) -> str:
        """Options symbols contain a strike + CE/PE suffix; everything else is index/spot."""
        if symbol.endswith("CE") or symbol.endswith("PE"):
            return self.exchange_options
        return "NSE_INDEX"

    @staticmethod
    def _extract_order_id(resp) -> str:
        if isinstance(resp, dict):
            if resp.get("status") == "success":
                return str(
                    resp.get("orderid")
                    or (resp.get("data") or {}).get("orderid")
                    or ""
                )
            raise RuntimeError(f"Order rejected: {resp}")
        return str(resp)


# ===============================================================
#  Live feed runner (poll-based on candle boundary)
# ===============================================================


def _normalize_history_df(df: pd.DataFrame) -> pd.DataFrame:
    """Convert an OpenAlgo history DataFrame into the canonical columns."""
    out = df.copy()
    if isinstance(out.index, pd.DatetimeIndex):
        index_name = out.index.name or "datetime"
        out = out.reset_index().rename(columns={index_name: "datetime"})
    # Standardize column names to lowercase.
    out.columns = [str(c).lower() for c in out.columns]
    if "datetime" not in out.columns:
        for candidate in ("timestamp", "time", "date"):
            if candidate in out.columns:
                out = out.rename(columns={candidate: "datetime"})
                break
    if "datetime" not in out.columns:
        raise RuntimeError(f"history frame missing datetime column: {list(out.columns)}")

    # Strip tz so downstream datetime.combine comparisons work.
    out["datetime"] = pd.to_datetime(out["datetime"]).dt.tz_localize(None)
    required = {"datetime", "open", "high", "low", "close", "volume"}
    missing = required - set(out.columns)
    if missing:
        # volume may be absent for indices — fill with 0 so VWAP path stays defined.
        if missing == {"volume"}:
            out["volume"] = 0.0
        else:
            raise RuntimeError(f"history frame missing columns: {sorted(missing)}")

    out = out[["datetime", "open", "high", "low", "close", "volume"]]
    out[["open", "high", "low", "close", "volume"]] = out[
        ["open", "high", "low", "close", "volume"]
    ].apply(pd.to_numeric, errors="coerce")
    return out.sort_values("datetime").reset_index(drop=True)


class LiveFeedRunner:
    """Polls OpenAlgo history at the candle boundary and drives the engine.

    Flow per trading day:
      1. Anywhere from 09:20 onward: fetch the current spot price -> lock ATM
         and derive CE + PE symbols.
      2. On every candle boundary: fetch CE + PE history (only the current
         day's session is fed to the engine) and route each new bar to the
         corresponding side.
    """

    def __init__(
        self,
        engine: HDStrategyEngine,
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
        # Per-side last processed bar time so we never replay a bar.
        self._last_bar_time: dict[str, Optional[datetime]] = {"CE": None, "PE": None}

    def stop(self) -> None:
        self._stop.set()

    # ── ATM lock helpers ────────────────────────────────────────────

    def _try_lock_atm(self, now: datetime) -> None:
        """If the session has crossed the ATM lock time and we haven't locked
        yet, fetch the current spot LTP and lock the CE + PE symbols.
        """
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

    # ── History fetch + normalize per option ────────────────────────

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
        # Compute indicators on full lookback so EMA/RSI are warmed up.
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
                    side, self._last_bar_time[side], row["open"], row["high"], row["low"], row["close"],
                )

    def _poll_once(self) -> None:
        now = datetime.now()
        self._try_lock_atm(now)
        if not self.engine.state.atm_locked:
            return

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
        """Wait for *seconds*, printing a countdown timer. Returns True if stopped."""
        import sys
        deadline = datetime.now() + timedelta(seconds=seconds)
        while not self._stop.is_set():
            remaining = (deadline - datetime.now()).total_seconds()
            if remaining <= 0:
                break
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

    def run_forever(self) -> None:
        logger.info(
            "LiveFeedRunner starting (spot=%s exchange=%s tf=%sm)",
            self.cfg.spot_symbol, self.cfg.exchange_spot, self.cfg.timeframe_minutes,
        )
        try:
            self._poll_once()
            self._print_cycle_summary()
        except Exception as exc:
            logger.warning("initial poll failed: %s", exc)

        while not self._stop.is_set():
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

    def _format_side_status(self, side: str) -> str:
        side_state = self.engine._side_state(side)
        symbol = side_state.option_symbol or "NOT LOCKED"
        lines = [f"│ {side}: {symbol}"]

        # Current indicators
        rsi_str = f"{side_state.last_rsi:.1f}" if side_state.last_rsi is not None else "--"
        e13 = f"{side_state.last_ema13:.1f}" if side_state.last_ema13 is not None else "--"
        e20 = f"{side_state.last_ema20:.1f}" if side_state.last_ema20 is not None else "--"
        e50 = f"{side_state.last_ema50:.1f}" if side_state.last_ema50 is not None else "--"
        ltp = f"{side_state.last_close:.1f}" if side_state.last_close is not None else "--"

        if (side_state.last_ema13 is not None and side_state.last_ema20 is not None
                and side_state.last_ema50 is not None):
            if side_state.last_ema13 > side_state.last_ema20 or side_state.last_ema20 > side_state.last_ema50:
                trend = "📈 BULL"
            else:
                trend = "📉 BEAR"
        else:
            trend = "--"

        lines.append(f"│     LTP={ltp}  RSI={rsi_str}  EMA13={e13}  EMA20={e20}  EMA50={e50}  {trend}")

        # Divergence state with clear explanation
        if side_state.divergence_ready:
            lines.append(
                f"│     Setup: ✅ DIVERGENCE ARMED — waiting for trigger candle (strong green / hammer)"
            )
            lines.append(
                f"│       P1: price low={side_state.p1_price:.1f}, RSI at low={side_state.p1_rsi:.1f}"
            )
            lines.append(
                f"│       P2: price low={side_state.p2_price:.1f}, RSI at low={side_state.p2_rsi:.1f}"
                f"  (price↑ RSI↓ = bullish divergence)"
            )
        elif side_state.p2_price is not None:
            lines.append(
                f"│     Setup: ⏳ P2 found but NO divergence (need P2 price > P1 AND P2 RSI < P1)"
            )
            lines.append(
                f"│       P1: low={side_state.p1_price:.1f} rsi={side_state.p1_rsi:.1f}  |"
                f"  P2: low={side_state.p2_price:.1f} rsi={side_state.p2_rsi:.1f}"
            )
        elif side_state.p1_price is not None:
            lines.append(
                f"│     Setup: ⏳ Got P1 — waiting for RSI to dip < 20 again to form P2"
            )
            lines.append(
                f"│       P1: price low={side_state.p1_price:.1f}, RSI at low={side_state.p1_rsi:.1f}"
            )
        elif side_state.pullback_active:
            lines.append(
                f"│     Setup: ⏳ RSI below 20 — recording pullback"
                f"  (low so far={side_state.pullback_low_price:.1f}, rsi={side_state.pullback_low_rsi:.1f})"
            )
        elif side_state.swing_low_active:
            lines.append(f"│     Setup: ⏳ Swing low active = {side_state.swing_low:.1f}")
        else:
            lines.append(f"│     Setup: ⏸  No setup — waiting for RSI to cross below 20")

        # Position / pending state
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

        print(f"\n┌─── {now.strftime('%H:%M:%S')} ─── HD Strategy Status {'─' * 30}┐")
        print(f"│ Strikes: {state.ce_symbol} / {state.pe_symbol}")
        print(f"│ SL hits: {state.sl_hits_today}/{self.engine.risk.max_sl_per_day}"
              f"   Entries today: {self.engine.total_entries}"
              f"   PnL: {self.engine.realized_pnl:+.1f}")
        print(f"├{'─' * 62}┤")
        print(ce_status)
        print(pe_status)
        print(f"└{'─' * 62}┘")


# ===============================================================
#  Historical replay (backtest against OpenAlgo history, no CSV needed)
# ===============================================================


class HistoricalReplayBroker(BrokerInterface):
    """Backtest broker driven by pre-loaded per-symbol OHLCV bars.

    The runner calls ``set_current_bar(symbol, row)`` before every engine
    step so that ``get_ltp(symbol)`` returns the current bar's close for
    that specific symbol (spot or option).
    """

    def __init__(self) -> None:
        self._bars: dict[str, pd.Series] = {}

    def set_current_bar(self, symbol: str, row: pd.Series) -> None:
        self._bars[symbol] = row

    def get_ltp(self, symbol: str) -> float:
        row = self._bars.get(symbol)
        if row is None:
            return 0.0
        return float(row["close"])

    def place_market_order(self, symbol: str, side: OrderSide, quantity: int) -> str:
        return f"BT-MKT-{symbol}-{side.value}-{quantity}"

    def place_stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        trigger_price: float,
        limit_price: float,
    ) -> str:
        return f"BT-SL-L-{symbol}-{side.value}-{quantity}"


def _fetch_history_df(
    broker: OpenAlgoBroker,
    symbol: str,
    exchange: str,
    interval: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    raw = broker.fetch_history(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
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
    """Compute indicators on all available bars, then return only the target day's session."""
    if df.empty:
        return df
    full = add_indicators(df.reset_index(drop=True), cfg)
    session_start = datetime.combine(day, cfg.market_open)
    session_end = datetime.combine(day, cfg.market_close)
    sliced = full[(full["datetime"] >= session_start) & (full["datetime"] < session_end)]
    return sliced.reset_index(drop=True)


def _find_atm_lock_price(spot_day: pd.DataFrame, cfg: StrategyConfig) -> Optional[float]:
    """Return the OPEN of the 09:20 candle for the given day."""
    target = cfg.atm_lock_time
    for _, row in spot_day.iterrows():
        if row["datetime"].time() == target:
            return float(row["open"])
        if row["datetime"].time() > target:
            # First bar at/after the lock time — use its open as a fallback.
            return float(row["open"])
    return None


def run_historical_replay(
    cfg: StrategyConfig,
    risk: RiskConfig,
    start_date: str,
    end_date: str,
    diagnose: bool = False,
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
    engine = HDStrategyEngine(cfg, risk, broker)
    engine.diagnose = diagnose

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

        # Reset day + lock ATM (this also derives CE + PE symbols).
        engine.reset_for_new_day(day)
        lock_ts = datetime.combine(day, cfg.atm_lock_time)
        engine.lock_atm_for_day(lock_ts, atm_price)
        ce_sym = engine.state.ce_symbol
        pe_sym = engine.state.pe_symbol
        assert ce_sym and pe_sym

        # Pull option history with extra warmup days so EMA/RSI are primed.
        warmup_start = (day - timedelta(days=5)).strftime("%Y-%m-%d")
        day_str = day.strftime("%Y-%m-%d")
        try:
            ce_raw = _fetch_history_df(
                history_broker, ce_sym, cfg.exchange_options, interval, warmup_start, day_str,
            )
            pe_raw = _fetch_history_df(
                history_broker, pe_sym, cfg.exchange_options, interval, warmup_start, day_str,
            )
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

        # Merge the two streams and step through them in chronological order.
        ce_events = [("CE", row) for _, row in ce_day.iterrows()]
        pe_events = [("PE", row) for _, row in pe_day.iterrows()]
        # Also stream spot bars only so broker can serve spot LTP if ever asked.
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

        # End-of-day forced square-off (using the last bar's timestamp).
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

    # --- Per-event trade log ---------------------------------------------------
    print("\n─── Trade Log ─────────────────────────────────────────────")
    for i, evt in enumerate(entries):
        ts = evt.timestamp.strftime("%H:%M:%S") if hasattr(evt.timestamp, "strftime") else str(evt.timestamp)
        sym = evt.message.split()[0] if evt.message else "?"
        print(f"  [{ts}] ENTRY #{i+1}  {sym:<45s}  pnl={evt.message}")
    for i, evt in enumerate(exits):
        ts = evt.timestamp.strftime("%H:%M:%S") if hasattr(evt.timestamp, "strftime") else str(evt.timestamp)
        msg = evt.message or ""
        # Determine exit type + price from the message
        lower = msg.lower()
        if "breakeven" in lower:
            exit_type = "BE STOP"
            # Extract LTP and entry prices (re is already imported at top level)
            match = re.search(r'option ltp ([\d.]+).*entry ([\d.]+)', msg, re.IGNORECASE)
            if match:
                print(f"  [{ts}] EXIT #{i+1}   {exit_type:<45s}  LTP={match.group(1)}  entry={match.group(2)}")
            else:
                print(f"  [{ts}] EXIT #{i+1}   {exit_type:<45s}  pnl={msg}")
        elif "forced square-off" in lower or "force" in lower:
            exit_type = "FORCED SQ OFF"
            match = re.search(r'Forced square-off at ([\d.:]+)', msg, re.IGNORECASE)
            if match:
                print(f"  [{ts}] EXIT #{i+1}   {exit_type:<45s}  time={match.group(1)}")
            else:
                print(f"  [{ts}] EXIT #{i+1}   {exit_type:<45s}  pnl={msg}")
        elif "stop hit" in lower or "hard sl" in lower:
            exit_type = "HARD SL"
            match = re.search(r'option low ([\d.]+).*SL ([\d.]+)', msg, re.IGNORECASE)
            if match:
                print(f"  [{ts}] EXIT #{i+1}   {exit_type:<45s}  LTP={match.group(1)}  SL={match.group(2)}")
            else:
                print(f"  [{ts}] EXIT #{i+1}   {exit_type:<45s}  pnl={msg}")
        else:
            sym = msg.split()[0] if msg else "?"
            print(f"  [{ts}] EXIT #{i+1}   {sym:<45s}  pnl={msg}")

    # --- Summary counts -------------------------------------------------------
    print("\n─── Summary ───────────────────────────────────────────────")
    print(f"Total entries     : {len(entries)}")
    print(f"Total exits       : {len(exits)}")
    print("=" * 72)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HD Strategy runner")
    parser.add_argument(
        "--mode",
        choices=("backtest", "smoke", "paper", "live"),
        default="smoke",
        help=(
            "backtest: OpenAlgo history replay | smoke: 1-shot OpenAlgo history+LTP dump | "
            "paper: live feed, no real orders | live: live feed + real orders"
        ),
    )
    parser.add_argument("--start", type=str, default=None,
                        help="Backtest start date YYYY-MM-DD (required for backtest mode)")
    parser.add_argument("--end", type=str, default=None,
                        help="Backtest end date YYYY-MM-DD (defaults to today when --start is given)")
    parser.add_argument("--symbol", type=str, default=None,
                        help="Override spot_symbol (default NIFTY)")
    parser.add_argument("--exchange", type=str, default=None,
                        help="Override exchange_spot (default NSE_INDEX)")
    parser.add_argument("--timeframe", type=int, default=None,
                        help="Override timeframe_minutes (default 3)")
    parser.add_argument("--max-risk", type=float, default=None,
                        help="Override max_option_risk_points (default 25.0)")
    parser.add_argument("--max-sl", type=int, default=None,
                        help="Override max_sl_per_day (default 3)")
    parser.add_argument("--body-threshold", type=float, default=None,
                        help="Override strong_body_threshold (default 0.85 = body >= 85%% of range)")
    parser.add_argument("--diagnose", action="store_true",
                        help="Print a per-candle DIAG line explaining why each side didn't generate a signal")
    parser.add_argument("--verbose", action="store_true",
                        help="Print a full candle summary (OHLC, candle type, EMA, RSI, VWAP, divergence state) for every bar")
    parser.add_argument("--log-level", type=str, default="INFO")
    return parser.parse_args(argv)


def _load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    script_dir = Path(__file__).resolve().parent
    # Check both the script directory and one level up (repo root).
    env_path = script_dir / ".env"
    if not env_path.exists():
        env_path = script_dir.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _run_live(
    cfg: StrategyConfig,
    risk: RiskConfig,
    dry_run: bool,
    diagnose: bool = False,
    verbose: bool = False,
) -> None:
    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        raise SystemExit("OPENALGO_API_KEY not set (check .env)")
    host = (
        os.getenv("OPENALGO_HOST")
        or os.getenv("OPENALGO_URL")
        or "http://127.0.0.1:5002"
    )
    ws_url = os.getenv("OPENALGO_WS_URL") or (
        f"ws://{os.getenv('WEBSOCKET_HOST', '127.0.0.1')}:"
        f"{os.getenv('WEBSOCKET_PORT', '8765')}"
    )
    product = os.getenv("PRODUCT", "MIS")
    broker = OpenAlgoBroker(
        api_key=api_key,
        host=host,
        ws_url=ws_url,
        strategy_tag=os.getenv("STRATEGY_NAME", "HD_Strategy"),
        product=product,
        exchange_options=cfg.exchange_options,
        dry_run=dry_run,
    )
    engine = HDStrategyEngine(cfg, risk, broker)
    engine.diagnose = diagnose
    engine.verbose = verbose
    runner = LiveFeedRunner(engine, broker, cfg)

    try:
        runner.run_forever()
    except KeyboardInterrupt:
        logger.info("interrupted; stopping runner")
        runner.stop()


def _run_smoke_test(cfg: StrategyConfig) -> None:
    """One-shot: fetch history via OpenAlgo, print the last few 3-min bars."""
    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        raise SystemExit("OPENALGO_API_KEY not set (check .env)")
    host = os.getenv("OPENALGO_HOST") or os.getenv("OPENALGO_URL") or "http://127.0.0.1:5002"
    broker = OpenAlgoBroker(api_key=api_key, host=host, dry_run=True)

    today = datetime.now().date()
    start = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    interval = f"{cfg.timeframe_minutes}m"
    logger.info(
        "smoke: fetching %s %s %s [%s -> %s]",
        cfg.spot_symbol, cfg.exchange_spot, interval, start, end,
    )
    raw = broker.fetch_history(
        symbol=cfg.spot_symbol,
        exchange=cfg.exchange_spot,
        interval=interval,
        start_date=start,
        end_date=end,
    )
    prepared = add_indicators(_normalize_history_df(raw), cfg)
    print(prepared.tail(5).to_string(index=False))
    ltp = broker.get_ltp(cfg.spot_symbol)
    print(f"\nLive LTP for {cfg.spot_symbol}: {ltp}")


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)
    _setup_logging(args.log_level)
    _load_dotenv_if_present()

    cfg = StrategyConfig()
    if args.symbol:
        cfg.spot_symbol = args.symbol
        cfg.option_index_symbol = args.symbol
    if args.exchange:
        cfg.exchange_spot = args.exchange
    if args.timeframe:
        cfg.timeframe_minutes = args.timeframe
    if args.max_risk is not None:
        cfg.max_option_risk_points = args.max_risk
    if args.body_threshold is not None:
        cfg.strong_body_threshold = args.body_threshold

    risk = RiskConfig()
    if args.max_sl is not None:
        risk.max_sl_per_day = args.max_sl

    if args.mode == "backtest":
        if not args.start:
            raise SystemExit(
                "backtest mode requires --start YYYY-MM-DD (CSV backtest has been removed)"
            )
        end_date = args.end or datetime.now().date().strftime("%Y-%m-%d")
        run_historical_replay(cfg, risk, args.start, end_date, diagnose=args.diagnose)
        return

    if args.mode == "smoke":
        _run_smoke_test(cfg)
        return

    dry_run = args.mode == "paper"
    _run_live(
        cfg,
        risk,
        dry_run=dry_run,
        diagnose=args.diagnose,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
