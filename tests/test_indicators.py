"""Unit tests for core.indicators helpers."""

import pandas as pd

from core.indicators import add_indicators, compute_rsi, is_hammer_candle, is_strong_green_candle
from core.models import StrategyConfig


def test_compute_rsi_produces_series_with_expected_length():
    close = pd.Series([100, 101, 102, 100, 99, 101, 103], dtype=float)
    rsi = compute_rsi(close, length=3)
    assert len(rsi) == len(close)
    assert rsi.iloc[-1] == rsi.iloc[-1]


def test_add_indicators_adds_ema_vwap_and_rsi_columns():
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-08-08 09:20:00", "2026-08-08 09:23:00", "2026-08-08 09:26:00"]),
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [10, 20, 30],
        }
    )
    out = add_indicators(df, StrategyConfig())
    for col in ("ema13", "ema20", "ema50", "vwap", "rsi3"):
        assert col in out.columns
    assert out["vwap"].iloc[-1] > 0


def test_is_strong_green_candle_true_and_false_cases():
    strong = pd.Series({"open": 10.0, "high": 20.0, "low": 10.0, "close": 19.5})
    weak = pd.Series({"open": 10.0, "high": 20.0, "low": 10.0, "close": 12.0})
    flat = pd.Series({"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0})
    assert bool(is_strong_green_candle(strong, threshold=0.85))
    assert not bool(is_strong_green_candle(weak, threshold=0.85))
    assert not bool(is_strong_green_candle(flat, threshold=0.85))


def test_is_hammer_candle_true_and_false_cases():
    hammer = pd.Series({"open": 15.0, "high": 16.0, "low": 10.0, "close": 15.5})
    doji = pd.Series({"open": 15.0, "high": 16.0, "low": 10.0, "close": 15.0})
    non_hammer = pd.Series({"open": 10.0, "high": 16.0, "low": 9.5, "close": 15.5})
    zero_range = pd.Series({"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0})
    assert bool(is_hammer_candle(hammer))
    assert not bool(is_hammer_candle(doji))
    assert not bool(is_hammer_candle(non_hammer))
    assert not bool(is_hammer_candle(zero_range))
