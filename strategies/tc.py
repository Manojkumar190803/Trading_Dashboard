from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from core.indicators import is_hammer_candle, is_strong_green_candle
from core.models import BaseSideState, Signal, StrategyConfig
from strategies.base import SignalProvider


@dataclass
class TCSideState(BaseSideState):
    """TC strategy state: green-run tracking and red pullback setup."""

    green_run_count: int = 0
    pgs_high: Optional[float] = None
    pgs_low: Optional[float] = None
    pgs_volume: Optional[float] = None
    setup_ready: bool = False
    setup_candle_time: Optional[datetime] = None
    red_high: Optional[float] = None
    red_low: Optional[float] = None


@dataclass
class TCConfig:
    """TC-strategy-specific parameters."""

    strong_body_threshold: float = 0.80


class TCSignalProvider(SignalProvider):
    """Trend continuation logic with high-volume red pullback trigger."""

    def __init__(self, tc_cfg: Optional[TCConfig] = None) -> None:
        self.tc_cfg = tc_cfg or TCConfig()

    def create_side_state(self) -> TCSideState:
        return TCSideState()

    def update_state(
        self,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        assert isinstance(side_state, TCSideState)

        side_state.setup_ready = False
        side_state.setup_candle_time = None
        side_state.red_high = None
        side_state.red_low = None

        if self._is_bullish_momentum_candle(row):
            side_state.green_run_count += 1
            side_state.pgs_high = float(row["high"])
            side_state.pgs_low = float(row["low"])
            side_state.pgs_volume = float(row.get("volume", 0.0))
            return

        is_red = float(row["close"]) < float(row["open"])
        if not is_red:
            self._reset_green_run(side_state)
            return

        can_evaluate_red = (
            side_state.green_run_count >= 2
            and side_state.pgs_high is not None
            and side_state.pgs_low is not None
            and side_state.pgs_volume is not None
        )
        if can_evaluate_red:
            red_volume = float(row.get("volume", 0.0))
            red_high = float(row["high"])
            red_low = float(row["low"])

            if (
                red_volume > side_state.pgs_volume
                and red_high > side_state.pgs_high
                and red_low >= side_state.pgs_low
            ):
                side_state.setup_ready = True
                side_state.setup_candle_time = row.get("datetime")
                side_state.red_high = red_high
                side_state.red_low = red_low

        self._reset_green_run(side_state)

    def generate_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Signal:
        assert isinstance(side_state, TCSideState)

        if side_state.position is not None or side_state.pending_entry is not None:
            return Signal.NONE

        if not side_state.setup_ready:
            return Signal.NONE

        if side_state.setup_candle_time != row.get("datetime"):
            return Signal.NONE

        ema13 = float(row["ema13"])
        ema20 = float(row["ema20"])
        ema50 = float(row["ema50"])
        close = float(row["close"])

        trend_ok = ema13 > ema20 and ema20 > ema50 and close > ema13
        if not trend_ok:
            return Signal.NONE

        return Signal.BUY_CE if side == "CE" else Signal.BUY_PE

    def compute_risk_points(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> Optional[float]:
        assert isinstance(side_state, TCSideState)
        if side_state.red_high is None or side_state.red_low is None:
            return None
        entry = side_state.red_high + 1.0
        stop = side_state.red_low - 1.0
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
        assert isinstance(side_state, TCSideState)
        if side_state.red_low is None:
            return float(row["low"] - 1.0)
        return side_state.red_low - 1.0

    def reset_after_entry(self, side_state: BaseSideState) -> None:
        assert isinstance(side_state, TCSideState)
        self._reset_green_run(side_state)
        side_state.setup_ready = False
        side_state.setup_candle_time = None
        side_state.red_high = None
        side_state.red_low = None

    def format_setup_status(self, side_state: BaseSideState) -> str:
        assert isinstance(side_state, TCSideState)
        if side_state.setup_ready:
            return (
                f"✅ TC READY red_high={side_state.red_high:.1f} "
                f"red_low={side_state.red_low:.1f}"
            )
        if side_state.green_run_count > 0:
            return f"⏳ TC Green run: {side_state.green_run_count}"
        return "⏸  TC waiting for setup"

    def diagnose_no_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Optional[str]:
        assert isinstance(side_state, TCSideState)

        if side_state.setup_ready and side_state.setup_candle_time == row.get("datetime"):
            ema13 = float(row["ema13"])
            ema20 = float(row["ema20"])
            ema50 = float(row["ema50"])
            close = float(row["close"])
            if not (ema13 > ema20 and ema20 > ema50):
                return (
                    f"EMA_ALIGN_FAIL (need ema13>ema20>ema50; got "
                    f"{ema13:.2f}>{ema20:.2f}>{ema50:.2f})"
                )
            if close <= ema13:
                return f"LTP_BELOW_EMA13 (close={close:.2f}, ema13={ema13:.2f})"

        if side_state.green_run_count < 2:
            return f"GREEN_RUN_PENDING ({side_state.green_run_count}/2)"
        return "NO_VALID_RED_SIGNAL"

    def _is_bullish_momentum_candle(self, row: pd.Series) -> bool:
        if float(row["close"]) <= float(row["open"]):
            return False
        return (
            is_strong_green_candle(row, self.tc_cfg.strong_body_threshold)
            or is_hammer_candle(row)
        )

    @staticmethod
    def _reset_green_run(side_state: TCSideState) -> None:
        side_state.green_run_count = 0
        side_state.pgs_high = None
        side_state.pgs_low = None
        side_state.pgs_volume = None