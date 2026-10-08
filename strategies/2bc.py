"""2BC (Two Body Candle) Breakout Strategy — momentum-driven breakout detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

from core.indicators import is_strong_green_candle
from core.models import BaseSideState, Signal, StrategyConfig
from strategies.base import SignalProvider


@dataclass
class TwoBodyCandleSideState(BaseSideState):
    """2BC strategy state for one option side."""

    consolidation_active: bool = False
    chop_value: Optional[float] = None
    adx_value: Optional[float] = None
    consolidation_candle_count: int = 0
    first_candle_time: Optional[datetime] = None
    first_candle_close: Optional[float] = None
    first_candle_rsi: Optional[float] = None
    second_candle_rsi: Optional[float] = None
    breakout_ready: bool = False


@dataclass
class TwoBodyCandleConfig:
    """2BC strategy-specific parameters."""

    chop_threshold: float = 61.8  # Consolidation indicator
    adx_threshold: float = 25.0  # Low trend indicator
    consolidation_candles: int = 3  # Candles to check Gate 1
    body_threshold: float = 0.85  # Strong green candle body %
    entry_limit_buffer: float = 0.5
    exit_limit_buffer: float = 0.5
    rsi_threshold_low: float = 80.0  # Phase 1: Normal momentum
    rsi_threshold_high: float = 80.0  # Phase 2: Extreme momentum
    max_initial_risk: float = 20.0  # Risk cap in points


class TwoBodyCandleSignalProvider(SignalProvider):
    """2BC breakout strategy with multi-gate entry and trailing SL."""

    def __init__(self, config: Optional[TwoBodyCandleConfig] = None) -> None:
        self.config = config or TwoBodyCandleConfig()

    def create_side_state(self) -> TwoBodyCandleSideState:
        return TwoBodyCandleSideState()

    def update_state(
        self,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        """Update 2BC state based on current candle."""
        assert isinstance(side_state, TwoBodyCandleSideState)
        
        # Extract technical indicators if available
        chop = row.get("chop", None)
        adx = row.get("adx", None)
        rsi3 = row.get("rsi_3", row.get("rsi", None))
        
        side_state.chop_value = chop
        side_state.adx_value = adx
        
        # Gate 1: Multi-factor consolidation filter
        if chop is not None and adx is not None:
            if chop > self.config.chop_threshold and adx < self.config.adx_threshold:
                side_state.consolidation_candle_count += 1
            else:
                side_state.consolidation_candle_count = 0
            
            if side_state.consolidation_candle_count >= self.config.consolidation_candles:
                side_state.consolidation_active = True
        
        # Gate 2 & 3: Two-candle breakout with RSI surge
        if prev_row is not None and side_state.consolidation_active:
            c1_is_strong = is_strong_green_candle(prev_row, self.config.body_threshold)
            c2_is_strong = is_strong_green_candle(row, self.config.body_threshold)
            c2_higher_high = row.get("close", 0) > prev_row.get("high", 0)
            
            c1_rsi = prev_row.get("rsi_3", prev_row.get("rsi", None))
            c2_rsi = rsi3
            
            if c1_is_strong and c2_is_strong and c2_higher_high:
                if c1_rsi is not None and c2_rsi is not None:
                    if c1_rsi < self.config.rsi_threshold_low and c2_rsi > self.config.rsi_threshold_high:
                        side_state.first_candle_time = prev_row.get("time", None)
                        side_state.first_candle_close = prev_row.get("close", None)
                        side_state.first_candle_rsi = c1_rsi
                        side_state.second_candle_rsi = c2_rsi
                        side_state.breakout_ready = True

    def generate_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Signal:
        """Generate BUY signal if 2BC setup is ready."""
        assert isinstance(side_state, TwoBodyCandleSideState)
        
        if side_state.position is not None or side_state.pending_entry is not None:
            return Signal.NONE
        
        if side_state.breakout_ready:
            return Signal.BUY_CE if side == "CE" else Signal.BUY_PE
        
        return Signal.NONE

    def compute_risk_points(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> Optional[float]:
        """Calculate risk from entry to initial stop loss."""
        assert isinstance(side_state, TwoBodyCandleSideState)
        
        if side_state.first_candle_close is None:
            return None
        
        # Entry is at High(C2) + 1.0
        # Initial SL is at Low(C1) - 1.0
        entry_price = row.get("high", 0) + 1.0
        initial_sl = side_state.first_candle_close - 1.0  # Approximate using first candle close
        
        risk = entry_price - initial_sl
        
        # Risk cap: discard if risk > 20 points
        if risk > self.config.max_initial_risk:
            return None
        
        return float(risk)

    def compute_entry_lots(self, row: pd.Series, cfg: StrategyConfig) -> int:
        """Position sizing based on VWAP."""
        premium = float(row.get("close", 0))
        vwap = float(row.get("vwap", premium))
        
        if pd.isna(vwap):
            return cfg.half_size_lots
        return cfg.full_size_lots if premium > vwap else cfg.half_size_lots

    def compute_stop_level(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> float:
        """Initial stop loss at Low(C1) - 1.0."""
        assert isinstance(side_state, TwoBodyCandleSideState)
        
        if side_state.first_candle_close is not None:
            return float(side_state.first_candle_close - 1.0)
        
        return float(row.get("low", 0) - 1.0)

    def reset_after_entry(self, side_state: BaseSideState) -> None:
        """Reset state after entry for next signal."""
        assert isinstance(side_state, TwoBodyCandleSideState)
        side_state.consolidation_active = False
        side_state.consolidation_candle_count = 0
        side_state.first_candle_time = None
        side_state.first_candle_close = None
        side_state.first_candle_rsi = None
        side_state.second_candle_rsi = None
        side_state.breakout_ready = False

    def format_setup_status(self, side_state: BaseSideState) -> str:
        """Human-readable status of 2BC setup."""
        assert isinstance(side_state, TwoBodyCandleSideState)
        
        if side_state.breakout_ready:
            return (
                f"✅ 2BC BREAKOUT READY  "
                f"CHOP={side_state.chop_value:.1f}  "
                f"ADX={side_state.adx_value:.1f}  "
                f"RSI1={side_state.first_candle_rsi:.0f} → "
                f"RSI2={side_state.second_candle_rsi:.0f}"
            )
        if side_state.consolidation_active:
            return (
                f"⏳ Consolidation active ({side_state.consolidation_candle_count}/{self.config.consolidation_candles})  "
                f"CHOP={side_state.chop_value:.1f} ADX={side_state.adx_value:.1f}"
            )
        return "⏳ Waiting for consolidation"
