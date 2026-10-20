from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from core.indicators import is_hammer_candle, is_strong_green_candle
from core.models import BaseSideState, Signal, StrategyConfig
from strategies.base import SignalProvider


@dataclass
class HDSideState(BaseSideState):
    """Per-option RSI pullback and one-candle alert state."""

    setup_pending: bool = False
    alert_ready: bool = False
    alert_candle_low: Optional[float] = None
    setup_candle_time: Optional[datetime] = None


@dataclass
class HDConfig:
    """HD-strategy-specific parameters (not shared with other strategies)."""

    strong_body_threshold: float = 0.85
    option_tick_size: float = 0.05


class HDSignalProvider(SignalProvider):
    """NIFTY trend + option RSI pullback + alert-candle signal logic."""

    strategy_key = "hd"

    def __init__(self, hd_cfg: Optional[HDConfig] = None) -> None:
        self.hd_cfg = hd_cfg or HDConfig()

    def create_side_state(self) -> HDSideState:
        return HDSideState()

    def update_state(
        self,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        assert isinstance(side_state, HDSideState)
        self._update_setup(side_state, row, prev_row)

    def generate_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Signal:
        assert isinstance(side_state, HDSideState)

        if side_state.position is not None or side_state.pending_entry is not None:
            return Signal.NONE

        if not side_state.alert_ready:
            return Signal.NONE

        trend = self._market_trend(row)
        if trend == "BULLISH" and side == "CE":
            return Signal.BUY_CE
        if trend == "BEARISH" and side == "PE":
            return Signal.BUY_PE
        return Signal.NONE

    def compute_risk_points(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> Optional[float]:
        assert isinstance(side_state, HDSideState)
        if side_state.alert_candle_low is None:
            return None
        return self.compute_entry_trigger_level(side_state, row) - side_state.alert_candle_low

    def compute_entry_lots(self, row: pd.Series, cfg: StrategyConfig) -> int:
        return cfg.full_size_lots

    def compute_stop_level(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> float:
        assert isinstance(side_state, HDSideState)
        return float(side_state.alert_candle_low if side_state.alert_candle_low is not None else row["low"])

    def compute_entry_trigger_level(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> float:
        tick_size = float(row.get("option_tick_size", self.hd_cfg.option_tick_size))
        return float(row["high"] + tick_size)

    def entry_limit_buffer(self, cfg: StrategyConfig) -> float:
        return 0.0

    def applies_vwap_room_filter(self) -> bool:
        return False

    def submit_stop_limit_on_signal(self) -> bool:
        return True

    def reset_after_entry(self, side_state: BaseSideState) -> None:
        assert isinstance(side_state, HDSideState)
        side_state.setup_pending = False
        side_state.alert_ready = False
        side_state.alert_candle_low = None
        side_state.setup_candle_time = None

    def format_setup_status(self, side_state: BaseSideState) -> str:
        assert isinstance(side_state, HDSideState)
        if side_state.alert_ready:
            return "ALERT CANDLE READY"
        if side_state.setup_pending:
            return "WAITING FOR NEXT CANDLE AFTER RSI < 20"
        return "⏸  Waiting for RSI < 20"

    def diagnose_no_signal(
        self,
        side: str,
        side_state: BaseSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> Optional[str]:
        assert isinstance(side_state, HDSideState)
        if side_state.alert_ready:
            return "ALERT_READY"
        if side_state.setup_pending:
            return "WAITING_FOR_ALERT_CANDLE"
        if self._market_trend(row) == "AMBIGUOUS":
            return "AMBIGUOUS_MARKET_TREND"
        return "WAITING_FOR_RSI_CROSS_BELOW_20"

    def _market_trend(self, row: pd.Series) -> str:
        ema13 = row.get("spot_ema13")
        ema20 = row.get("spot_ema20")
        ema50 = row.get("spot_ema50")
        if any(value is None or pd.isna(value) for value in (ema13, ema20, ema50)):
            return "AMBIGUOUS"
        bullish = ema13 > ema20 or ema20 > ema50
        bearish = ema13 < ema20 or ema20 < ema50
        if bullish == bearish:
            return "AMBIGUOUS"
        return "BULLISH" if bullish else "BEARISH"

    def _is_alert_candle(self, row: pd.Series) -> bool:
        if float(row["close"]) <= float(row["open"]):
            return False
        if is_strong_green_candle(row, self.hd_cfg.strong_body_threshold):
            return True
        return is_hammer_candle(row)

    def _update_setup(
        self,
        ss: HDSideState,
        row: pd.Series,
        prev_row: Optional[pd.Series],
    ) -> None:
        ss.alert_ready = False
        rsi = row.get("rsi3")
        if ss.setup_pending:
            ss.setup_pending = False
            if self._is_alert_candle(row):
                ss.alert_ready = True
                ss.alert_candle_low = float(row["low"])

        prev_rsi = None if prev_row is None else prev_row.get("rsi3")
        if (
            rsi is not None
            and not pd.isna(rsi)
            and prev_rsi is not None
            and not pd.isna(prev_rsi)
            and prev_rsi >= 20
            and rsi < 20
        ):
            ss.setup_pending = True
            ss.setup_candle_time = row.get("datetime")
            ss.alert_candle_low = None
