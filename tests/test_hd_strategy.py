from datetime import datetime

import pandas as pd
import pytest

from core.models import PendingEntry, Position, Signal, StrategyConfig
from strategies.hd import HDSignalProvider


def candle(**values):
    defaults = {
        "datetime": datetime(2026, 10, 15, 9, 30),
        "open": 150.0,
        "high": 160.0,
        "low": 149.0,
        "close": 159.5,
        "rsi3": 25.0,
        "spot_ema13": 101.0,
        "spot_ema20": 100.0,
        "spot_ema50": 99.0,
        "vwap": 155.0,
    }
    defaults.update(values)
    return pd.Series(defaults)


def prepare_next_candle(provider, side="CE", previous_rsi=25.0):
    state = provider.create_side_state()
    pullback = candle(rsi3=19.0, low=148.0)
    provider.update_state(state, pullback, candle(rsi3=previous_rsi))
    return state, pullback


def test_rsi_dip_then_next_strong_green_triggers_ce_in_bullish_market():
    provider = HDSignalProvider()
    state, pullback = prepare_next_candle(provider, "CE")
    alert = candle(datetime=datetime(2026, 10, 15, 9, 33))

    provider.update_state(state, alert, pullback)

    assert provider.generate_signal("CE", state, alert, pullback) is Signal.BUY_CE
    assert provider.compute_entry_trigger_level(state, alert) == 160.05
    assert provider.compute_stop_level(state, alert) == 149.0
    assert provider.compute_risk_points(state, alert) == pytest.approx(11.05)


def test_rsi_dip_then_next_green_hammer_triggers_pe_in_bearish_market():
    provider = HDSignalProvider()
    state, pullback = prepare_next_candle(provider, "PE")
    alert = candle(
        datetime=datetime(2026, 10, 15, 9, 33),
        open=150.0,
        high=152.0,
        low=140.0,
        close=151.0,
        spot_ema13=99.0,
        spot_ema20=100.0,
        spot_ema50=101.0,
    )

    provider.update_state(state, alert, pullback)

    assert provider.generate_signal("PE", state, alert, pullback) is Signal.BUY_PE


def test_setup_expires_when_next_candle_is_not_strong():
    provider = HDSignalProvider()
    state, pullback = prepare_next_candle(provider)
    weak = candle(
        datetime=datetime(2026, 10, 15, 9, 33),
        open=150.0,
        high=160.0,
        low=149.0,
        close=155.0,
    )

    provider.update_state(state, weak, pullback)

    assert provider.generate_signal("CE", state, weak, pullback) is Signal.NONE
    later = candle(datetime=datetime(2026, 10, 15, 9, 36))
    provider.update_state(state, later, weak)
    assert provider.generate_signal("CE", state, later, weak) is Signal.NONE


def test_ambiguous_or_flat_spot_trend_does_not_generate_signal():
    provider = HDSignalProvider()
    state, pullback = prepare_next_candle(provider)
    alert = candle(
        datetime=datetime(2026, 10, 15, 9, 33),
        spot_ema13=101.0,
        spot_ema20=100.0,
        spot_ema50=102.0,
    )
    provider.update_state(state, alert, pullback)

    assert provider.generate_signal("CE", state, alert, pullback) is Signal.NONE
    assert provider.generate_signal("PE", state, alert, pullback) is Signal.NONE


def test_order_and_position_sizing_use_hd_contract():
    provider = HDSignalProvider()
    cfg = StrategyConfig(full_size_lots=3, option_lot_size=65)

    assert provider.compute_entry_lots(candle(), cfg) == 3
    assert provider.entry_limit_buffer(cfg) == 0.0
    assert provider.submit_stop_limit_on_signal()


def test_signal_guards_reject_missing_setup_busy_position_and_wrong_side():
    provider = HDSignalProvider()
    state = provider.create_side_state()
    alert = candle()

    assert provider.generate_signal("CE", state, alert, None) is Signal.NONE

    state.alert_ready = True
    assert provider.generate_signal("PE", state, alert, None) is Signal.NONE
    state.pending_entry = PendingEntry(
        signal=Signal.BUY_CE,
        created_at=alert["datetime"],
        option_symbol="NIFTYCE",
        quantity=65,
        option_trigger_level=160.05,
        option_stop_level=149,
        trigger_candle_high=160,
        trigger_candle_low=149,
    )
    assert provider.generate_signal("CE", state, alert, None) is Signal.NONE
    state.pending_entry = None
    state.position = Position(
        option_symbol="NIFTYCE",
        option_type="CE",
        quantity=65,
        initial_quantity=65,
        entry_price=160.05,
        entry_time=alert["datetime"],
        option_stop_level=149,
        option_entry_trigger=160.05,
        option_risk_points=11.05,
    )
    assert provider.generate_signal("CE", state, alert, None) is Signal.NONE


def test_risk_stop_and_tick_size_fallbacks():
    provider = HDSignalProvider()
    state = provider.create_side_state()
    row = candle(option_tick_size=0.1)

    assert provider.compute_risk_points(state, row) is None
    assert provider.compute_stop_level(state, row) == 149.0
    assert provider.compute_entry_trigger_level(state, row) == 160.1
    state.alert_candle_low = 148.0
    assert provider.compute_stop_level(state, row) == 148.0
    assert provider.compute_entry_trigger_level(state, candle()) == 160.05


def test_status_diagnostics_and_reset_cover_each_setup_state():
    provider = HDSignalProvider()
    state = provider.create_side_state()
    row = candle()

    assert provider.format_setup_status(state) == "⏸  Waiting for RSI < 20"
    assert provider.diagnose_no_signal("CE", state, row, None) == "WAITING_FOR_RSI_CROSS_BELOW_20"

    state.setup_pending = True
    assert provider.format_setup_status(state) == "WAITING FOR NEXT CANDLE AFTER RSI < 20"
    assert provider.diagnose_no_signal("CE", state, row, None) == "WAITING_FOR_ALERT_CANDLE"

    state.alert_ready = True
    assert provider.format_setup_status(state) == "ALERT CANDLE READY"
    assert provider.diagnose_no_signal("CE", state, row, None) == "ALERT_READY"
    provider.reset_after_entry(state)
    assert provider.format_setup_status(state) == "⏸  Waiting for RSI < 20"
    assert state.alert_candle_low is None


def test_rsi_requires_valid_cross_and_red_or_weak_candles_expire_setup():
    provider = HDSignalProvider()
    state = provider.create_side_state()
    provider.update_state(state, candle(rsi3=19.0), None)
    assert not state.setup_pending

    prior = candle(rsi3=19.0)
    provider.update_state(state, candle(rsi3=19.0), prior)
    assert not state.setup_pending
    provider.update_state(state, candle(rsi3=float("nan")), candle(rsi3=25.0))
    assert not state.setup_pending

    state, pullback = prepare_next_candle(provider)
    red = candle(
        datetime=datetime(2026, 10, 15, 9, 33),
        open=160.0,
        high=161.0,
        low=149.0,
        close=150.0,
    )
    provider.update_state(state, red, pullback)
    assert not state.alert_ready
    assert state.alert_candle_low is None


def test_diagnosis_reports_ambiguous_trend_and_missing_spot_ema():
    provider = HDSignalProvider()
    state = provider.create_side_state()

    assert provider.diagnose_no_signal("CE", state, pd.Series({"rsi3": 25}), None) == "AMBIGUOUS_MARKET_TREND"