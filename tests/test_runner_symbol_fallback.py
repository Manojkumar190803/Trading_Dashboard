"""Tests for replay option symbol fallback helpers in core.runner."""

from datetime import datetime

import pandas as pd

import core.runner as runner
from core.broker import ConsoleBroker
from core.engine import BaseStrategyEngine
from core.models import RiskConfig, StrategyConfig
from strategies.ema21 import EMA21SignalProvider


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": [datetime(2026, 8, 8, 9, 20)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000.0],
        }
    )


def test_parse_option_symbol():
    root, exp, strike, opt_type = runner._parse_option_symbol("NIFTY11AUG2624600CE")
    assert root == "NIFTY"
    assert exp == "11AUG26"
    assert strike == 24600
    assert opt_type == "CE"


def test_resolve_option_pair_history_falls_back_to_nearby_strike(monkeypatch):
    expected_strike = 24550

    def fake_fetch(_broker, symbol, _exchange, _interval, _start, _end):
        if str(expected_strike) in symbol:
            return _sample_df()
        raise RuntimeError(f"missing {symbol}")

    monkeypatch.setattr(runner, "_fetch_history_df", fake_fetch)

    ce_df, pe_df, ce_sym, pe_sym, off = runner._resolve_option_pair_history(
        broker=object(),  # type: ignore[arg-type]
        ce_symbol="NIFTY11AUG2624600CE",
        pe_symbol="NIFTY11AUG2624600PE",
        exchange="NFO",
        interval="3m",
        start_date="2026-08-01",
        end_date="2026-08-07",
        strike_step=50,
        max_steps=4,
    )

    assert not ce_df.empty
    assert not pe_df.empty
    assert ce_sym == "NIFTY11AUG2624550CE"
    assert pe_sym == "NIFTY11AUG2624550PE"
    assert off == -1


def test_restore_open_position_without_alert_recreates_protection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class PositionBroker(ConsoleBroker):
        def get_position_book(self):
            return [{
                "symbol": "NIFTY01SEP2624250CE",
                "quantity": 130,
                "average_price": 93.6,
            }]

        def get_open_orders(self):
            return []

    broker = PositionBroker()
    engine = BaseStrategyEngine(
        StrategyConfig(), RiskConfig(), broker, EMA21SignalProvider()
    )
    engine.state.ce.option_symbol = "NIFTY01SEP2624250CE"
    engine.state.pe.option_symbol = "NIFTY01SEP2624250PE"

    runner._restore_open_positions(engine, broker, datetime(2026, 8, 27).date())

    position = engine.state.ce.position
    assert position is not None
    assert position.quantity == 130
    assert position.entry_price == 93.6
    assert position.option_stop_level == 73.6


def test_restore_open_entry_order_after_restart(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class EntryOrderBroker(ConsoleBroker):
        def get_position_book(self):
            return []

        def get_open_orders(self):
            return [{
                "symbol": "NIFTY01SEP2624050CE",
                "action": "BUY",
                "quantity": 130,
                "price": 78.80,
                "trigger_price": 78.30,
                "orderid": "26083140021566",
            }]

    broker = EntryOrderBroker()
    engine = BaseStrategyEngine(
        StrategyConfig(), RiskConfig(), broker, EMA21SignalProvider()
    )
    engine.state.ce.option_symbol = "NIFTY01SEP2624050CE"
    engine.state.pe.option_symbol = "NIFTY01SEP2624050PE"
    engine.state.ce.order_submission_uncertain = True

    runner._restore_open_positions(engine, broker, datetime(2026, 8, 31).date())

    pending = engine.state.ce.pending_entry
    assert pending is not None
    assert pending.order_id == "26083140021566"
    assert pending.quantity == 130
    assert pending.option_trigger_level == 78.30
    assert engine.state.ce.order_submission_uncertain is False


def test_restore_uncertain_entry_preserves_original_ema21_stop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class UncertainEntryBroker(ConsoleBroker):
        def __init__(self):
            super().__init__()
            self.cancelled = []

        def get_position_book(self):
            return [{
                "symbol": "NIFTY08SEP2624050PE",
                "quantity": 130,
                "average_price": 85.0,
            }]

        def get_open_orders(self):
            return [{
                "symbol": "NIFTY08SEP2624050PE",
                "action": "SELL",
                "quantity": 130,
                "price": 64.0,
                "trigger_price": 65.0,
                "orderid": "BAD-SL",
            }]

        def cancel_order(self, order_id):
            self.cancelled.append(order_id)
            return True

    broker = UncertainEntryBroker()
    engine = BaseStrategyEngine(
        StrategyConfig(), RiskConfig(), broker, EMA21SignalProvider()
    )
    side_state = engine.state.pe
    side_state.option_symbol = "NIFTY08SEP2624050PE"
    side_state.order_submission_uncertain = True
    side_state.first_red_high = 84.80  # type: ignore[attr-defined]
    side_state.setup_candle_low = 77.75  # type: ignore[attr-defined]

    runner._restore_open_positions(engine, broker, datetime(2026, 9, 1).date())

    assert side_state.position is not None
    assert side_state.position.entry_price == 85.0
    assert side_state.position.option_entry_trigger == 84.80
    assert side_state.position.option_stop_level == 77.75
    assert broker.cancelled == ["BAD-SL"]