"""Tests for VWAP room filter (Gate 5) and step-trailing SL formula."""

from datetime import datetime
from typing import Optional
from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.broker import ConsoleBroker
from core.engine import BaseStrategyEngine
from core.models import (
    BaseSideState,
    Position,
    RiskConfig,
    Signal,
    StrategyConfig,
)
from strategies.base import SignalProvider


class StubSignalProvider(SignalProvider):
    """Minimal signal provider for engine-level tests."""

    def __init__(self, risk_points: float = 10.0, lots: int = 2):
        self._risk_points = risk_points
        self._lots = lots

    def create_side_state(self) -> BaseSideState:
        return BaseSideState()

    def update_state(self, side_state, row, prev_row):
        pass

    def generate_signal(self, side, side_state, row, prev_row) -> Signal:
        return Signal.NONE

    def compute_risk_points(self, side_state, row) -> Optional[float]:
        return self._risk_points

    def compute_entry_lots(self, row, cfg) -> int:
        return self._lots

    def compute_stop_level(self, side_state, row) -> float:
        return float(row["high"] + 1.0 - self._risk_points)

    def reset_after_entry(self, side_state):
        pass


def _make_row(high=100.0, low=90.0, close=95.0, vwap=120.0, **kwargs):
    data = {
        "high": high, "low": low, "close": close, "open": 92.0,
        "vwap": vwap, "ema13": 95.0, "ema20": 93.0, "ema50": 91.0,
        "rsi3": 30.0, "datetime": datetime(2026, 8, 8, 10, 0),
    }
    data.update(kwargs)
    return pd.Series(data)


def _make_engine(risk_points=10.0, lots=2, min_vwap_room_rr=1.5):
    cfg = StrategyConfig(min_vwap_room_rr=min_vwap_room_rr)
    risk = RiskConfig()
    broker = ConsoleBroker()
    provider = StubSignalProvider(risk_points=risk_points, lots=lots)
    engine = BaseStrategyEngine(cfg=cfg, risk=risk, broker=broker, signal_provider=provider)
    engine.state.atm_locked = True
    engine.state.ce_symbol = "NIFTY08AUG2625000CE"
    engine.state.pe_symbol = "NIFTY08AUG2625000PE"
    return engine


# ═══════════════════════════════════════════════════════════════════════
# VWAP Room Filter Tests
# ═══════════════════════════════════════════════════════════════════════


class TestVwapRoomFilter:
    def test_entry_below_vwap_with_sufficient_room_allowed(self):
        """Entry=101, VWAP=120, IR=10 → room=19 >= 1.5*10=15 → trade placed."""
        engine = _make_engine(risk_points=10.0)
        side_state = engine.signal_provider.create_side_state()
        side_state.option_symbol = "NIFTY08AUG2625000CE"
        row = _make_row(high=100.0, vwap=120.0)  # entry=101, room=19

        ts = datetime(2026, 8, 8, 10, 0)
        engine.place_pending_entry("CE", side_state, ts, row)

        assert side_state.pending_entry is not None

    def test_entry_below_vwap_with_insufficient_room_blocked(self):
        """Entry=101, VWAP=110, IR=10 → room=9 < 1.5*10=15 → trade discarded."""
        engine = _make_engine(risk_points=10.0)
        side_state = engine.signal_provider.create_side_state()
        side_state.option_symbol = "NIFTY08AUG2625000CE"
        row = _make_row(high=100.0, vwap=110.0)  # entry=101, room=9

        ts = datetime(2026, 8, 8, 10, 0)
        engine.place_pending_entry("CE", side_state, ts, row)

        assert side_state.pending_entry is None
        assert any("VWAP room" in a.message for a in engine.alerts)

    def test_entry_above_vwap_filter_not_applied(self):
        """Entry=101, VWAP=95 → entry above VWAP → filter skipped, trade placed."""
        engine = _make_engine(risk_points=10.0)
        side_state = engine.signal_provider.create_side_state()
        side_state.option_symbol = "NIFTY08AUG2625000CE"
        row = _make_row(high=100.0, vwap=95.0)  # entry=101 > vwap=95

        ts = datetime(2026, 8, 8, 10, 0)
        engine.place_pending_entry("CE", side_state, ts, row)

        assert side_state.pending_entry is not None

    def test_vwap_nan_filter_not_applied(self):
        """If VWAP is NaN, filter should not block the trade."""
        engine = _make_engine(risk_points=10.0)
        side_state = engine.signal_provider.create_side_state()
        side_state.option_symbol = "NIFTY08AUG2625000CE"
        row = _make_row(high=100.0, vwap=float("nan"))

        ts = datetime(2026, 8, 8, 10, 0)
        engine.place_pending_entry("CE", side_state, ts, row)

        assert side_state.pending_entry is not None

    def test_boundary_exactly_1_5_rr_allowed(self):
        """Entry=101, VWAP=116, IR=10 → room=15 == 1.5*10=15 → allowed."""
        engine = _make_engine(risk_points=10.0)
        side_state = engine.signal_provider.create_side_state()
        side_state.option_symbol = "NIFTY08AUG2625000CE"
        row = _make_row(high=100.0, vwap=116.0)  # entry=101, room=15

        ts = datetime(2026, 8, 8, 10, 0)
        engine.place_pending_entry("CE", side_state, ts, row)

        assert side_state.pending_entry is not None


# ═══════════════════════════════════════════════════════════════════════
# Step-Trailing SL Formula Tests
# ═══════════════════════════════════════════════════════════════════════


class TestStepTrailingSL:
    def _make_active_position(self, engine, entry=100.0, sl=90.0):
        """Simulate an active 1-lot position past T1 and T2 (trailing phase)."""
        pos = Position(
            option_symbol="NIFTY08AUG2625000CE",
            option_type="CE",
            quantity=65,
            initial_quantity=130,
            entry_price=entry,
            entry_time=datetime(2026, 8, 8, 10, 0),
            option_stop_level=sl,
            option_entry_trigger=entry,
            option_risk_points=entry - sl,
            t1_done=True,
            t2_done=True,
            breakeven_armed=True,
            highest_rr_step=1.5,
            trailing_sl_level=entry,
        )
        engine.state.ce.position = pos
        return pos

    def test_tsl_at_2_0_rr(self):
        """At 2.0 RR: SL should be Entry + 0.5 × IR."""
        engine = _make_engine()
        pos = self._make_active_position(engine, entry=100.0, sl=90.0)
        ir = 10.0

        engine.process_tick("CE", ltp=120.0, ts=datetime(2026, 8, 8, 10, 5))

        expected_sl = 100.0 + 0.5 * ir  # 105.0
        assert pos.trailing_sl_level == pytest.approx(expected_sl)

    def test_tsl_at_2_5_rr(self):
        """At 2.5 RR: SL should be Entry + 1.0 × IR."""
        engine = _make_engine()
        pos = self._make_active_position(engine, entry=100.0, sl=90.0)
        ir = 10.0

        engine.process_tick("CE", ltp=125.0, ts=datetime(2026, 8, 8, 10, 5))

        expected_sl = 100.0 + 1.0 * ir  # 110.0
        assert pos.trailing_sl_level == pytest.approx(expected_sl)

    def test_tsl_at_3_0_rr(self):
        """At 3.0 RR: SL should be Entry + 1.5 × IR."""
        engine = _make_engine()
        pos = self._make_active_position(engine, entry=100.0, sl=90.0)
        ir = 10.0

        engine.process_tick("CE", ltp=130.0, ts=datetime(2026, 8, 8, 10, 5))

        expected_sl = 100.0 + 1.5 * ir  # 115.0
        assert pos.trailing_sl_level == pytest.approx(expected_sl)

    def test_tsl_at_4_0_rr(self):
        """At 4.0 RR: SL should be Entry + 2.5 × IR."""
        engine = _make_engine()
        pos = self._make_active_position(engine, entry=100.0, sl=90.0)
        ir = 10.0

        engine.process_tick("CE", ltp=140.0, ts=datetime(2026, 8, 8, 10, 5))

        expected_sl = 100.0 + 2.5 * ir  # 125.0
        assert pos.trailing_sl_level == pytest.approx(expected_sl)
