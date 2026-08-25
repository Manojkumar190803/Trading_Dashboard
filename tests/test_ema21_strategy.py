from datetime import datetime, timedelta

import pandas as pd
import pytest

from core.models import Position, Signal
from core.broker import ConsoleBroker, HistoricalReplayBroker
from core.engine import BaseStrategyEngine
from core.models import RiskConfig, StrategyConfig
from strategies.ema21 import EMA21SignalProvider, EMA21SideState


def _row(offset: int, *, open_: float, high: float, low: float, close: float, ema: float) -> pd.Series:
    return pd.Series(
        {
            "datetime": datetime(2026, 8, 10, 9, 20) + timedelta(minutes=5 * offset),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "ema21": ema,
        }
    )


def test_provider_captures_setup_and_first_red_confirmation():
    provider = EMA21SignalProvider()
    state = provider.create_side_state()
    assert isinstance(state, EMA21SideState)

    previous = _row(0, open_=100, high=101, low=98, close=99, ema=100)
    setup = _row(1, open_=99, high=103, low=95, close=101, ema=100)
    provider.update_state(state, setup, previous)

    assert state.setup_active is True
    assert state.setup_candle_low == 95.0
    assert state.confirmation_count == 0

    first_confirmation = _row(2, open_=105, high=106, low=100, close=102, ema=101)
    provider.update_state(state, first_confirmation, setup)

    assert state.confirmation_count == 1
    assert state.first_red_high == 106.0
    assert state.first_red_low == 100.0
    assert provider.generate_signal("CE", state, first_confirmation, setup) == Signal.BUY_CE


def test_provider_emits_signal_on_first_red_confirmation():
    provider = EMA21SignalProvider()
    state = provider.create_side_state()
    previous = _row(0, open_=100, high=101, low=98, close=99, ema=100)
    setup = _row(1, open_=99, high=103, low=95, close=101, ema=100)
    provider.update_state(state, setup, previous)

    first_red = _row(2, open_=105, high=106, low=100, close=102, ema=101)
    provider.update_state(state, first_red, setup)

    assert state.entry_ready is True
    assert provider.generate_signal("CE", state, first_red, setup) == Signal.BUY_CE
    assert provider.compute_risk_points(state, first_red) == 11.0
    assert provider.compute_stop_level(state, first_red) == 95.0


def test_provider_cancels_setup_when_confirmation_closes_on_ema():
    provider = EMA21SignalProvider()
    state = provider.create_side_state()
    previous = _row(0, open_=100, high=101, low=98, close=99, ema=100)
    setup = _row(1, open_=99, high=103, low=95, close=101, ema=100)
    provider.update_state(state, setup, previous)

    invalid = _row(2, open_=105, high=106, low=99, close=101, ema=101)
    provider.update_state(state, invalid, setup)

    assert state.setup_active is False
    assert state.ema_failure is True
    assert provider.generate_signal("CE", state, invalid, setup) == Signal.NONE


def test_engine_places_ema21_stop_entry_at_red_high():
    provider = EMA21SignalProvider()
    engine = BaseStrategyEngine(
        StrategyConfig(max_option_risk_points=20.0),
        RiskConfig(max_sl_per_day=3),
        ConsoleBroker(ltp_fallback=107.0),
        provider,
    )
    engine.state.trading_day = datetime(2026, 8, 10).date()
    engine.state.ce = provider.create_side_state()
    engine.state.pe = provider.create_side_state()
    engine.state.atm_locked = True
    engine.state.ce.option_symbol = "NIFTY12AUG2625000CE"

    previous = _row(0, open_=100, high=101, low=98, close=99, ema=100)
    setup = _row(1, open_=99, high=103, low=95, close=101, ema=100)
    first_red = _row(2, open_=105, high=106, low=100, close=102, ema=101)
    second = _row(3, open_=101, high=104, low=100, close=103, ema=102)
    third = _row(4, open_=102, high=105, low=101, close=104, ema=103)

    engine.process_option_candle("CE", setup, previous)
    engine.process_option_candle("CE", first_red, setup)

    assert engine.state.ce.position is None
    assert engine.state.ce.pending_entry is not None
    assert engine.state.ce.pending_entry.option_trigger_level == 106.0
    assert engine.state.ce.pending_entry.option_stop_level == 95.0

    engine.process_option_candle("CE", second, first_red)
    position = engine.state.ce.position
    assert position is not None
    assert position.entry_price == 107.0
    assert position.option_entry_trigger == 106.0
    assert position.option_stop_level == 95.0
    assert position.quantity == 130
    assert position.initial_quantity == 130
    assert engine.state.ce.pending_entry is None
    assert engine.total_entries == 1


def test_engine_does_not_create_order_when_entry_stop_gap_exceeds_25_points():
    provider = EMA21SignalProvider()
    engine = BaseStrategyEngine(
        StrategyConfig(max_option_risk_points=20.0),
        RiskConfig(max_sl_per_day=3),
        ConsoleBroker(ltp_fallback=150.0),
        provider,
    )
    engine.state.trading_day = datetime(2026, 8, 10).date()
    engine.state.ce = provider.create_side_state()
    engine.state.pe = provider.create_side_state()
    engine.state.atm_locked = True
    engine.state.ce.option_symbol = "NIFTY12AUG2625000CE"

    state = engine.state.ce
    state.setup_candle_low = 95.0
    state.first_red_high = 130.0
    state.first_red_low = 100.0
    row = _row(2, open_=125, high=130, low=120, close=126, ema=121)

    engine.place_pending_entry("CE", state, row["datetime"], row)

    assert state.pending_entry is None
    assert engine.total_entries == 0
    assert any("before order" in alert.message and "gap" in alert.message for alert in engine.alerts)


def test_engine_ema21_one_lot_trails_after_one_and_half_rr():
    provider = EMA21SignalProvider()
    engine = BaseStrategyEngine(
        StrategyConfig(max_option_risk_points=20.0),
        RiskConfig(max_sl_per_day=3),
        ConsoleBroker(ltp_fallback=150.0),
        provider,
    )
    engine.state.ce.option_symbol = "NIFTY12AUG2625000CE"
    engine.state.ce.position = Position(
        option_symbol=engine.state.ce.option_symbol,
        option_type="CE",
        quantity=65,
        initial_quantity=65,
        entry_price=107.0,
        entry_time=datetime(2026, 8, 10, 10, 0),
        option_stop_level=94.0,
        option_entry_trigger=107.0,
        option_risk_points=13.0,
    )

    engine.process_tick("CE", 150.0, datetime(2026, 8, 10, 10, 1))
    position = engine.state.ce.position
    assert position is not None
    assert position.quantity == 65
    assert position.breakeven_armed is True
    assert position.trailing_sl_level == pytest.approx(126.5)
    assert not any("full exit (1-lot)" in alert.message for alert in engine.alerts)


def test_engine_ema21_exit_pnl_uses_actual_fill_price():
    provider = EMA21SignalProvider()
    engine = BaseStrategyEngine(
        StrategyConfig(),
        RiskConfig(),
        ConsoleBroker(ltp_fallback=127.10),
        provider,
    )
    engine.state.ce.position = Position(
        option_symbol="NIFTY12AUG2625000CE",
        option_type="CE",
        quantity=130,
        initial_quantity=130,
        entry_price=57.10,
        entry_time=datetime(2026, 8, 10, 10, 0),
        option_stop_level=50.0,
        option_entry_trigger=57.90,
        option_risk_points=7.90,
    )

    engine._exit_position(
        engine.state.ce,
        datetime(2026, 8, 10, 13, 24),
        130,
        "EMA-21 close exit",
    )

    assert engine.realized_pnl == pytest.approx(9100.0)
    assert engine.state.ce.position is None
    assert "pnl_entry=57.10" in engine.alerts[-1].message


def test_engine_ema21_candle_low_breach_exits_position():
    provider = EMA21SignalProvider()
    engine = BaseStrategyEngine(
        StrategyConfig(),
        RiskConfig(),
        ConsoleBroker(ltp_fallback=128.50),
        provider,
    )
    engine.state.ce.position = Position(
        option_symbol="NIFTY25AUG2624300PE",
        option_type="PE",
        quantity=130,
        initial_quantity=130,
        entry_price=129.20,
        entry_time=datetime(2026, 8, 24, 13, 36),
        option_stop_level=128.55,
        option_entry_trigger=138.80,
        option_risk_points=10.25,
    )

    engine.monitor_open_position(
        engine.state.ce,
        _row(3, open_=129.00, high=129.10, low=128.50, close=128.60, ema=130.00),
    )

    assert engine.state.ce.position is None
    assert engine.state.sl_hits_today == 1
    assert "option low 128.50 <= SL 128.55" in engine.alerts[-1].message


def test_engine_ema21_moves_to_breakeven_at_one_and_half_rr():
    provider = EMA21SignalProvider()
    engine = BaseStrategyEngine(
        StrategyConfig(),
        RiskConfig(),
        ConsoleBroker(ltp_fallback=72.0),
        provider,
    )
    engine.state.ce.position = Position(
        option_symbol="NIFTY25AUG2624300PE",
        option_type="PE",
        quantity=130,
        initial_quantity=130,
        entry_price=57.10,
        entry_time=datetime(2026, 8, 24, 10, 0),
        option_stop_level=50.0,
        option_entry_trigger=57.90,
        option_risk_points=10.25,
    )

    engine.monitor_open_position(
        engine.state.ce,
        _row(4, open_=70.0, high=73.0, low=70.0, close=72.0, ema=65.0),
    )

    assert engine.state.ce.position is not None
    assert engine.state.ce.position.quantity == 130
    assert engine.state.ce.position.breakeven_armed is True
    assert engine.state.ce.position.trailing_sl_level == pytest.approx(57.10)


def test_engine_ema21_books_half_at_two_rr_and_trails():
    provider = EMA21SignalProvider()
    engine = BaseStrategyEngine(
        StrategyConfig(),
        RiskConfig(),
        ConsoleBroker(ltp_fallback=78.0),
        provider,
    )
    engine.state.ce.position = Position(
        option_symbol="NIFTY25AUG2624300PE",
        option_type="PE",
        quantity=130,
        initial_quantity=130,
        entry_price=57.10,
        entry_time=datetime(2026, 8, 24, 10, 0),
        option_stop_level=50.0,
        option_entry_trigger=57.90,
        option_risk_points=10.25,
    )

    engine.monitor_open_position(
        engine.state.ce,
        _row(4, open_=76.0, high=78.0, low=76.0, close=77.0, ema=70.0),
    )

    position = engine.state.ce.position
    assert position is not None
    assert position.quantity == 65
    assert position.t2_done is True
    assert position.trailing_sl_level == pytest.approx(62.225)


def test_replay_stop_limit_fill_uses_trigger_not_candle_close():
    broker = HistoricalReplayBroker()
    symbol = "NIFTY12AUG2625000CE"
    broker.set_current_bar(
        symbol,
        _row(2, open_=145, high=145.2, low=135, close=136.95, ema=140),
    )

    assert broker.simulate_stop_limit_fill(symbol, 144.85, 145.35) == 144.85
    assert broker.get_ltp(symbol) == 136.95


def test_replay_stop_limit_fill_is_rejected_when_limit_is_exceeded():
    broker = HistoricalReplayBroker()
    symbol = "NIFTY12AUG2625000CE"
    broker.set_current_bar(
        symbol,
        _row(2, open_=145, high=145.5, low=135, close=136.95, ema=140),
    )

    assert broker.simulate_stop_limit_fill(symbol, 144.85, 145.35) is None


def test_ema21_stop_entry_does_not_repeat_signal():
    provider = EMA21SignalProvider()
    engine = BaseStrategyEngine(
        StrategyConfig(max_option_risk_points=20.0),
        RiskConfig(max_sl_per_day=3),
        HistoricalReplayBroker(),
        provider,
    )
    engine.state.trading_day = datetime(2026, 8, 10).date()
    engine.state.ce = provider.create_side_state()
    engine.state.pe = provider.create_side_state()
    engine.state.atm_locked = True
    engine.state.ce.option_symbol = "NIFTY12AUG2625000CE"

    previous = _row(0, open_=100, high=101, low=98, close=99, ema=100)
    setup = _row(1, open_=99, high=103, low=95, close=101, ema=100)
    confirmations = [
        _row(2, open_=105, high=106, low=100, close=102, ema=101),
        _row(3, open_=101, high=104, low=101, close=103, ema=102),
        _row(4, open_=102, high=105, low=101, close=104, ema=103),
    ]
    engine.process_option_candle("CE", setup, previous)
    for row, prior in zip(confirmations, [setup, *confirmations[:-1]]):
        engine.process_option_candle("CE", row, prior)

    state = engine.state.ce
    assert state.position is not None
    assert state.entry_ready is False

    engine.process_option_candle(
        "CE",
        _row(5, open_=149, high=151, low=148, close=150, ema=106),
        confirmations[-1],
    )
    assert engine.total_entries == 1
    assert sum(alert.category == "ENTRY" for alert in engine.alerts) == 1