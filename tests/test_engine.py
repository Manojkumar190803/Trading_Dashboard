"""Comprehensive tests for core/engine.py BaseStrategyEngine."""

import pandas as pd

from core.broker import BrokerInterface
from core.models import RiskConfig, StrategyConfig
from core.multi_strategy import MultiStrategyRuntime


class StubSignalProvider:
    """Minimal signal provider for engine-level tests."""

    def create_side_state(self):
        return None

    def update_state(self, side_state, row, prev_row):
        pass

    def generate_signal(self, side, side_state, row, prev_row):
        from core.models import Signal
        return Signal.NONE


class StubBroker(BrokerInterface):
    def get_ltp(self, symbol):
        return 100.0

    def place_stop_limit_order(self, symbol, side, quantity, trigger_price, limit_price):
        return "dry-stop"

    def place_market_order(self, symbol, side, quantity):
        return "dry-market"


def test_multi_strategy_runtime_processes_enabled_strategies_once_per_candle():
    runtime = MultiStrategyRuntime(
        StrategyConfig(),
        RiskConfig(),
        StubBroker(),
        enabled_keys=["hd", "ema21"],
    )
    row = pd.Series(
        {
            "datetime": pd.Timestamp("2026-09-07 09:21:00"),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000.0,
            "ema13": 100.0,
            "ema20": 99.5,
            "ema50": 99.0,
            "ema21": 99.8,
            "rsi3": 50.0,
        }
    )

    assert runtime.process_candle(row, None) == ["hd", "ema21"]
    assert runtime.process_candle(row, None) == []
    assert set(runtime.snapshots()) == {"hd", "ema21"}

    ema_engine = runtime.engines["ema21"]
    runtime.set_enabled(["hd"])
    runtime.set_enabled(["hd", "ema21"])
    assert runtime.engines["ema21"] is ema_engine
