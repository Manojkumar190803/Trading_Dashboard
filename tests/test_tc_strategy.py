"""Tests for TC (Trend Continuation) strategy signal logic."""

from datetime import datetime

import pandas as pd

from core.models import Signal, StrategyConfig
from strategies.tc import TCSignalProvider


def _row(
    open_=100.0,
    high=110.0,
    low=99.0,
    close=109.0,
    ema13=105.0,
    ema20=104.0,
    ema50=103.0,
    vwap=106.0,
    volume=1000.0,
    dt=None,
) -> pd.Series:
    return pd.Series(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "ema13": ema13,
            "ema20": ema20,
            "ema50": ema50,
            "vwap": vwap,
            "volume": volume,
            "rsi3": 40.0,
            "datetime": dt or datetime(2026, 8, 8, 10, 0),
        }
    )


def test_tc_signal_fires_on_valid_four_gate_setup():
    provider = TCSignalProvider()
    ss = provider.create_side_state()

    # Two bullish momentum candles.
    g1 = _row(open_=100.0, high=108.0, low=99.5, close=107.8, volume=1000, dt=datetime(2026, 8, 8, 10, 0))
    g2 = _row(open_=107.0, high=113.0, low=106.8, close=112.8, volume=1100, dt=datetime(2026, 8, 8, 10, 3))
    provider.update_state(ss, g1, None)
    provider.update_state(ss, g2, g1)

    # Red pullback: high breaks PGS high, low holds PGS low, volume spikes.
    red = _row(
        open_=112.9,
        high=113.5,
        low=107.2,
        close=110.5,
        volume=1500,
        ema13=109.0,
        ema20=108.0,
        ema50=107.0,
        dt=datetime(2026, 8, 8, 10, 6),
    )
    provider.update_state(ss, red, g2)

    sig = provider.generate_signal("CE", ss, red, g2)
    assert sig == Signal.BUY_CE


def test_tc_no_signal_when_red_volume_not_higher_than_pgs():
    provider = TCSignalProvider()
    ss = provider.create_side_state()

    g1 = _row(open_=100.0, high=108.0, low=99.5, close=107.8, volume=1000, dt=datetime(2026, 8, 8, 10, 0))
    g2 = _row(open_=107.0, high=113.0, low=106.8, close=112.8, volume=1100, dt=datetime(2026, 8, 8, 10, 3))
    provider.update_state(ss, g1, None)
    provider.update_state(ss, g2, g1)

    red = _row(
        open_=112.9,
        high=113.5,
        low=107.2,
        close=110.5,
        volume=1000,
        dt=datetime(2026, 8, 8, 10, 6),
    )
    provider.update_state(ss, red, g2)

    assert provider.generate_signal("CE", ss, red, g2) == Signal.NONE


def test_tc_no_signal_when_red_breaks_pgs_low():
    provider = TCSignalProvider()
    ss = provider.create_side_state()

    g1 = _row(open_=100.0, high=108.0, low=99.5, close=107.8, volume=1000, dt=datetime(2026, 8, 8, 10, 0))
    g2 = _row(open_=107.0, high=113.0, low=106.8, close=112.8, volume=1100, dt=datetime(2026, 8, 8, 10, 3))
    provider.update_state(ss, g1, None)
    provider.update_state(ss, g2, g1)

    red = _row(
        open_=112.9,
        high=113.5,
        low=106.7,
        close=110.5,
        volume=1500,
        dt=datetime(2026, 8, 8, 10, 6),
    )
    provider.update_state(ss, red, g2)

    assert provider.generate_signal("CE", ss, red, g2) == Signal.NONE


def test_tc_setup_is_not_reused_on_later_candle():
    provider = TCSignalProvider()
    ss = provider.create_side_state()

    g1 = _row(open_=100.0, high=108.0, low=99.5, close=107.8, volume=1000, dt=datetime(2026, 8, 8, 10, 0))
    g2 = _row(open_=107.0, high=113.0, low=106.8, close=112.8, volume=1100, dt=datetime(2026, 8, 8, 10, 3))
    red = _row(
        open_=112.9,
        high=113.5,
        low=107.2,
        close=110.5,
        volume=1500,
        dt=datetime(2026, 8, 8, 10, 6),
    )
    next_candle = _row(open_=110.6, high=111.0, low=109.8, close=110.9, dt=datetime(2026, 8, 8, 10, 9))

    provider.update_state(ss, g1, None)
    provider.update_state(ss, g2, g1)
    provider.update_state(ss, red, g2)
    assert provider.generate_signal("CE", ss, red, g2) == Signal.BUY_CE

    # Same setup cannot trigger on a later candle.
    assert provider.generate_signal("CE", ss, next_candle, red) == Signal.NONE


def test_tc_risk_and_stop_are_based_on_red_candle_bounds():
    provider = TCSignalProvider()
    ss = provider.create_side_state()

    g1 = _row(open_=100.0, high=108.0, low=99.5, close=107.8, volume=1000, dt=datetime(2026, 8, 8, 10, 0))
    g2 = _row(open_=107.0, high=113.0, low=106.8, close=112.8, volume=1100, dt=datetime(2026, 8, 8, 10, 3))
    red = _row(
        open_=112.9,
        high=114.0,
        low=107.5,
        close=110.5,
        volume=1500,
        dt=datetime(2026, 8, 8, 10, 6),
    )
    provider.update_state(ss, g1, None)
    provider.update_state(ss, g2, g1)
    provider.update_state(ss, red, g2)

    risk = provider.compute_risk_points(ss, red)
    stop = provider.compute_stop_level(ss, red)

    assert risk == (114.0 + 1.0) - (107.5 - 1.0)
    assert stop == 106.5


def test_tc_lot_sizing_uses_vwap_rule():
    provider = TCSignalProvider()
    cfg = StrategyConfig(full_size_lots=2, half_size_lots=1)

    above_vwap = _row(close=111.0, vwap=110.0)
    below_vwap = _row(close=109.0, vwap=110.0)

    assert provider.compute_entry_lots(above_vwap, cfg) == 2
    assert provider.compute_entry_lots(below_vwap, cfg) == 1