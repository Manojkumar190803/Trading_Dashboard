"""Focused tests for BaseStrategyEngine tick and square-off behavior."""

from datetime import datetime

from core.broker import ConsoleBroker
from core.engine import BaseStrategyEngine
from core.models import BaseSideState, Position, RiskConfig, Signal, StrategyConfig
from strategies.base import SignalProvider


class StubSignalProvider(SignalProvider):
    def create_side_state(self) -> BaseSideState:
        return BaseSideState()

    def update_state(self, side_state, row, prev_row):
        pass

    def generate_signal(self, side, side_state, row, prev_row):
        return Signal.NONE

    def compute_risk_points(self, side_state, row):
        return 10.0

    def compute_entry_lots(self, row, cfg):
        return 1

    def compute_stop_level(self, side_state, row):
        return float(row["low"] - 1.0)

    def reset_after_entry(self, side_state):
        pass


def _make_engine() -> BaseStrategyEngine:
    return BaseStrategyEngine(
        cfg=StrategyConfig(option_lot_size=65),
        risk=RiskConfig(max_sl_per_day=3),
        broker=ConsoleBroker(ltp_fallback=100.0),
        signal_provider=StubSignalProvider(),
    )


def _attach_position(engine: BaseStrategyEngine, side: str = "CE") -> None:
    ss = engine.state.ce if side == "CE" else engine.state.pe
    ss.position = Position(
        option_symbol="NIFTY08AUG2625000CE" if side == "CE" else "NIFTY08AUG2625000PE",
        option_type=side,
        quantity=130,
        initial_quantity=130,
        entry_price=100.0,
        entry_time=datetime(2026, 8, 8, 10, 0),
        option_stop_level=90.0,
        option_entry_trigger=100.0,
        option_risk_points=10.0,
    )


def test_process_tick_no_position_is_noop():
    engine = _make_engine()
    engine.process_tick("CE", 110.0, datetime(2026, 8, 8, 10, 1))
    assert engine.state.ce.position is None


def test_process_tick_hard_stop_exits_position():
    engine = _make_engine()
    _attach_position(engine, "CE")
    engine.process_tick("CE", 89.0, datetime(2026, 8, 8, 10, 2))
    assert engine.state.ce.position is None
    assert engine.total_hard_sl_hits == 1


def test_process_tick_arms_tsl_and_partial_exit_for_two_lot_position():
    engine = _make_engine()
    _attach_position(engine, "CE")

    # 1.5 RR arms breakeven.
    engine.process_tick("CE", 115.0, datetime(2026, 8, 8, 10, 3))
    pos = engine.state.ce.position
    assert pos is not None and pos.breakeven_armed is True

    # 2.0 RR books one lot (65 qty from initial 130).
    engine.process_tick("CE", 120.0, datetime(2026, 8, 8, 10, 4))
    pos = engine.state.ce.position
    assert pos is not None and pos.quantity == 65


def test_force_square_off_side_clears_pending_and_position():
    engine = _make_engine()
    _attach_position(engine, "PE")
    ss = engine.state.pe
    ss.pending_entry = object()  # type: ignore[assignment]
    engine.force_square_off_side(ss, datetime(2026, 8, 8, 15, 16))
    assert ss.pending_entry is None
    assert ss.position is None