"""Focused tests for BaseStrategyEngine tick and square-off behavior."""

from datetime import date, datetime

import pandas as pd

from core.broker import ConsoleBroker
from core.engine import BaseStrategyEngine
from core.models import BaseSideState, PendingEntry, Position, RiskConfig, Signal, StrategyConfig
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


class TimeoutBroker(ConsoleBroker):
    def place_stop_limit_order(self, *args, **kwargs):
        raise TimeoutError("broker read timeout")


class RecordingBroker(ConsoleBroker):
    def __init__(self):
        super().__init__()
        self.stop_orders = []
        self.modified_stop_orders = []
        self.cancelled_orders = []

    def cancel_order(self, order_id):
        self.cancelled_orders.append(order_id)
        return True

    def place_stop_limit_order(self, symbol, side, quantity, trigger_price, limit_price):
        self.stop_orders.append((symbol, side, quantity, trigger_price, limit_price))
        return f"OID-{len(self.stop_orders)}"

    def modify_stop_limit_order(self, order_id, symbol, side, quantity, trigger_price, limit_price):
        self.modified_stop_orders.append(
            (order_id, symbol, side, quantity, trigger_price, limit_price)
        )
        return True


class ExistingStopBroker(RecordingBroker):
    requires_position_reconciliation = True

    def __init__(self):
        super().__init__()
        self.open_orders = [{
            "symbol": "NIFTY01SEP2624250PE",
            "action": "SELL",
            "quantity": 130,
            "trigger_price": 90.0,
            "orderid": "EXISTING-SL",
        }]

    def get_open_orders(self):
        return self.open_orders


class FailedModifyBroker(RecordingBroker):
    def modify_stop_limit_order(self, *args, **kwargs):
        return False


class StaleCancelBroker(ExistingStopBroker):
    def cancel_order(self, order_id):
        self.cancelled_orders.append(order_id)
        return True


class ReconciledBroker(RecordingBroker):
    requires_position_reconciliation = True

    def __init__(self, quantity):
        super().__init__()
        self.quantity = quantity
        self.market_orders = []

    def get_position_book(self):
        return [{"symbol": "NIFTY08AUG2625000PE", "quantity": self.quantity}]

    def place_market_order(self, symbol, side, quantity):
        self.market_orders.append((symbol, side, quantity))
        return "MKT-1"


class EMA21StubSignalProvider(StubSignalProvider):
    strategy_key = "ema21"


def _make_engine() -> BaseStrategyEngine:
    return BaseStrategyEngine(
        cfg=StrategyConfig(option_lot_size=65, pending_entry_expiry_candles=3),
        risk=RiskConfig(max_sl_per_day=3),
        broker=ConsoleBroker(ltp_fallback=100.0),
        signal_provider=StubSignalProvider(),
    )


def _row(ts: datetime, high: float = 100.0, low: float = 95.0) -> pd.Series:
    return pd.Series(
        {
            "datetime": ts,
            "open": 97.0,
            "high": high,
            "low": low,
            "close": 98.0,
            "rsi3": 40.0,
            "ema13": 98.0,
            "ema20": 97.0,
            "ema50": 96.0,
            "vwap": 97.5,
            "volume": 1000.0,
        }
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


def test_uncertain_entry_submission_blocks_duplicate_order_attempt():
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(option_lot_size=65),
        risk=RiskConfig(max_sl_per_day=3),
        broker=TimeoutBroker(),
        signal_provider=EMA21StubSignalProvider(),
    )
    side_state = engine.state.ce
    side_state.option_symbol = "NIFTY01SEP2624250PE"
    side_state.first_red_high = 88.0  # type: ignore[attr-defined]
    row = _row(datetime(2026, 8, 27, 12, 6), high=87.8, low=86.8)

    engine.place_pending_entry("CE", side_state, row["datetime"], row)
    engine.place_pending_entry("CE", side_state, row["datetime"], row)

    assert side_state.order_submission_uncertain is True
    assert side_state.pending_entry is None
    assert sum("submission uncertain" in alert.message for alert in engine.alerts) == 1


def test_live_entry_places_separate_protective_sell_stop():
    broker = RecordingBroker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(option_tick_size=0.05, stop_buffer_points=1.0),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=EMA21StubSignalProvider(),
    )
    position = Position(
        option_symbol="NIFTY01SEP2624250PE",
        option_type="PE",
        quantity=130,
        initial_quantity=130,
        entry_price=94.05,
        entry_time=datetime(2026, 8, 27, 12, 6),
        option_stop_level=90.0,
        option_entry_trigger=94.0,
        option_risk_points=4.0,
    )

    engine._place_protective_stop("PE", position, position.entry_time)

    assert position.protective_stop_order_id == "OID-1"
    assert broker.stop_orders == [
        ("NIFTY01SEP2624250PE", "SELL", 130, 90.0, 89.0)
    ]
    assert any(alert.category == "PROTECTIVE_SL" for alert in engine.alerts)


def test_protective_stop_reuses_existing_matching_order():
    broker = ExistingStopBroker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(option_tick_size=0.05, stop_buffer_points=1.0),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=EMA21StubSignalProvider(),
    )
    position = Position(
        option_symbol="NIFTY01SEP2624250PE",
        option_type="PE",
        quantity=130,
        initial_quantity=130,
        entry_price=94.05,
        entry_time=datetime(2026, 8, 27, 12, 6),
        option_stop_level=90.0,
        option_entry_trigger=94.0,
        option_risk_points=4.0,
    )

    engine._place_protective_stop("PE", position, position.entry_time)

    assert position.protective_stop_order_id == "EXISTING-SL"
    assert broker.stop_orders == []


def test_trailing_modifies_existing_protective_stop_without_placing_new_order():
    broker = RecordingBroker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(option_tick_size=0.05, stop_buffer_points=1.0),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=EMA21StubSignalProvider(),
    )
    position = Position(
        option_symbol="NIFTY01SEP2624250PE",
        option_type="PE",
        quantity=130,
        initial_quantity=130,
        entry_price=100.0,
        entry_time=datetime(2026, 8, 27, 12, 6),
        option_stop_level=90.0,
        option_entry_trigger=100.0,
        option_risk_points=10.0,
        protective_stop_order_id="OPEN-SL-1",
    )

    position.option_stop_level = 105.0
    engine._refresh_protective_stop("PE", position, position.entry_time)

    assert broker.modified_stop_orders == [
        ("OPEN-SL-1", "NIFTY01SEP2624250PE", "SELL", 130, 105.0, 104.0)
    ]
    assert broker.stop_orders == []
    assert broker.cancelled_orders == []


def test_trailing_keeps_existing_order_id_when_modify_fails():
    broker = FailedModifyBroker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=EMA21StubSignalProvider(),
    )
    position = Position(
        option_symbol="NIFTY01SEP2624250PE",
        option_type="PE",
        quantity=130,
        initial_quantity=130,
        entry_price=100.0,
        entry_time=datetime(2026, 8, 27, 12, 6),
        option_stop_level=90.0,
        option_entry_trigger=100.0,
        option_risk_points=10.0,
        protective_stop_order_id="OPEN-SL-1",
    )

    engine._refresh_protective_stop("PE", position, position.entry_time)

    assert position.protective_stop_order_id == "OPEN-SL-1"
    assert broker.stop_orders == []
    assert any("existing SL was not replaced" in alert.message for alert in engine.alerts)


def test_trailing_status_reports_next_target_after_partial_booking():
    broker = RecordingBroker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=EMA21StubSignalProvider(),
    )
    position = Position(
        option_symbol="NIFTY01SEP2624250PE",
        option_type="PE",
        quantity=130,
        initial_quantity=130,
        entry_price=100.0,
        entry_time=datetime(2026, 8, 27, 12, 6),
        option_stop_level=90.0,
        option_entry_trigger=100.0,
        option_risk_points=10.0,
        protective_stop_order_id="OPEN-SL-1",
    )
    engine.state.pe.position = position

    engine.process_tick("PE", 120.0, datetime(2026, 8, 27, 12, 10))

    assert position.quantity == 65
    assert position.next_target_rr == 2.5
    assert "looking for 2.5R" in position.progress_status

    engine.process_tick("PE", 125.0, datetime(2026, 8, 27, 12, 11))

    assert position.next_target_rr == 3.0
    assert "2.5R reached" in position.progress_status
    assert "SL shifted to 110.00" in position.progress_status


def test_protective_stop_waits_when_cancelled_order_is_still_open():
    broker = StaleCancelBroker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(option_tick_size=0.05, stop_buffer_points=1.0),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=EMA21StubSignalProvider(),
    )
    position = Position(
        option_symbol="NIFTY01SEP2624250PE",
        option_type="PE",
        quantity=130,
        initial_quantity=130,
        entry_price=94.05,
        entry_time=datetime(2026, 8, 27, 12, 6),
        option_stop_level=89.0,
        option_entry_trigger=94.0,
        option_risk_points=5.0,
    )

    engine._place_protective_stop("PE", position, position.entry_time)

    assert broker.cancelled_orders == ["EXISTING-SL"]
    assert broker.stop_orders == []
    assert position.protective_stop_order_id is None


def test_live_exit_is_blocked_when_broker_has_short_position():
    broker = ReconciledBroker(-130)
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=StubSignalProvider(),
    )
    _attach_position(engine, "PE")

    engine._exit_position(
        engine.state.pe,
        datetime(2026, 8, 8, 11, 0),
        130,
        "test exit",
    )

    assert broker.market_orders == []
    assert engine.state.pe.position is not None
    assert any("exit blocked" in alert.message for alert in engine.alerts)


def test_live_entry_fill_is_blocked_when_broker_reports_short_position():
    broker = ReconciledBroker(-130)
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=EMA21StubSignalProvider(),
    )
    side_state = engine.state.pe
    side_state.pending_entry = PendingEntry(
        signal=Signal.BUY_PE,
        created_at=datetime(2026, 8, 8, 10, 0),
        option_symbol="NIFTY08AUG2625000PE",
        quantity=130,
        option_trigger_level=116.25,
        option_stop_level=108.85,
        trigger_candle_high=116.25,
        trigger_candle_low=110.0,
        order_id="OPEN-1",
    )

    engine.try_fill_pending_entry(
        "PE",
        side_state,
        datetime(2026, 8, 8, 10, 3),
        _row(datetime(2026, 8, 8, 10, 3), high=120.0, low=110.0),
    )

    assert side_state.position is None
    assert side_state.order_submission_uncertain is True
    assert any("fill blocked" in alert.message for alert in engine.alerts)


def test_hard_sl_count_is_shared_between_strategy_engines(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    trade_day = datetime(2026, 8, 8, 10, 0)
    first = _make_engine()
    second = _make_engine()
    first.state.trading_day = trade_day.date()
    second.state.trading_day = trade_day.date()
    _attach_position(first, "CE")

    first._exit_position(first.state.ce, trade_day, 130, "hard stop", is_hard_sl=True)
    second._sync_shared_sl_count(trade_day.date())

    assert first.state.sl_hits_today == 1
    assert second.state.sl_hits_today == 1
    assert (tmp_path / "logs" / "sl_hits_20260808.json").exists()


def test_candle_low_hits_trailing_stop_after_same_candle_trail_update():
    engine = _make_engine()
    side_state = engine.state.ce
    side_state.position = Position(
        option_symbol="NIFTY01SEP2624250PE",
        option_type="PE",
        quantity=65,
        initial_quantity=65,
        entry_price=80.0,
        entry_time=datetime(2026, 8, 27, 12, 0),
        option_stop_level=70.0,
        option_entry_trigger=80.0,
        option_risk_points=10.0,
        breakeven_armed=True,
        t1_done=True,
        trailing_sl_level=80.0,
        highest_rr_step=1.5,
    )
    row = _row(datetime(2026, 8, 27, 12, 6), high=110.0, low=84.0)

    engine.monitor_open_position(side_state, row)

    assert side_state.position is None
    assert any("candle low" in alert.message for alert in engine.alerts)


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


def test_process_tick_modifies_sl_once_for_high_rr_tick():
    broker = RecordingBroker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(option_lot_size=65),
        risk=RiskConfig(max_sl_per_day=3),
        broker=broker,
        signal_provider=EMA21StubSignalProvider(),
    )
    _attach_position(engine, "CE")
    engine.state.ce.position.protective_stop_order_id = "EXISTING-SL"

    engine.process_tick("CE", 125.0, datetime(2026, 8, 8, 10, 5))
    assert len(broker.modified_stop_orders) == 1

    engine.process_tick("CE", 125.0, datetime(2026, 8, 8, 10, 6))
    assert len(broker.modified_stop_orders) == 1


def test_force_square_off_side_clears_pending_and_position():
    engine = _make_engine()
    _attach_position(engine, "PE")
    ss = engine.state.pe
    ss.pending_entry = object()  # type: ignore[assignment]
    engine.force_square_off_side(ss, datetime(2026, 8, 8, 15, 16))
    assert ss.pending_entry is None
    assert ss.position is None


def test_pending_entry_expires_after_3_candles():
    engine = _make_engine()
    engine.state.trading_day = datetime(2026, 8, 8).date()
    ss = engine.state.ce
    ss.option_symbol = "NIFTY08AUG2625000CE"
    ss.pending_entry = PendingEntry(
        signal=Signal.BUY_CE,
        created_at=datetime(2026, 8, 8, 10, 0),
        option_symbol=ss.option_symbol,
        quantity=65,
        option_trigger_level=120.0,
        option_stop_level=90.0,
        trigger_candle_high=119.0,
        trigger_candle_low=95.0,
    )

    # 4 candles elapsed (12 minutes on 3m TF) -> should expire.
    row = _row(datetime(2026, 8, 8, 10, 12), high=110.0, low=95.0)
    engine.try_fill_pending_entry("CE", row=row, side_state=ss, ts=row["datetime"])

    assert ss.pending_entry is None
    assert any("expired after" in a.message for a in engine.alerts)


def test_live_pending_entry_cancellation_cancels_broker_order():
    broker = RecordingBroker()
    engine = _make_engine()
    engine.broker = broker
    engine.state.trading_day = datetime(2026, 8, 8).date()
    side_state = engine.state.ce
    side_state.pending_entry = PendingEntry(
        signal=Signal.BUY_CE,
        created_at=datetime(2026, 8, 8, 10, 0),
        option_symbol="NIFTY08AUG2625000CE",
        quantity=65,
        option_trigger_level=120.0,
        option_stop_level=90.0,
        trigger_candle_high=119.0,
        trigger_candle_low=95.0,
        order_id="OPEN-1",
    )

    row = _row(datetime(2026, 8, 8, 10, 12), high=110.0, low=95.0)
    engine.try_fill_pending_entry("CE", row=row, side_state=side_state, ts=row["datetime"])

    assert broker.cancelled_orders == ["OPEN-1"]
    assert side_state.pending_entry is None


def test_pending_entry_still_valid_at_3rd_candle():
    engine = _make_engine()
    engine.state.trading_day = datetime(2026, 8, 8).date()
    ss = engine.state.ce
    ss.option_symbol = "NIFTY08AUG2625000CE"
    ss.pending_entry = PendingEntry(
        signal=Signal.BUY_CE,
        created_at=datetime(2026, 8, 8, 10, 0),
        option_symbol=ss.option_symbol,
        quantity=65,
        option_trigger_level=120.0,
        option_stop_level=90.0,
        trigger_candle_high=119.0,
        trigger_candle_low=95.0,
    )

    # Exactly 3 candles elapsed (9 minutes) -> still allowed.
    row = _row(datetime(2026, 8, 8, 10, 9), high=110.0, low=95.0)
    engine.process_option_candle("CE", row, None)

    assert ss.pending_entry is not None


def test_lock_atm_uses_expiry_override_date():
    engine = _make_engine()
    lock_ts = datetime(2026, 8, 8, 9, 20)
    # Override to a known monthly code date.
    engine.lock_atm_for_day(lock_ts, spot_price=57746.45, expiry_day_override=date(2026, 8, 25))

    assert engine.state.atm_locked is True
    assert engine.state.ce_symbol is not None
    assert engine.state.pe_symbol is not None
    assert "25AUG26" in engine.state.ce_symbol
    assert "25AUG26" in engine.state.pe_symbol