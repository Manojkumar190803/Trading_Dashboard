"""Focused tests for BaseStrategyEngine tick and square-off behavior."""

import os
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

from core.broker import ConsoleBroker, HistoricalReplayBroker
from core.engine import BaseStrategyEngine
from core.models import BaseSideState, PendingEntry, Position, RiskConfig, Signal, StrategyConfig
import run_strategy
import strategy_daemon
from strategies.base import SignalProvider
from strategies.hd import HDSignalProvider


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
        signal_provider=StubSignalProvider(),
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
    assert Path(os.environ["SHARED_SL_COUNT_FILE"]).exists()


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
    ss.pending_entry = PendingEntry(
        signal=Signal.BUY_PE,
        created_at=datetime(2026, 8, 8, 15, 0),
        option_symbol="NIFTY08AUG2625000PE",
        quantity=65,
        option_trigger_level=100.0,
        option_stop_level=90.0,
        trigger_candle_high=100.0,
        trigger_candle_low=90.0,
    )
    engine.force_square_off_side(ss, datetime(2026, 8, 8, 15, 16))
    assert ss.pending_entry is None
    assert ss.position is None


def test_day_transition_resets_daily_entry_count():
    engine = _make_engine()
    engine.total_entries = 1

    engine.reset_for_new_day(datetime(2026, 8, 11).date())

    assert engine.total_entries == 0


def test_replay_ignores_shared_live_sl_count(tmp_path, monkeypatch):
    shared_count = tmp_path / "sl_hits.json"
    shared_count.write_text('{"count": 3}', encoding="utf-8")
    monkeypatch.setenv("SHARED_SL_COUNT_FILE", str(shared_count))
    engine = BaseStrategyEngine(
        StrategyConfig(),
        RiskConfig(max_sl_per_day=3),
        HistoricalReplayBroker(),
        StubSignalProvider(),
    )
    engine.state.trading_day = datetime(2026, 9, 11).date()

    engine._sync_shared_sl_count(engine.state.trading_day)

    assert engine.state.sl_hits_today == 0


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


def test_hd_contract_lock_selects_exactly_one_strike_itm_per_side():
    class ChainBroker(ConsoleBroker):
        def fetch_option_chain(self, underlying, exchange, expiry_date):
            assert (underlying, exchange, expiry_date) == ("NIFTY", "NSE_INDEX", "25AUG26")
            return {
                "status": "success",
                "chain": [
                    {"strike": 24900, "ce": {"symbol": "CE-24900", "ltp": 150}},
                    {"strike": 24950, "ce": {"symbol": "CE-24950", "ltp": 145}},
                    {"strike": 25000, "ce": {"symbol": "CE-25000", "ltp": 150}, "pe": {"symbol": "PE-25000", "ltp": 150}},
                    {"strike": 25050, "ce": {"symbol": "CE-25050", "ltp": 150}, "pe": {"symbol": "PE-25050", "ltp": 155}},
                    {"strike": 25100, "pe": {"symbol": "PE-25100", "ltp": 150}},
                ],
            }

    engine = BaseStrategyEngine(
        cfg=StrategyConfig(premium_min_price=120, premium_max_price=180),
        risk=RiskConfig(),
        broker=ChainBroker(),
        signal_provider=HDSignalProvider(),
    )

    engine.lock_atm_for_day(
        datetime(2026, 8, 8, 9, 20),
        spot_price=25020,
        expiry_day_override=date(2026, 8, 25),
    )

    assert engine.state.ce_symbol == "CE-24950"
    assert engine.state.pe_symbol == "PE-25050"
    assert engine.state.atm_locked is True


def test_hd_contract_lock_rejects_chain_without_in_range_contracts():
    class ChainBroker(ConsoleBroker):
        def fetch_option_chain(self, underlying, exchange, expiry_date):
            return {
                "status": "success",
                "data": {"chain": [{"strike": 25000, "ce": {"symbol": "CE", "ltp": 200}}]},
            }

    engine = BaseStrategyEngine(
        cfg=StrategyConfig(premium_min_price=120, premium_max_price=180),
        risk=RiskConfig(),
        broker=ChainBroker(),
        signal_provider=HDSignalProvider(),
    )

    engine.lock_atm_for_day(
        datetime(2026, 8, 8, 9, 20),
        spot_price=25020,
        expiry_day_override=date(2026, 8, 25),
    )

    assert engine.state.atm_locked is False
    assert engine.state.ce_symbol is None
    assert engine.state.pe_symbol is None


def test_hd_contract_lock_keeps_eligible_side_when_other_side_has_no_match():
    class ChainBroker(ConsoleBroker):
        def fetch_option_chain(self, underlying, exchange, expiry_date):
            return {
                "status": "success",
                "data": {
                    "chain": [
                        {"strike": 24950, "ce": {"symbol": "CE-24950", "ltp": 150}},
                        {"strike": 25050, "pe": {"symbol": "PE-25050", "ltp": 200}},
                    ]
                },
            }

    engine = BaseStrategyEngine(
        cfg=StrategyConfig(premium_min_price=120, premium_max_price=180),
        risk=RiskConfig(),
        broker=ChainBroker(),
        signal_provider=HDSignalProvider(),
    )

    engine.lock_atm_for_day(
        datetime(2026, 8, 8, 9, 20),
        spot_price=25020,
        expiry_day_override=date(2026, 8, 25),
    )

    assert engine.state.atm_locked is True
    assert engine.state.ce_symbol == "CE-24950"
    assert engine.state.pe_symbol is None


def test_hd_contract_lock_does_not_fall_back_from_missing_one_step_itm_strike():
    class ChainBroker(ConsoleBroker):
        def fetch_option_chain(self, underlying, exchange, expiry_date):
            return {
                "status": "success",
                "data": {
                    "chain": [
                        {"strike": 25000, "ce": {"symbol": "ATM-CE", "ltp": 150}},
                        {"strike": 25100, "ce": {"symbol": "OTM-CE", "ltp": 150}},
                        {"strike": 25050, "pe": {"symbol": "ITM-PE", "ltp": 150}},
                    ]
                },
            }

    engine = BaseStrategyEngine(
        cfg=StrategyConfig(premium_min_price=120, premium_max_price=180),
        risk=RiskConfig(),
        broker=ChainBroker(),
        signal_provider=HDSignalProvider(),
    )

    engine.lock_atm_for_day(
        datetime(2026, 8, 8, 9, 20),
        spot_price=25020,
        expiry_day_override=date(2026, 8, 25),
    )

    assert engine.state.atm_locked is True
    assert engine.state.ce_symbol is None
    assert engine.state.pe_symbol == "ITM-PE"


def test_hd_trailing_uses_global_rr_steps_without_partial_exit():
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(option_lot_size=65, t1_rr=1.25, trailing_step_rr=0.5),
        risk=RiskConfig(),
        broker=RecordingBroker(),
        signal_provider=HDSignalProvider(),
    )
    side_state = engine.state.ce
    side_state.position = Position(
        option_symbol="NIFTY-CE",
        option_type="CE",
        quantity=130,
        initial_quantity=130,
        entry_price=100.0,
        entry_time=datetime(2026, 8, 8, 10, 0),
        option_stop_level=90.0,
        option_entry_trigger=99.0,
        option_risk_points=10.0,
    )

    engine.process_tick("CE", 112.5, datetime(2026, 8, 8, 10, 1))
    assert side_state.position.option_stop_level == 100.0
    assert side_state.position.highest_rr_step == 1.25

    engine.process_tick("CE", 117.5, datetime(2026, 8, 8, 10, 2))
    assert side_state.position.option_stop_level == 105.0
    assert side_state.position.highest_rr_step == 1.75

    engine.process_tick("CE", 120.0, datetime(2026, 8, 8, 10, 3))
    assert side_state.position.quantity == 130
    assert side_state.position.option_stop_level == 105.0


def test_hd_trailing_stop_hit_does_not_count_as_hard_sl():
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(option_lot_size=65, t1_rr=1.25, trailing_step_rr=0.5),
        risk=RiskConfig(),
        broker=RecordingBroker(),
        signal_provider=HDSignalProvider(),
    )
    side_state = engine.state.ce
    side_state.position = Position(
        option_symbol="NIFTY-CE",
        option_type="CE",
        quantity=65,
        initial_quantity=65,
        entry_price=100.0,
        entry_time=datetime(2026, 8, 8, 10, 0),
        option_stop_level=100.0,
        option_entry_trigger=99.0,
        option_risk_points=10.0,
        breakeven_armed=True,
        t1_done=True,
        trailing_sl_level=100.0,
        highest_rr_step=1.25,
    )

    engine.process_tick("CE", 99.0, datetime(2026, 8, 8, 10, 1))

    assert side_state.position is None
    assert engine.state.sl_hits_today == 0
    assert engine.total_hard_sl_hits == 0


def test_hd_pending_order_survives_cutoff_and_generic_expiry():
    broker = RecordingBroker()
    broker.is_replay = True
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(entry_cutoff=time(14, 40), pending_entry_expiry_candles=3),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=HDSignalProvider(),
    )
    side_state = engine.state.ce
    side_state.option_symbol = "NIFTY-CE"
    side_state.pending_entry = PendingEntry(
        signal=Signal.BUY_CE,
        created_at=datetime(2026, 8, 8, 14, 0),
        option_symbol="NIFTY-CE",
        quantity=65,
        option_trigger_level=120.0,
        option_stop_level=90.0,
        trigger_candle_high=119.0,
        trigger_candle_low=95.0,
    )

    engine.try_fill_pending_entry(
        "CE",
        side_state,
        datetime(2026, 8, 8, 14, 45),
        _row(datetime(2026, 8, 8, 14, 45), high=110.0, low=95.0),
    )

    assert side_state.pending_entry is not None


def test_hd_pending_order_cancels_when_stop_is_breached():
    broker = RecordingBroker()
    broker.is_replay = True
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=HDSignalProvider(),
    )
    engine.reset_for_new_day(date(2026, 8, 8))
    side_state = engine.state.ce
    side_state.pending_entry = PendingEntry(
        signal=Signal.BUY_CE,
        created_at=datetime(2026, 8, 8, 10, 0),
        option_symbol="NIFTY-CE",
        quantity=65,
        option_trigger_level=120.0,
        option_stop_level=90.0,
        trigger_candle_high=119.0,
        trigger_candle_low=95.0,
    )

    engine.try_fill_pending_entry(
        "CE",
        side_state,
        datetime(2026, 8, 8, 10, 3),
        _row(datetime(2026, 8, 8, 10, 3), high=110.0, low=89.0),
    )

    assert side_state.pending_entry is None


def test_hd_dashboard_settings_reach_strategy_config(monkeypatch):
    environment = strategy_daemon._strategy_environment(
        {
            "strategy": "HD",
            "premiumMinPrice": 125,
            "premiumMaxPrice": 175,
            "maxInitialRiskPoints": 18,
            "lotSizeAdjustment": 3.0,
            "monitoringStartTime": "09:30",
            "monitoringEndTime": "15:00",
            "entryCutoffTime": "14:45",
        },
        {"breakEvenRR": 1.25, "trailStepRR": 0.5},
    )
    for name, value in environment.items():
        if name.startswith("HD_"):
            monkeypatch.setenv(name, value)

    cfg = StrategyConfig()
    run_strategy._apply_hd_policy(cfg)

    assert cfg.premium_min_price == 125
    assert cfg.premium_max_price == 175
    assert cfg.max_option_risk_points == 18
    assert cfg.full_size_lots == 3
    assert cfg.market_open.strftime("%H:%M") == "09:30"
    assert cfg.market_close.strftime("%H:%M") == "15:00"
    assert cfg.force_square_off.strftime("%H:%M") == "15:00"
    assert cfg.atm_lock_time.strftime("%H:%M") == "09:30"
    assert cfg.entry_cutoff.strftime("%H:%M") == "14:45"
    assert cfg.t1_rr == 1.25
    assert cfg.trailing_step_rr == 0.5


def test_hd_dashboard_values_override_inherited_runtime_defaults(monkeypatch):
    monkeypatch.setenv("HD_MONITORING_START_TIME", "10:00")
    monkeypatch.setenv("HD_MAX_OPTION_RISK_POINTS", "7")

    environment = strategy_daemon._strategy_environment(
        {"strategy": "HD"},
        {"maxInitialRiskPoints": 15},
    )

    assert environment["HD_MONITORING_START_TIME"] == "09:15"
    assert environment["HD_MONITORING_END_TIME"] == "15:30"
    assert environment["HD_ENTRY_CUTOFF"] == "14:40"
    assert environment["HD_MAX_OPTION_RISK_POINTS"] == "20"
    assert environment["HD_FULL_SIZE_LOTS"] == "1"
    assert environment["HD_PREMIUM_MIN_PRICE"] == "120"
    assert environment["HD_PREMIUM_MAX_PRICE"] == "180"


def test_hd_entry_order_uses_dashboard_risk_and_lot_settings():
    broker = RecordingBroker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(
            option_lot_size=65,
            full_size_lots=2,
            max_option_risk_points=12.0,
        ),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=HDSignalProvider(),
    )
    engine.reset_for_new_day(date(2026, 8, 8))
    side_state = engine.state.ce
    side_state.option_symbol = "NIFTY-CE"
    side_state.alert_ready = True
    side_state.alert_candle_low = 100.0
    row = pd.Series({
        "datetime": datetime(2026, 8, 8, 10, 0),
        "open": 105.0,
        "high": 110.0,
        "low": 100.0,
        "close": 109.5,
    })

    engine.place_pending_entry("CE", side_state, row["datetime"], row)

    assert broker.stop_orders == [("NIFTY-CE", "BUY", 130, 110.05, 110.05)]
    assert side_state.pending_entry is not None

    rejected_broker = RecordingBroker()
    rejected_engine = BaseStrategyEngine(
        cfg=StrategyConfig(
            option_lot_size=65,
            full_size_lots=2,
            max_option_risk_points=10.0,
        ),
        risk=RiskConfig(),
        broker=rejected_broker,
        signal_provider=HDSignalProvider(),
    )
    rejected_engine.reset_for_new_day(date(2026, 8, 8))
    rejected_state = rejected_engine.state.ce
    rejected_state.option_symbol = "NIFTY-CE"
    rejected_state.alert_ready = True
    rejected_state.alert_candle_low = 100.0

    rejected_engine.place_pending_entry("CE", rejected_state, row["datetime"], row)

    assert rejected_broker.stop_orders == []
    assert rejected_state.pending_entry is None


def test_hd_dashboard_monitoring_start_change_restarts_instrument():
    instrument = {
        "strategy": "HD",
        "brokerSymbol": "NIFTY",
        "monitoringStartTime": "09:15",
        "monitoringEndTime": "15:00",
    }
    changed = {**instrument, "monitoringStartTime": "09:30"}

    assert strategy_daemon._runtime_signature(instrument, {}) != (
        strategy_daemon._runtime_signature(changed, {})
    )


def test_hd_broker_fill_sets_actual_entry_and_initial_risk():
    class FilledBroker(RecordingBroker):
        requires_position_reconciliation = True

        def get_order_status(self, order_id):
            return {"order_status": "complete", "average_price": 102.0}

        def get_position_book(self):
            return [{"symbol": "NIFTY-CE", "quantity": 65}]

    engine = BaseStrategyEngine(
        cfg=StrategyConfig(),
        risk=RiskConfig(),
        broker=FilledBroker(),
        signal_provider=HDSignalProvider(),
    )
    engine.reset_for_new_day(date(2026, 8, 8))
    side_state = engine.state.ce
    side_state.option_symbol = "NIFTY-CE"
    side_state.pending_entry = PendingEntry(
        signal=Signal.BUY_CE,
        created_at=datetime(2026, 8, 8, 10, 0),
        option_symbol="NIFTY-CE",
        quantity=65,
        option_trigger_level=101.0,
        option_stop_level=90.0,
        trigger_candle_high=100.95,
        trigger_candle_low=90.0,
        order_id="ENTRY-1",
    )

    engine.try_fill_pending_entry(
        "CE",
        side_state,
        datetime(2026, 8, 8, 10, 3),
        _row(datetime(2026, 8, 8, 10, 3), high=101.0, low=100.0),
    )

    assert side_state.position.entry_price == 102.0
    assert side_state.position.option_risk_points == 12.0
    assert side_state.pending_entry is None


def test_hd_broker_fill_over_risk_limit_is_exited():
    class FilledBroker(RecordingBroker):
        requires_position_reconciliation = True

        def __init__(self):
            super().__init__()
            self.market_orders = []

        def get_order_status(self, order_id):
            return {"order_status": "complete", "average_price": 111.0}

        def get_position_book(self):
            return [{"symbol": "NIFTY-CE", "quantity": 65}]

        def place_market_order(self, symbol, side, quantity):
            self.market_orders.append((symbol, side, quantity))
            return "EXIT-1"

    broker = FilledBroker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(max_option_risk_points=20.0),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=HDSignalProvider(),
    )
    engine.reset_for_new_day(date(2026, 8, 8))
    side_state = engine.state.ce
    side_state.option_symbol = "NIFTY-CE"
    side_state.pending_entry = PendingEntry(
        signal=Signal.BUY_CE,
        created_at=datetime(2026, 8, 8, 10, 0),
        option_symbol="NIFTY-CE",
        quantity=65,
        option_trigger_level=101.0,
        option_stop_level=90.0,
        trigger_candle_high=100.95,
        trigger_candle_low=90.0,
        order_id="ENTRY-1",
    )

    engine.try_fill_pending_entry(
        "CE",
        side_state,
        datetime(2026, 8, 8, 10, 3),
        _row(datetime(2026, 8, 8, 10, 3), high=101.0, low=100.0),
    )

    assert side_state.position is None
    assert side_state.pending_entry is None
    assert broker.market_orders == [("NIFTY-CE", "SELL", 65)]