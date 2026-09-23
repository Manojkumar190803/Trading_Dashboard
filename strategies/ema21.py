from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from core.models import BaseSideState, Signal, StrategyConfig
from strategies.base import SignalProvider


@dataclass
class EMA21SideState(BaseSideState):
    setup_active: bool = False
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


class EMA21SignalProvider(SignalProvider):
    strategy_key = "ema21"

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

        if side_state.setup_active:
            if float(row["close"]) <= float(ema):
                side_state.ema_failure = True
                side_state.last_ema_failure_time = row.get("datetime")
                self._clear_setup(side_state)
                return
            side_state.confirmation_count += 1
            if float(row["close"]) > float(row["open"]):
                side_state.green_confirmation_count += 1
            elif side_state.first_red_high is None:
                side_state.first_red_high = float(row["high"])
                side_state.first_red_low = float(row["low"])
                side_state.first_red_time = row.get("datetime")
                # The first red candle within the three-candle window triggers
                # the pending stop-limit entry immediately.
                side_state.entry_ready = True

            if side_state.confirmation_count >= 3:
                if side_state.first_red_high is None:
                    self._clear_setup(side_state)
            return

        if prev_row is None:
            return
        prev_ema = prev_row.get("ema21")
        if prev_ema is None or pd.isna(prev_ema):
            return
        if float(prev_row["close"]) <= float(prev_ema) and float(row["close"]) > float(ema):
            side_state.setup_active = True
            side_state.setup_candle_low = float(row["low"])
            side_state.setup_candle_time = row.get("datetime")
            side_state.confirmation_count = 0
            side_state.green_confirmation_count = 0
            side_state.first_red_high = None
            side_state.first_red_low = None
            side_state.first_red_time = None
            side_state.entry_ready = False
            side_state.entry_block_reason = None

    def generate_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Signal:
        assert isinstance(side_state, EMA21SideState)
        if (
            (side_state.entry_ready or side_state.first_red_high is not None)
            and side_state.position is None
            and side_state.pending_entry is None
            and (
                side_state.last_ema_failure_time is None
                or side_state.first_red_time is None
                or side_state.first_red_time > side_state.last_ema_failure_time
            )
        ):
            return Signal.BUY_CE if side == "CE" else Signal.BUY_PE
        return Signal.NONE

    def compute_risk_points(self, side_state: BaseSideState, row: pd.Series) -> Optional[float]:
        assert isinstance(side_state, EMA21SideState)
        if side_state.setup_candle_low is None or side_state.first_red_high is None:
            return None
        trigger = side_state.first_red_high
        stop = side_state.setup_candle_low
        return trigger - stop

    def compute_entry_lots(self, row: pd.Series, cfg: StrategyConfig) -> int:
        return cfg.full_size_lots

    def compute_stop_level(self, side_state: BaseSideState, row: pd.Series) -> float:
        assert isinstance(side_state, EMA21SideState)
        if side_state.setup_candle_low is None:
            raise ValueError("EMA21 setup candle is not available")
        return side_state.setup_candle_low

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
        return float(cfg.entry_limit_buffer_points)

    def applies_vwap_room_filter(self) -> bool:
        return False

    def submit_stop_limit_on_signal(self) -> bool:
        return True

    def reset_after_entry(self, side_state: BaseSideState) -> None:
        assert isinstance(side_state, EMA21SideState)
        self._clear_setup(side_state)

    def process_setup_tick(self, side_state: BaseSideState, ltp: float, ts: datetime) -> bool:
        """Build the live confirmation candle and arm entry on its first red tick."""
        assert isinstance(side_state, EMA21SideState)
        if not side_state.setup_active or side_state.entry_ready:
            return False
        if side_state.setup_candle_time is not None:
            setup_time = side_state.setup_candle_time
            if setup_time.tzinfo is None and ts.tzinfo is not None:
                setup_time = setup_time.replace(tzinfo=ts.tzinfo)
            elif setup_time.tzinfo is not None and ts.tzinfo is None:
                ts = ts.replace(tzinfo=setup_time.tzinfo)
            minute = ts.minute - (ts.minute % 3)
            candle_start = ts.replace(minute=minute, second=0, microsecond=0)
            setup_minute = setup_time.minute - (setup_time.minute % 3)
            next_confirmation_start = setup_time.replace(
                minute=setup_minute, second=0, microsecond=0
            ) + pd.Timedelta(minutes=3).to_pytimedelta()
            if candle_start < next_confirmation_start:
                return False
        else:
            minute = ts.minute - (ts.minute % 3)
            candle_start = ts.replace(minute=minute, second=0, microsecond=0)
        if side_state.live_confirmation_start != candle_start:
            side_state.live_confirmation_start = candle_start
            side_state.live_confirmation_open = float(ltp)
            side_state.live_confirmation_high = float(ltp)
            side_state.live_confirmation_low = float(ltp)
        else:
            side_state.live_confirmation_high = max(
                float(side_state.live_confirmation_high or ltp), float(ltp)
            )
            side_state.live_confirmation_low = min(
                float(side_state.live_confirmation_low or ltp), float(ltp)
            )
        if (
            side_state.live_confirmation_open is not None
            and float(ltp) < side_state.live_confirmation_open
        ):
            side_state.confirmation_count = max(1, side_state.confirmation_count)
            side_state.first_red_high = side_state.live_confirmation_high
            side_state.first_red_low = side_state.live_confirmation_low
            side_state.first_red_time = ts
            side_state.entry_ready = True
            return True
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
        side_state.entry_block_reason = None
        side_state.live_confirmation_start = None
        side_state.live_confirmation_open = None
        side_state.live_confirmation_high = None
        side_state.live_confirmation_low = None

    def format_setup_status(self, side_state: BaseSideState) -> str:
        assert isinstance(side_state, EMA21SideState)
        if side_state.position is not None:
            return "POSITION_ACTIVE"
        if side_state.pending_entry is not None:
            return f"ENTRY_PENDING broker-trigger confirmations={side_state.confirmation_count}/3"
        if side_state.order_submission_uncertain:
            return "ENTRY_SUBMISSION_UNCERTAIN reconcile-broker"
        if side_state.entry_block_reason:
            return f"ENTRY_BLOCKED {side_state.entry_block_reason}"
        if side_state.entry_ready or side_state.first_red_high is not None:
            return f"ENTRY_READY confirmations={side_state.confirmation_count}/3"
        if side_state.setup_active:
            red = "red-found" if side_state.first_red_high is not None else "waiting-red"
            return f"CONFIRMING candles={side_state.confirmation_count}/3 {red}"
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