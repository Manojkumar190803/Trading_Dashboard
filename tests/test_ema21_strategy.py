from datetime import datetime, timedelta

import pandas as pd
import pytest

from core.models import PendingEntry, Position, Signal
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


def test_provider_captures_first_red_within_three_candles():
    provider = EMA21SignalProvider()
    state = provider.create_side_state()
    assert isinstance(state, EMA21SideState)

    previous = _row(0, open_=100, high=101, low=98, close=99, ema=100)
    setup = _row(1, open_=99, high=103, low=95, close=101, ema=100)
    provider.update_state(state, setup, previous)

    assert state.setup_active is True
    assert state.setup_candle_low == 95.0
    assert state.confirmation_count == 0

    first_green = _row(2, open_=101, high=106, low=100, close=102, ema=101)
    first_red = _row(3, open_=105, high=108, low=100, close=102, ema=101)
    provider.update_state(state, first_green, setup)
    provider.update_state(state, first_red, first_green)

    assert state.confirmation_count == 2
    assert state.green_confirmation_count == 1
    assert state.first_red_high == 108.0
    assert state.first_red_low == 100.0
    assert provider.generate_signal("CE", state, first_red, first_green) == Signal.BUY_CE


def test_provider_emits_signal_on_red_within_three_candles():
    provider = EMA21SignalProvider()
    state = provider.create_side_state()
    previous = _row(0, open_=100, high=101, low=98, close=99, ema=100)
    setup = _row(1, open_=99, high=103, low=95, close=101, ema=100)
    provider.update_state(state, setup, previous)

    first_green = _row(2, open_=101, high=106, low=100, close=102, ema=101)
    second_green = _row(3, open_=102, high=107, low=101, close=104, ema=102)
    first_red = _row(4, open_=105, high=106, low=100, close=102, ema=101)
    provider.update_state(state, first_green, setup)
    provider.update_state(state, second_green, first_green)
    provider.update_state(state, first_red, second_green)

    assert state.entry_ready is True
    assert provider.generate_signal("CE", state, first_red, setup) == Signal.BUY_CE
    assert provider.compute_risk_points(state, first_red) == 11.0
    assert provider.compute_stop_level(state, first_red) == 95.0


def test_provider_rejects_setup_without_red_within_three_candles():
    provider = EMA21SignalProvider()
    state = provider.create_side_state()
    previous = _row(0, open_=100, high=101, low=98, close=99, ema=100)
    setup = _row(1, open_=99, high=103, low=95, close=101, ema=100)
    provider.update_state(state, setup, previous)

    for offset in (2, 3, 4):
        green = _row(offset, open_=101, high=106, low=100, close=102, ema=101)
        provider.update_state(state, green, setup)

    assert state.setup_active is False
    assert state.entry_ready is False
    assert provider.generate_signal("CE", state, green, setup) == Signal.NONE


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
    first_green = _row(2, open_=101, high=106, low=100, close=102, ema=101)
    second_green = _row(3, open_=102, high=107, low=101, close=104, ema=102)
    first_red = _row(4, open_=105, high=106, low=100, close=102, ema=101)

    engine.process_option_candle("CE", setup, previous)
    engine.process_option_candle("CE", first_green, setup)
    engine.process_option_candle("CE", second_green, first_green)
    engine.process_option_candle("CE", first_red, second_green)

    assert engine.state.ce.position is None
    assert engine.state.ce.pending_entry is not None
    assert engine.state.ce.pending_entry.option_trigger_level == 106.0
    assert engine.state.ce.pending_entry.option_stop_level == 95.0

    engine.process_option_candle("CE", _row(5, open_=101, high=104, low=100, close=103, ema=102), first_red)
    position = engine.state.ce.position
    assert position is not None
    assert position.entry_price == 107.0
    assert position.option_entry_trigger == 106.0
    assert position.option_stop_level == 95.0
    assert position.quantity == 130
    assert position.initial_quantity == 130
    assert engine.state.ce.pending_entry is None
    assert engine.total_entries == 1


def test_ema21_cancels_old_order_before_accepting_new_setup():
    class LiveOrderBroker(ConsoleBroker):
        def __init__(self):
            super().__init__(ltp_fallback=107.0)
            self.order_ids = []
            self.cancelled = []

        def place_stop_limit_order(self, symbol, side, quantity, trigger_price, limit_price):
            order_id = f"OID-{len(self.order_ids) + 1}"
            self.order_ids.append((order_id, trigger_price))
            return order_id

        def get_order_status(self, order_id):
            return {"order_status": "open", "orderid": order_id}

        def cancel_order(self, order_id):
            self.cancelled.append(order_id)
            return True

    provider = EMA21SignalProvider()
    broker = LiveOrderBroker()
    engine = BaseStrategyEngine(
        StrategyConfig(max_option_risk_points=30.0),
        RiskConfig(max_sl_per_day=3),
        broker,
        provider,
    )
    engine.state.trading_day = datetime(2026, 8, 10).date()
    engine.state.atm_locked = True
    engine.state.ce = provider.create_side_state()
    engine.state.ce.option_symbol = "NIFTY12AUG2625000CE"

    previous = _row(0, open_=100, high=101, low=98, close=99, ema=100)
    first_setup = _row(1, open_=99, high=103, low=95, close=101, ema=100)
    first_green = _row(2, open_=101, high=110, low=100, close=105, ema=101)
    first_red = _row(3, open_=120, high=116.25, low=108, close=112, ema=110)
    failed = _row(4, open_=112, high=114, low=106, close=108, ema=110)
    second_setup = _row(5, open_=108, high=115, low=100, close=112, ema=110)
    second_green = _row(6, open_=112, high=120, low=110, close=118, ema=115)
    second_red = _row(7, open_=124, high=123.40, low=115, close=120, ema=118)

    for row, prior in (
        (first_setup, previous),
        (first_green, first_setup),
        (first_red, first_green),
        (failed, first_red),
        (second_setup, failed),
        (second_green, second_setup),
        (second_red, second_green),
    ):
        engine.process_option_candle("CE", row, prior)

    assert broker.cancelled == ["OID-1"]
    assert broker.order_ids == [("OID-1", 116.25), ("OID-2", 123.40)]
    assert engine.state.ce.pending_entry is not None
    assert engine.state.ce.pending_entry.option_trigger_level == 123.40


def test_completed_entry_with_zero_broker_quantity_clears_pending_state():
    class CompletedButFlatBroker(ConsoleBroker):
        requires_position_reconciliation = True

        def get_order_status(self, order_id):
            return {
                "order_status": "complete",
                "orderid": order_id,
                "average_price": 128.85,
            }

        def get_position_book(self):
            return []

    provider = EMA21SignalProvider()
    engine = BaseStrategyEngine(
        StrategyConfig(),
        RiskConfig(max_sl_per_day=3),
        CompletedButFlatBroker(),
        provider,
    )
    engine.state.atm_locked = True
    engine.state.pe = provider.create_side_state()
    engine.state.pe.option_symbol = "NIFTY15SEP2623700PE"
    engine.state.pe.pending_entry = PendingEntry(
        signal=Signal.BUY_PE,
        created_at=datetime(2026, 9, 8, 12, 48),
        option_symbol=engine.state.pe.option_symbol,
        quantity=130,
        option_trigger_level=128.70,
        option_stop_level=118.30,
        trigger_candle_high=128.70,
        trigger_candle_low=125.05,
        order_id="stale-completed-order",
    )

    engine.try_fill_pending_entry(
        "PE",
        engine.state.pe,
        datetime(2026, 9, 8, 12, 54),
        _row(0, open_=123, high=124, low=122, close=122.30, ema=123.0),
    )

    assert engine.state.pe.pending_entry is None
    assert engine.state.pe.position is None
    assert any("no broker position" in alert.message for alert in engine.alerts)


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


def test_engine_skips_live_entry_when_broker_position_already_exists():
    class PositionBroker(ConsoleBroker):
        def get_position_book(self):
            return [{"symbol": "NIFTY12AUG2625000CE", "quantity": 130}]

    provider = EMA21SignalProvider()
    engine = BaseStrategyEngine(
        StrategyConfig(max_option_risk_points=20.0),
        RiskConfig(max_sl_per_day=3),
        PositionBroker(ltp_fallback=107.0),
        provider,
    )
    engine.state.trading_day = datetime(2026, 8, 10).date()
    engine.state.atm_locked = True
    engine.state.ce.option_symbol = "NIFTY12AUG2625000CE"
    state = engine.state.ce
    state.setup_candle_low = 95.0
    state.first_red_high = 106.0
    row = _row(2, open_=105, high=106, low=100, close=102, ema=101)

    engine.place_pending_entry("CE", state, row["datetime"], row)

    assert state.pending_entry is None
    assert state.position is None
    assert any("broker position already exists" in alert.message for alert in engine.alerts)


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


def test_engine_ema21_candle_low_breach_exits_position(tmp_path, monkeypatch):
    monkeypatch.setenv("SHARED_SL_COUNT_FILE", str(tmp_path / "sl_hits.json"))
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
        _row(2, open_=101, high=106, low=100, close=102, ema=101),
        _row(3, open_=102, high=104, low=101, close=103, ema=102),
        _row(4, open_=105, high=106, low=101, close=103, ema=102),
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