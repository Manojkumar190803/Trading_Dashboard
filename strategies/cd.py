from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.indicators import is_hammer_candle, is_strong_green_candle
from core.models import BaseSideState, Signal, StrategyConfig
from strategies.base import SignalProvider


@dataclass
class CDSideState(BaseSideState):
    """CD strategy: RSI classic-divergence + dual-candle confirmation."""

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
    # Dual-candle confirmation state
    confirm_count: int = 0  # 0=not confirming, 1=first candle OK, 2=armed
    confirm_lows: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.confirm_lows is None:
            self.confirm_lows = []


@dataclass
class CDConfig:
    """CD-strategy-specific parameters."""

    strong_body_threshold: float = 0.85


class CDSignalProvider(SignalProvider):
    """Classic divergence (Price LL + RSI HL) + dual-candle confirmation."""

    def __init__(self, cd_cfg: Optional[CDConfig] = None) -> None:
        self.cd_cfg = cd_cfg or CDConfig()

    def create_side_state(self) -> CDSideState:
        return CDSideState()

    def update_state(
        self,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        assert isinstance(side_state, CDSideState)
        was_ready = side_state.divergence_ready
        self._update_divergence(side_state, row, prev_row)
        # Only check confirmation on candles AFTER divergence was armed
        if was_ready:
            self._update_confirmation(side_state, row)

    def generate_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Signal:
        assert isinstance(side_state, CDSideState)

        if side_state.position is not None or side_state.pending_entry is not None:
            return Signal.NONE

        # CD fires when dual-candle confirmation is complete (confirm_count == 2)
        if side_state.confirm_count == 2:
            return Signal.BUY_CE if side == "CE" else Signal.BUY_PE

        return Signal.NONE

    def compute_risk_points(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> Optional[float]:
        assert isinstance(side_state, CDSideState)
        stop = self._raw_stop_level(side_state, row)
        if stop is None:
            return None
        entry = float(row["high"] + 1.0)
        return entry - stop

    def compute_entry_lots(self, row: pd.Series, cfg: StrategyConfig) -> int:
        premium = float(row["close"])
        vwap = float(row["vwap"])
        if pd.isna(vwap):
            return cfg.half_size_lots
        return cfg.full_size_lots if premium > vwap else cfg.half_size_lots

    def compute_stop_level(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> float:
        assert isinstance(side_state, CDSideState)
        stop = self._raw_stop_level(side_state, row)
        if stop is None:
            return float(row["low"] - 1.0)
        return stop

    def reset_after_entry(self, side_state: BaseSideState) -> None:
        assert isinstance(side_state, CDSideState)
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
        side_state.confirm_count = 0
        side_state.confirm_lows = []

    def format_setup_status(self, side_state: BaseSideState) -> str:
        assert isinstance(side_state, CDSideState)
        if side_state.confirm_count == 2:
            return (
                f"✅ CD CONFIRMED  "
                f"p1={side_state.p1_price:.1f}(rsi {side_state.p1_rsi:.0f})  "
                f"p2={side_state.p2_price:.1f}(rsi {side_state.p2_rsi:.0f})"
            )
        if side_state.confirm_count == 1:
            return (
                f"⏳ 1/2 confirm candles OK  "
                f"p1={side_state.p1_price:.1f}/{side_state.p1_rsi:.0f}  "
                f"p2={side_state.p2_price:.1f}/{side_state.p2_rsi:.0f}"
            )
        if side_state.divergence_ready:
            return (
                f"⏳ CD DIVERGENCE — awaiting confirmation  "
                f"p1={side_state.p1_price:.1f}(rsi {side_state.p1_rsi:.0f})  "
                f"p2={side_state.p2_price:.1f}(rsi {side_state.p2_rsi:.0f})"
            )
        if side_state.p2_price is not None:
            return (
                f"⏳ P2 found but NO classic divergence  "
                f"p1={side_state.p1_price:.1f}/{side_state.p1_rsi:.0f}  "
                f"p2={side_state.p2_price:.1f}/{side_state.p2_rsi:.0f}"
            )
        if side_state.p1_price is not None:
            return (
                f"⏳ Waiting for P2  "
                f"(p1={side_state.p1_price:.1f}, rsi={side_state.p1_rsi:.0f})"
            )
        if side_state.pullback_active:
            return (
                f"⏳ Pullback active  "
                f"low={side_state.pullback_low_price:.1f} rsi={side_state.pullback_low_rsi:.0f}"
            )
        if side_state.swing_low_active:
            return f"⏳ Swing low = {side_state.swing_low:.1f}"
        return "⏸  Waiting for RSI < 20"

    def diagnose_no_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Optional[str]:
        assert isinstance(side_state, CDSideState)

        if side_state.p1_price is None:
            state = "swing_low_active" if side_state.swing_low_active else "waiting_for_rsi<20"
            pull = "pullback_active" if side_state.pullback_active else "no_pullback"
            return f"NO_P1 ({state}, {pull})"
        if side_state.p2_price is None:
            return (
                f"NO_P2 (have p1: price={side_state.p1_price:.2f} rsi={side_state.p1_rsi:.1f}; "
                f"waiting for second pullback cross-above-20)"
            )
        if not side_state.divergence_ready:
            return (
                f"DIV_NOT_ARMED (p1={side_state.p1_price:.2f}/{side_state.p1_rsi:.1f}, "
                f"p2={side_state.p2_price:.2f}/{side_state.p2_rsi:.1f}; "
                f"need p2_price<p1_price AND p2_rsi>p1_rsi for classic divergence)"
            )
        if side_state.confirm_count < 2:
            return (
                f"CONFIRM_PENDING ({side_state.confirm_count}/2 candles confirmed; "
                f"need 2 consecutive strong-green or hammer candles)"
            )
        return "SIGNAL_OK (unexpected — signal should have fired)"

    # ── Internals ─────────────────────────────────────────────────────

    def _raw_stop_level(self, ss: CDSideState, row: pd.Series) -> Optional[float]:
        """Lowest low of P1, P2, and confirmation candles - 1.0."""
        lows = []
        if ss.p1_price is not None:
            lows.append(ss.p1_price)
        if ss.p2_price is not None:
            lows.append(ss.p2_price)
        lows.extend(ss.confirm_lows)
        if not lows:
            return None
        return min(lows) - 1.0

    def _is_bullish_candle(self, row: pd.Series) -> bool:
        """Strong green or hammer — and must be green (close > open)."""
        if row["close"] <= row["open"]:
            return False
        return (
            is_strong_green_candle(row, self.cd_cfg.strong_body_threshold)
            or is_hammer_candle(row)
        )

    def _update_confirmation(self, ss: CDSideState, row: pd.Series) -> None:
        """Track dual-candle confirmation after divergence is armed."""
        if not ss.divergence_ready:
            ss.confirm_count = 0
            ss.confirm_lows = []
            return

        # Already fully confirmed — don't overwrite until reset
        if ss.confirm_count == 2:
            return

        if self._is_bullish_candle(row):
            ss.confirm_count += 1
            ss.confirm_lows.append(float(row["low"]))
        else:
            # Invalidation: reset confirmation and full divergence state
            ss.confirm_count = 0
            ss.confirm_lows = []
            ss.divergence_ready = False
            ss.p1_price = None
            ss.p1_rsi = None
            ss.p2_price = None
            ss.p2_rsi = None

    def _update_divergence(
        self,
        ss: CDSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        """Same swing-low state machine as HD, but classic divergence condition."""
        rsi = row["rsi3"]
        if pd.isna(rsi):
            return
        prev_rsi = prev_row["rsi3"] if prev_row is not None else None
        prev_rsi_valid = prev_rsi is not None and not pd.isna(prev_rsi)

        crossed_below_20 = prev_rsi_valid and prev_rsi >= 20 and rsi < 20
        crossed_above_20 = prev_rsi_valid and prev_rsi <= 20 and rsi > 20

        if crossed_below_20:
            ss.swing_low_active = True
            ss.swing_low = row["low"]
            ss.pullback_active = True
            ss.pullback_low_price = row["low"]
            ss.pullback_low_rsi = rsi
            # New sub-20 excursion resets any in-progress confirmation
            if not ss.divergence_ready:
                ss.confirm_count = 0
                ss.confirm_lows = []

        if ss.swing_low_active:
            if ss.swing_low is None:
                ss.swing_low = row["low"]
            else:
                ss.swing_low = min(ss.swing_low, row["low"])

        if ss.pullback_active and rsi < 20:
            if ss.pullback_low_price is None:
                ss.pullback_low_price = row["low"]
            else:
                ss.pullback_low_price = min(ss.pullback_low_price, row["low"])
            if ss.pullback_low_rsi is None:
                ss.pullback_low_rsi = rsi
            else:
                ss.pullback_low_rsi = min(ss.pullback_low_rsi, rsi)

        if ss.pullback_active and crossed_above_20:
            finished_price = ss.pullback_low_price
            finished_rsi = ss.pullback_low_rsi
            if finished_price is not None and finished_rsi is not None:
                if ss.p1_price is None or ss.p1_rsi is None:
                    ss.p1_price = finished_price
                    ss.p1_rsi = finished_rsi
                    ss.p2_price = None
                    ss.p2_rsi = None
                    ss.divergence_ready = False
                else:
                    ss.p2_price = finished_price
                    ss.p2_rsi = finished_rsi
                    # Classic divergence: Price LL + RSI HL
                    ss.divergence_ready = (
                        ss.p2_price < ss.p1_price and ss.p2_rsi > ss.p1_rsi
                    )
                    if not ss.divergence_ready:
                        ss.confirm_count = 0
                        ss.confirm_lows = []
            ss.pullback_active = False
            ss.pullback_low_price = None
            ss.pullback_low_rsi = None
