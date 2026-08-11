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
    """HD strategy extends BaseSideState with RSI-divergence tracking."""

    swing_low_active: bool = False
    swing_low: Optional[float] = None
    pullback_active: bool = False
    pullback_low_price: Optional[float] = None
    pullback_low_rsi: Optional[float] = None
    pullback_low_time: Optional[datetime] = None
    p1_price: Optional[float] = None
    p1_rsi: Optional[float] = None
    p1_candle_time: Optional[datetime] = None
    p2_price: Optional[float] = None
    p2_rsi: Optional[float] = None
    p2_candle_time: Optional[datetime] = None
    divergence_ready: bool = False


@dataclass
class HDConfig:
    """HD-strategy-specific parameters (not shared with other strategies)."""

    strong_body_threshold: float = 0.85


class HDSignalProvider(SignalProvider):
    """RSI bullish-divergence + trend + trigger-candle signal logic."""

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
        self._update_bullish_setup(side_state, row, prev_row)

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

        bullish_trend = (row["ema13"] > row["ema20"]) or (row["ema20"] > row["ema50"])
        trigger_ok = (
            is_strong_green_candle(row, self.hd_cfg.strong_body_threshold)
            or is_hammer_candle(row)
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

    def compute_risk_points(
        self,
        side_state: BaseSideState,
        row: pd.Series,
    ) -> Optional[float]:
        assert isinstance(side_state, HDSideState)
        if side_state.swing_low is None:
            return None
        return float(row["high"] - side_state.swing_low)

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
        assert isinstance(side_state, HDSideState)
        return float((side_state.swing_low or row["low"]) - 1.0)

    def reset_after_entry(self, side_state: BaseSideState) -> None:
        assert isinstance(side_state, HDSideState)
        side_state.swing_low_active = False
        side_state.swing_low = None
        side_state.pullback_active = False
        side_state.pullback_low_price = None
        side_state.pullback_low_rsi = None
        side_state.pullback_low_time = None
        side_state.p1_price = None
        side_state.p1_rsi = None
        side_state.p1_candle_time = None
        side_state.p2_price = None
        side_state.p2_rsi = None
        side_state.p2_candle_time = None
        side_state.divergence_ready = False

    def format_setup_status(self, side_state: BaseSideState) -> str:
        assert isinstance(side_state, HDSideState)
        if side_state.divergence_ready:
            return (
                f"✅ DIVERGENCE ARMED  "
                f"p1={side_state.p1_price:.1f}(rsi {side_state.p1_rsi:.0f})  "
                f"p2={side_state.p2_price:.1f}(rsi {side_state.p2_rsi:.0f})"
            )
        if side_state.p2_price is not None:
            return (
                f"⏳ P2 found but NO divergence  "
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
        assert isinstance(side_state, HDSideState)
        rsi = row.get("rsi3")
        ema13, ema20, ema50 = row.get("ema13"), row.get("ema20"), row.get("ema50")

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
                f"need p2_price>p1_price AND p2_rsi<p1_rsi)"
            )

        bullish_trend = (ema13 > ema20) or (ema20 > ema50)
        if not bullish_trend:
            return (
                f"EMA_TREND_FAIL (need ema13>ema20 OR ema20>ema50; got "
                f"{ema13:.2f} vs {ema20:.2f} vs {ema50:.2f})"
            )

        strong_green = is_strong_green_candle(row, self.hd_cfg.strong_body_threshold)
        hammer = is_hammer_candle(row)
        if not (strong_green or hammer):
            total = row["high"] - row["low"]
            body = row["close"] - row["open"]
            body_pct = (abs(body) / total * 100) if total > 0 else 0.0
            return (
                f"NO_TRIGGER_CANDLE (need body >= {self.hd_cfg.strong_body_threshold*100:.0f}% "
                f"or hammer; body={body:+.2f}={body_pct:.0f}% of range={total:.2f})"
            )

        return "SIGNAL_OK (unexpected — signal should have fired)"

    # ── RSI-divergence state machine ──────────────────────────────────

    def _update_bullish_setup(
        self,
        ss: HDSideState,
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
            ss.swing_low_active = True
            ss.swing_low = row["low"]
            ss.pullback_active = True
            ss.pullback_low_price = row["low"]
            ss.pullback_low_rsi = rsi
            ss.pullback_low_time = row.get("datetime")
            ss.divergence_ready = False

        if ss.swing_low_active:
            if ss.swing_low is None:
                ss.swing_low = row["low"]
            else:
                ss.swing_low = min(ss.swing_low, row["low"])

        if ss.pullback_active and rsi < 20:
            if ss.pullback_low_price is None:
                ss.pullback_low_price = row["low"]
                ss.pullback_low_time = row.get("datetime")
            else:
                if float(row["low"]) <= float(ss.pullback_low_price):
                    ss.pullback_low_price = row["low"]
                    ss.pullback_low_time = row.get("datetime")
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
                    ss.p1_candle_time = ss.pullback_low_time
                    ss.p2_price = None
                    ss.p2_rsi = None
                    ss.p2_candle_time = None
                    ss.divergence_ready = False
                else:
                    ss.p2_price = finished_price
                    ss.p2_rsi = finished_rsi
                    ss.p2_candle_time = ss.pullback_low_time
                    ss.divergence_ready = (
                        ss.p2_price > ss.p1_price and ss.p2_rsi < ss.p1_rsi
                    )
            ss.pullback_active = False
            ss.pullback_active = False
            ss.pullback_low_price = None
            ss.pullback_low_rsi = None
            ss.pullback_low_time = None
