"""BO (Breakout) Strategy — simple breakout detection at market open."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from core.models import BaseSideState, Signal, StrategyConfig
from strategies.base import SignalProvider


@dataclass
class BreakoutSideState(BaseSideState):
    """Breakout strategy state for one option side."""

    opening_range_established: bool = False
    opening_range_high: Optional[float] = None
    opening_range_low: Optional[float] = None
    opening_range_candles: int = 0
    breakout_trigger_high: Optional[float] = None
    breakout_trigger_low: Optional[float] = None
    breakout_ready: bool = False


@dataclass
class BreakoutConfig:
    """Breakout strategy-specific parameters."""

    opening_range_candles: int = 5  # Number of candles to form opening range
    breakout_threshold: float = 0.5  # Points above/below opening range
    entry_limit_buffer: float = 0.5
    exit_limit_buffer: float = 0.5
    stop_loss_buffer: float = 1.0  # Points below opening range low for CE


class BreakoutSignalProvider(SignalProvider):
    """Simple breakout strategy based on opening range."""

    def __init__(self, config: Optional[BreakoutConfig] = None) -> None:
        self.config = config or BreakoutConfig()

    def create_side_state(self) -> BreakoutSideState:
        return BreakoutSideState()

    def update_state(
        self,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        """Update breakout state based on current candle."""
        assert isinstance(side_state, BreakoutSideState)
        
        # Establish opening range
        if not side_state.opening_range_established:
            if side_state.opening_range_candles == 0:
                side_state.opening_range_high = row.get("high", 0)
                side_state.opening_range_low = row.get("low", float('inf'))
            
            high = row.get("high", 0)
            low = row.get("low", float('inf'))
            
            if high > side_state.opening_range_high:
                side_state.opening_range_high = high
            if low < side_state.opening_range_low:
                side_state.opening_range_low = low
            
            side_state.opening_range_candles += 1
            
            if side_state.opening_range_candles >= self.config.opening_range_candles:
                side_state.opening_range_established = True
                side_state.breakout_trigger_high = (
                    side_state.opening_range_high + self.config.breakout_threshold
                )
                side_state.breakout_trigger_low = (
                    side_state.opening_range_low - self.config.breakout_threshold
                )
        
        # Check for breakout
        elif not side_state.breakout_ready:
            current_high = row.get("high", 0)
            current_low = row.get("low", float('inf'))
            
            if (current_high > side_state.breakout_trigger_high or 
                current_low < side_state.breakout_trigger_low):
                side_state.breakout_ready = True

    def generate_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Signal:
        """Generate BUY signal if breakout is triggered."""
        assert isinstance(side_state, BreakoutSideState)
        
        if side_state.position is not None or side_state.pending_entry is not None:
            return Signal.NONE
        
        if not side_state.breakout_ready:
            return Signal.NONE
        
        # Buy on upside breakout (above opening range high)
        if side_state.opening_range_high is not None:
            if row.get("high", 0) > side_state.breakout_trigger_high:
                return Signal.BUY_CE if side == "CE" else Signal.BUY_PE
        
        return Signal.NONE

    def compute_risk_points(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> Optional[float]:
        """Calculate risk based on opening range."""
        assert isinstance(side_state, BreakoutSideState)
        
        if side_state.opening_range_low is None:
            return None
        
        entry_price = row.get("high", 0) + self.config.breakout_threshold
        stop_price = side_state.opening_range_low - self.config.stop_loss_buffer
        
        return float(entry_price - stop_price)

    def compute_entry_lots(self, row: pd.Series, cfg: StrategyConfig) -> int:
        """Standard position sizing."""
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
        """Stop loss below opening range low."""
        assert isinstance(side_state, BreakoutSideState)
        
        if side_state.opening_range_low is not None:
            return float(side_state.opening_range_low - self.config.stop_loss_buffer)
        
        return float(row.get("low", 0) - self.config.stop_loss_buffer)

    def reset_after_entry(self, side_state: BaseSideState) -> None:
        """Reset state after entry."""
        assert isinstance(side_state, BreakoutSideState)
        side_state.opening_range_established = False
        side_state.opening_range_high = None
        side_state.opening_range_low = None
        side_state.opening_range_candles = 0
        side_state.breakout_trigger_high = None
        side_state.breakout_trigger_low = None
        side_state.breakout_ready = False

    def format_setup_status(self, side_state: BaseSideState) -> str:
        """Human-readable status of breakout setup."""
        assert isinstance(side_state, BreakoutSideState)
        
        if side_state.breakout_ready:
            return (
                f"✅ BREAKOUT READY  "
                f"OR: [{side_state.opening_range_low:.1f}, {side_state.opening_range_high:.1f}]"
            )
        if side_state.opening_range_established:
            return (
                f"⏳ Range established ({side_state.opening_range_candles} candles)  "
                f"[{side_state.opening_range_low:.1f}, {side_state.opening_range_high:.1f}]"
            )
        return f"⏳ Building opening range ({side_state.opening_range_candles}/{self.config.opening_range_candles})"
