"""Tests for replay option symbol fallback helpers in core.runner."""

from datetime import datetime
from types import SimpleNamespace

import pandas as pd

import core.runner as runner
from core.broker import ConsoleBroker
from core.engine import BaseStrategyEngine
from core.models import PendingEntry, Position, RiskConfig, Signal, StrategyConfig
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


class PositionBookBroker(ConsoleBroker):
    requires_position_reconciliation = True

    def __init__(self, positions, available=True):
        super().__init__()
        self.positions = positions
        self.position_book_available = available

    def get_position_book(self):
        return self.positions


class CancelTrackingBroker(ConsoleBroker):
    def __init__(self):
        super().__init__()
        self.cancelled = []

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return True


def _engine_with_position():
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(),
        risk=RiskConfig(),
        broker=ConsoleBroker(),
        signal_provider=EMA21SignalProvider(),
    )
    engine.state.ce.position = Position(
        option_symbol="NIFTY08SEP2623950CE",
        option_type="CE",
        quantity=130,
        initial_quantity=130,
        entry_price=130.75,
        entry_time=datetime(2026, 9, 4, 11, 26),
        option_stop_level=120.0,
        option_entry_trigger=130.0,
        option_risk_points=10.0,
    )
    return engine


def test_position_reconciliation_clears_local_position_when_broker_is_flat():
    engine = _engine_with_position()
    broker = PositionBookBroker([])

    runner._clear_positions_missing_from_broker([engine], broker)

    assert engine.state.ce.position is None


def test_position_reconciliation_preserves_local_position_when_book_unavailable():
    engine = _engine_with_position()
    broker = PositionBookBroker([], available=False)

    runner._clear_positions_missing_from_broker([engine], broker)

    assert engine.state.ce.position is not None


def test_startup_cancels_pending_order_on_any_later_ema21_failure():
    broker = CancelTrackingBroker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=EMA21SignalProvider(),
    )
    engine.state.pe.pending_entry = PendingEntry(
        signal=Signal.BUY_PE,
        created_at=datetime(2026, 9, 8, 12, 48),
        option_symbol="NIFTY15SEP2623700PE",
        quantity=130,
        option_trigger_level=128.70,
        option_stop_level=118.30,
        trigger_candle_high=128.70,
        trigger_candle_low=125.05,
        order_id="stale-order",
    )
    candles = pd.DataFrame(
        {
            "datetime": [
                datetime(2026, 9, 8, 12, 51),
                datetime(2026, 9, 8, 12, 54),
                datetime(2026, 9, 8, 12, 57),
            ],
            "close": [126.0, 122.0, 123.75],
            "ema21": [123.5, 123.0, 123.37],
        }
    )

    assert runner._cancel_stale_ema21_pending(engine, broker, "PE", candles)
    assert broker.cancelled == ["stale-order"]
    assert engine.state.pe.pending_entry is None


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


def test_restore_open_position_does_not_rebind_new_stop_to_stale_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class PositionBroker(ConsoleBroker):
        def __init__(self):
            super().__init__()
            self.place_count = 0
            self.open_order_reads = 0

        def get_position_book(self):
            return [{
                "symbol": "NIFTY01SEP2624250CE",
                "quantity": 65,
                "average_price": 100.0,
            }]

        def get_open_orders(self):
            self.open_order_reads += 1
            if self.open_order_reads == 2:
                return []
            return [{
                "symbol": "NIFTY01SEP2624250CE",
                "action": "SELL",
                "quantity": 130,
                "trigger_price": 90.0,
                "orderid": "STALE-SL",
            }]

        def cancel_order(self, order_id):
            return True

        def place_stop_limit_order(self, *args, **kwargs):
            self.place_count += 1
            return "NEW-SL"

    broker = PositionBroker()
    engine = BaseStrategyEngine(StrategyConfig(), RiskConfig(), broker, EMA21SignalProvider())
    engine.state.ce.option_symbol = "NIFTY01SEP2624250CE"

    runner._restore_open_positions(engine, broker, datetime(2026, 8, 27).date())
    runner._restore_open_positions(engine, broker, datetime(2026, 8, 27).date())

    assert broker.place_count == 1
    assert engine.state.ce.position is not None
    assert engine.state.ce.position.protective_stop_order_id == "NEW-SL"


def test_restore_open_position_parses_comma_separated_entry_alert(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "trade_alerts_NIFTY_20260902.csv").write_text(
        "timestamp,strategy,category,message\n"
        "2026-09-02 14:06:00,EMA21SignalProvider,ENTRY,"
        '"Entered CE NIFTY08SEP2623850CE @ 180.65, qty=130, trigger=180.35, '
        'SL=170.30, option_risk=10.05"\n',
        encoding="utf-8",
    )

    class PositionBroker(ConsoleBroker):
        def get_position_book(self):
            return [{
                "symbol": "NIFTY08SEP2623850CE",
                "quantity": 130,
                "average_price": 180.65,
            }]

        def get_open_orders(self):
            return []

    broker = PositionBroker()
    engine = BaseStrategyEngine(
        StrategyConfig(), RiskConfig(), broker, EMA21SignalProvider()
    )
    engine.state.ce.option_symbol = "NIFTY08SEP2623850CE"
    engine.state.pe.option_symbol = "NIFTY08SEP2623850PE"

    runner._restore_open_positions(engine, broker, datetime(2026, 9, 2).date())

    position = engine.state.ce.position
    assert position is not None
    assert position.quantity == 130
    assert position.entry_price == 180.65
    assert position.option_entry_trigger == 180.35
    assert position.option_stop_level == 170.30


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


def test_live_tick_poll_includes_pending_entry_symbol():
    class QuoteBroker(ConsoleBroker):
        def __init__(self):
            super().__init__(ltp_fallback=116.5)
            self.quoted = []

        def get_ltp(self, symbol):
            self.quoted.append(symbol)
            return super().get_ltp(symbol)

    side_state = SimpleNamespace(
        position=None,
        pending_entry=SimpleNamespace(option_symbol="NIFTY01SEP2624250PE"),
    )
    engine = SimpleNamespace(
        _side_state=lambda side: side_state,
        process_tick=lambda *args: (_ for _ in ()).throw(AssertionError("pending order cannot process risk ticks")),
    )
    live_runner = runner.LiveFeedRunner.__new__(runner.LiveFeedRunner)
    live_runner.engine = engine
    live_runner.broker = QuoteBroker()

    live_runner._poll_active_ticks()

    assert live_runner.broker.quoted == ["NIFTY01SEP2624250PE"]