from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.models import BaseSideState, Signal, StrategyConfig


class SignalProvider(ABC):
    """Strategy-specific signal logic. Implement this to plug in new strategies."""

    @abstractmethod
    def create_side_state(self) -> BaseSideState:
        """Return a fresh side state instance (may be a subclass of BaseSideState)."""
        ...

    @abstractmethod
    def update_state(
        self,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        """Update strategy-specific state on each new bar (e.g. divergence tracking)."""
        ...

    @abstractmethod
    def generate_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Signal:
        """Return BUY_CE, BUY_PE, or NONE based on current state + bar."""
        ...

    @abstractmethod
    def compute_risk_points(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> Optional[float]:
        """Compute the option risk (stop distance) for this setup. None = skip."""
        ...

    @abstractmethod
    def compute_entry_lots(
        self,
        row: pd.Series,
        cfg: StrategyConfig,
    ) -> int:
        """Return the number of lots to enter."""
        ...

    @abstractmethod
    def compute_stop_level(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> float:
        """Return the stop-loss price level for a pending entry."""
        ...

    @abstractmethod
    def reset_after_entry(self, side_state: BaseSideState) -> None:
        """Reset setup state after an entry is placed (avoid re-triggering)."""
        ...

    def compute_entry_trigger_level(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> float:
        return float(row["high"] + 1.0)

    def entry_limit_buffer(self, cfg: StrategyConfig) -> float:
        return float(cfg.entry_limit_buffer_points)

    def applies_vwap_room_filter(self) -> bool:
        return getattr(self, "strategy_key", None) != "ema21"

    def submit_stop_limit_on_signal(self) -> bool:
        return getattr(self, "strategy_key", None) == "ema21"

    def pending_entry_cancellation_reason(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Optional[str]:
        return None

    def format_setup_status(self, side_state: BaseSideState) -> str:
        """Return a human-readable string describing the current setup state."""
        return ""

    def diagnose_no_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Optional[str]:
        """Return a diagnostic string explaining why no signal fired, or None."""
        return None
