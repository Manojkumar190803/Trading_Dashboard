from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Optional


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
    trailing_step_rr: float = 0.5
    expiry_policy: str = "weekly"
    weekly_expiry_weekday: int = 1  # Monday=0 ... Tuesday=1

    # ── Timing (all in IST) ──────────────────────────────────────────
    timeframe_minutes: int = 3
    market_open: time = time(9, 20)
    market_close: time = time(15, 15)
    force_square_off: time = time(15, 15)
    signal_cutoff: time = time(15, 0)
    atm_lock_time: time = time(9, 20)
    entry_start: time = time(9, 20)
    entry_cutoff: time = time(14, 45)

    # ── Indicators (applied to the option premium chart) ─────────────
    ema_fast: int = 13
    ema_mid: int = 20
    ema_slow: int = 50
    ema_period: int = 21
    rsi_length: int = 3

    # ── Risk (all on option premium points) ──────────────────────────
    max_option_risk_points: float = 20.0
    min_vwap_room_rr: float = 1.5
    pending_entry_expiry_candles: int = 3
    entry_buffer_points: float = 0.0
    stop_buffer_points: float = 1.0
    entry_limit_buffer_points: float = 0.5
    option_tick_size: float = 0.05
    max_trades_per_day: int = 3

    # ── Targets (RR multiples) ───────────────────────────────────────
    t1_rr: float = 1.5
    t2_rr: float = 2.0


@dataclass
class RiskConfig:
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
    protective_stop_order_id: Optional[str] = None
    t1_done: bool = False
    t2_done: bool = False
    breakeven_armed: bool = False
    # Step-trailing: highest RR milestone reached (in 0.5 steps).
    highest_rr_step: float = 0.0
    trailing_sl_level: Optional[float] = None
    current_price: Optional[float] = None
    progress_status: str = "Monitoring position"
    next_target_rr: Optional[float] = None


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
    order_id: Optional[str] = None


@dataclass
class StrategyAlert:
    timestamp: datetime
    category: str
    message: str


@dataclass
class BaseSideState:
    """Generic per-side state. Strategies extend this with their own fields."""

    option_symbol: Optional[str] = None
    position: Optional[Position] = None
    pending_entry: Optional[PendingEntry] = None
    order_submission_uncertain: bool = False
    last_close: Optional[float] = None
    last_ema21: Optional[float] = None
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
    ce: BaseSideState = field(default_factory=BaseSideState)
    pe: BaseSideState = field(default_factory=BaseSideState)
