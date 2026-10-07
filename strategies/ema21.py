from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from typing import Optional

import pandas as pd

from core.models import BaseSideState, Signal, StrategyConfig
from strategies.base import SignalProvider


@dataclass
class EMA21SideState(BaseSideState):
    """Buy setup state for one option side."""

    setup_active: bool = False
    setup_low: Optional[float] = None
    setup_candle_low: Optional[float] = None
    setup_candle_time: Optional[datetime] = None
    confirmation_count: int = 0
    green_confirmation_count: int = 0
    first_red_high: Optional[float] = None
    first_red_low: Optional[float] = None
    first_red_time: Optional[datetime] = None
    entry_ready: bool = False
    ema_failure: bool = False
    last_ema_failure_time: Optional[datetime] = None
    live_confirmation_start: Optional[datetime] = None
    live_confirmation_open: Optional[float] = None
    live_confirmation_high: Optional[float] = None
    live_confirmation_low: Optional[float] = None
    setup_invalidated: bool = False


@dataclass
class EMA21Config:
    """EMA21 strategy-specific order parameters in option premium points."""

    entry_limit_buffer: float = 0.5
    exit_limit_buffer: float = 0.5
    confirmation_candles: int = 3

    @classmethod
    def from_env(cls) -> "EMA21Config":
        return cls(
            entry_limit_buffer=_env_float(
                "EMA21_ENTRY_LIMIT_BUFFER", cls.entry_limit_buffer
            ),
            exit_limit_buffer=_env_float(
                "EMA21_EXIT_LIMIT_BUFFER", cls.exit_limit_buffer
            ),
            confirmation_candles=_env_int(
                "EMA21_CONFIRMATION_CANDLES", cls.confirmation_candles, minimum=1
            ),
        )


class EMA21SignalProvider(SignalProvider):
    strategy_key = "ema21"
    setup_cross_tolerance = 0.01

    def __init__(self, ema21_cfg: Optional[EMA21Config] = None) -> None:
        self.ema21_cfg = ema21_cfg or EMA21Config.from_env()

    def create_side_state(self) -> EMA21SideState:
        return EMA21SideState()

    def update_state(
        self,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        assert isinstance(side_state, EMA21SideState)
        side_state.ema_failure = False
        ema = row.get("ema21")
        if ema is None or pd.isna(ema):
            return

        if side_state.setup_low is None and side_state.setup_active:
            side_state.setup_low = side_state.setup_candle_low

        if side_state.setup_low is None and not side_state.setup_active:
            if self._is_setup_cross(row, prev_row):
                side_state.setup_low = float(row["low"])
                side_state.setup_active = True
                side_state.setup_candle_low = side_state.setup_low
                side_state.setup_candle_time = row.get("datetime")
                side_state.confirmation_count = 0
                side_state.green_confirmation_count = 0
                side_state.first_red_high = None
                side_state.first_red_low = None
                side_state.first_red_time = None
                side_state.entry_ready = False
                side_state.setup_invalidated = False
                side_state.entry_block_reason = None
            return

        row_dt = row.get("datetime")
        setup_dt = side_state.setup_candle_time
        if row_dt == setup_dt:
            return

        if (
            side_state.confirmation_count >= self.ema21_cfg.confirmation_candles
            and side_state.first_red_high is None
        ):
            self._clear_setup(side_state)
            return

        side_state.confirmation_count += 1
        if float(row["close"]) <= float(ema):
            side_state.setup_invalidated = True
            side_state.ema_failure = True
            side_state.last_ema_failure_time = row.get("datetime")
            self._clear_setup(side_state)
            side_state.ema_failure = True
            side_state.last_ema_failure_time = row.get("datetime")
            return

        if float(row["close"]) > float(row["open"]):
            side_state.green_confirmation_count += 1
        if side_state.first_red_high is None and float(row["close"]) < float(row["open"]):
            side_state.first_red_high = float(row["high"])
            side_state.first_red_low = float(row["low"])
            side_state.first_red_time = row.get("datetime")
            side_state.entry_ready = True
        if (
            side_state.confirmation_count >= self.ema21_cfg.confirmation_candles
            and side_state.first_red_high is None
        ):
            self._clear_setup(side_state)

    def generate_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Signal:
        assert isinstance(side_state, EMA21SideState)
        if side_state.position is not None or side_state.pending_entry is not None:
            return Signal.NONE
        if side_state.setup_invalidated:
            self._clear_setup(side_state)
            return Signal.NONE
        if side_state.first_red_time != row.get("datetime"):
            return Signal.NONE
        return Signal.BUY_CE if side == "CE" else Signal.BUY_PE

    def compute_risk_points(self, side_state: BaseSideState, row: pd.Series) -> Optional[float]:
        assert isinstance(side_state, EMA21SideState)
        setup_low = side_state.setup_low
        if setup_low is None:
            setup_low = side_state.setup_candle_low
        if setup_low is None or side_state.first_red_high is None:
            return None
        return side_state.first_red_high - setup_low

    def compute_entry_lots(self, row: pd.Series, cfg: StrategyConfig) -> int:
        return cfg.full_size_lots

    def compute_stop_level(self, side_state: BaseSideState, row: pd.Series) -> float:
        assert isinstance(side_state, EMA21SideState)
        setup_low = side_state.setup_low or side_state.setup_candle_low
        if setup_low is None:
            raise ValueError("EMA21 setup candle is not available")
        return setup_low

    def compute_entry_trigger_level(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> float:
        assert isinstance(side_state, EMA21SideState)
        if side_state.first_red_high is None:
            raise ValueError("EMA21 trigger requested before red confirmation")
        return side_state.first_red_high

    def entry_limit_buffer(self, cfg: StrategyConfig) -> float:
        return self.ema21_cfg.entry_limit_buffer

    def exit_limit_buffer(self, cfg: StrategyConfig) -> float:
        return self.ema21_cfg.exit_limit_buffer

    def pending_entry_cancellation_reason(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Optional[str]:
        assert isinstance(side_state, EMA21SideState)
        if side_state.setup_invalidated:
            self._clear_setup(side_state)
            return "confirmation candle closed at or below EMA21"
        return None

    def applies_vwap_room_filter(self) -> bool:
        return False

    def submit_stop_limit_on_signal(self) -> bool:
        return True

    def reset_after_entry(self, side_state: BaseSideState) -> None:
        assert isinstance(side_state, EMA21SideState)
        self._clear_setup(side_state)

    def process_setup_tick(self, side_state: BaseSideState, ltp: float, ts: datetime) -> bool:
        """Ignore forming confirmation candles; entries require a closed candle."""
        assert isinstance(side_state, EMA21SideState)
        return False

    @staticmethod
    def _clear_setup(side_state: EMA21SideState) -> None:
        side_state.setup_active = False
        side_state.setup_candle_low = None
        side_state.setup_candle_time = None
        side_state.confirmation_count = 0
        side_state.green_confirmation_count = 0
        side_state.first_red_high = None
        side_state.first_red_low = None
        side_state.first_red_time = None
        side_state.entry_ready = False
        side_state.setup_low = None
        side_state.setup_invalidated = False
        side_state.entry_block_reason = None
        side_state.live_confirmation_start = None
        side_state.live_confirmation_open = None
        side_state.live_confirmation_high = None
        side_state.live_confirmation_low = None

    def format_setup_status(self, side_state: BaseSideState) -> str:
        assert isinstance(side_state, EMA21SideState)
        if side_state.position is not None:
            return "POSITION_ACTIVE"
        # Counting intentionally keeps advancing past the window once a red
        # trigger is found (see test_provider_keeps_setup_active_past_max_
        # confirmations_once_red_found) so it must be capped for display only.
        displayed_count = min(side_state.confirmation_count, self.ema21_cfg.confirmation_candles)
        if side_state.pending_entry is not None:
            alert = " alert-candle-triggered" if side_state.first_red_time is not None else ""
            return (
                f"ENTRY_PENDING broker-trigger confirmations="
                f"{displayed_count}/{self.ema21_cfg.confirmation_candles}"
                f"{alert}"
            )
        if side_state.order_submission_uncertain:
            return "ENTRY_SUBMISSION_UNCERTAIN reconcile-broker"
        if side_state.entry_block_reason:
            return f"ENTRY_BLOCKED {side_state.entry_block_reason}"
        if side_state.entry_ready or side_state.first_red_high is not None:
            return (
                f"ENTRY_READY confirmations={displayed_count}/"
                f"{self.ema21_cfg.confirmation_candles} alert-candle-triggered"
            )
        if side_state.setup_active:
            red = "red-found" if side_state.first_red_high is not None else "waiting-red"
            return (
                f"CONFIRMING candles={side_state.confirmation_count}/"
                f"{self.ema21_cfg.confirmation_candles} {red}"
            )
        return "WAITING"

    def diagnose_no_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Optional[str]:
        assert isinstance(side_state, EMA21SideState)
        return self.format_setup_status(side_state)

    @staticmethod
    def _is_setup_cross(row: pd.Series, prev_row: Optional[pd.Series]) -> bool:
        if prev_row is None:
            return False
        prev_ema = prev_row.get("ema21")
        ema = row.get("ema21")
        if prev_ema is None or ema is None or pd.isna(prev_ema) or pd.isna(ema):
            return False
        return (
            float(prev_row["close"]) <= float(prev_ema) + EMA21SignalProvider.setup_cross_tolerance
            and float(row["close"]) > float(ema)
        )


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _env_int(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value