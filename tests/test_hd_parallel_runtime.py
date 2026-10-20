import json
from datetime import date, datetime

import core.engine as engine_module
import core.runner as runner_module
import strategy_daemon
from core.broker import ConsoleBroker
from core.engine import BaseStrategyEngine
from core.models import Position, RiskConfig, StrategyConfig
from strategies.ema21 import EMA21SignalProvider
from strategies.hd import HDSignalProvider


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


def test_hd_daemon_reads_dashboard_api_and_global_trailing_config(monkeypatch, tmp_path):
    config_file = tmp_path / "instruments_config.json"
    config_file.write_text(json.dumps({
        "trailingStopsConfig": {"breakEvenRR": 1.5, "trailStepRR": 0.75},
        "instruments": [],
    }), encoding="utf-8")
    monkeypatch.setattr(strategy_daemon, "CONFIG_FILE", config_file)
    monkeypatch.setenv("STRATEGY_DASHBOARD_API_URL", "http://dashboard/api/instruments")
    monkeypatch.setattr(
        strategy_daemon,
        "urlopen",
        lambda url, timeout: _Response({
            "count": 1,
            "instruments": [{"id": 42, "strategy": "HD", "status": "ACTIVE"}],
        }),
    )

    config = strategy_daemon._load_config()

    assert config is not None
    assert config["instruments"] == [{"id": 42, "strategy": "HD", "status": "ACTIVE"}]
    assert config["trailingStopsConfig"] == {"breakEvenRR": 1.5, "trailStepRR": 0.75}


def test_hd_daemon_does_not_treat_api_failure_as_empty_instrument_list(monkeypatch):
    monkeypatch.setenv("STRATEGY_DASHBOARD_API_URL", "http://dashboard/api/instruments")
    monkeypatch.setattr(
        strategy_daemon,
        "urlopen",
        lambda url, timeout: (_ for _ in ()).throw(OSError("dashboard offline")),
    )

    assert strategy_daemon._load_config() is None


def test_hd_daemon_filter_excludes_ema21_instruments(monkeypatch):
    monkeypatch.setenv("STRATEGY_FILTER", "HD")
    config = {
        "instruments": [
            {"id": 1, "strategy": "21EMA", "status": "ACTIVE"},
            {"id": 2, "strategy": "HD", "status": "ACTIVE"},
        ],
    }

    assert list(strategy_daemon._managed_instruments(config)) == [2]
    assert strategy_daemon._build_command(config["instruments"][1]) == [
        "python3", "run_strategy.py", "--script", "NIFTY",
        "--strategy", "hd", "--mode", "live",
    ]


def test_manager_supports_all_dashboard_strategies(monkeypatch):
    strategies = ["21EMA", "HD", "CD", "TC", "2BC", "BO"]
    monkeypatch.setenv("STRATEGY_FILTER", ",".join(strategies))
    config = {
        "instruments": [
            {
                "id": index,
                "strategy": strategy,
                "brokerSymbol": "NIFTY",
                "status": "ACTIVE",
            }
            for index, strategy in enumerate(strategies, start=1)
        ],
    }

    managed = strategy_daemon._managed_instruments(config)

    assert list(managed) == [1, 2, 3, 4, 5, 6]
    assert [
        strategy_daemon._build_command(instrument)[5]
        for instrument in managed.values()
    ] == ["ema21", "hd", "cd", "tc", "2bc", "bo"]


def test_only_one_manager_can_hold_the_shared_logs_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(strategy_daemon, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(
        strategy_daemon,
        "DAEMON_LOCK_FILE",
        tmp_path / ".strategy_daemon.lock",
    )

    first_lock = strategy_daemon._acquire_singleton_lock()
    assert first_lock is not None
    try:
        assert strategy_daemon._acquire_singleton_lock() is None
    finally:
        first_lock.close()

    next_lock = strategy_daemon._acquire_singleton_lock()
    assert next_lock is not None
    next_lock.close()


def test_daemon_manages_only_active_instruments(monkeypatch):
    monkeypatch.delenv("STRATEGY_FILTER", raising=False)
    config = {
        "instruments": [
            {"id": 1, "strategy": "21EMA", "status": "ACTIVE"},
            {"id": 2, "strategy": "HD", "status": "INACTIVE"},
            {"id": 3, "strategy": "21EMA", "status": "ARCHIVED"},
        ],
    }

    assert list(strategy_daemon._managed_instruments(config)) == [1]


def test_hd_runtime_gets_its_own_broker_tag_and_sl_counter(monkeypatch):
    monkeypatch.delenv("SHARED_SL_COUNT_FILE", raising=False)
    monkeypatch.setenv("SHARED_SL_COUNT_NAMESPACE", "HD")
    env = strategy_daemon._strategy_environment(
        {"strategy": "HD", "lotSizeAdjustment": 2},
    )

    assert env["STRATEGY_NAME"] == "HD"
    assert env["SHARED_SL_COUNT_NAMESPACE"] == "HD"
    assert engine_module._shared_sl_count_path(date(2026, 10, 16)).name == (
        "sl_hits_20261016_HD.json"
    )


def test_strategy_runtime_tags_and_sl_counters_are_isolated(monkeypatch):
    monkeypatch.delenv("STRATEGY_NAME", raising=False)
    monkeypatch.delenv("SHARED_SL_COUNT_FILE", raising=False)
    monkeypatch.delenv("SHARED_SL_COUNT_NAMESPACE", raising=False)

    expected_tags = {
        "21EMA": "Strategy",
        "HD": "HD",
        "CD": "CD",
        "TC": "TC",
        "2BC": "2BC",
        "BO": "BO",
    }
    for strategy, expected_tag in expected_tags.items():
        environment = strategy_daemon._strategy_environment({"strategy": strategy})
        assert environment["STRATEGY_NAME"] == expected_tag
        assert environment["SHARED_SL_COUNT_NAMESPACE"] == (
            "EMA21" if strategy == "21EMA" else strategy
        )
        if strategy != "21EMA":
            assert "SHARED_SL_COUNT_FILE" not in environment


def test_ema21_reuses_legacy_stop_count_until_namespaced_file_exists(
    monkeypatch,
    tmp_path,
):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    trading_day = date(2026, 10, 16)
    legacy_path = logs_dir / "sl_hits_20261016.json"
    namespaced_path = logs_dir / "sl_hits_20261016_EMA21.json"
    legacy_path.write_text('{"count": 2}', encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHARED_SL_COUNT_FILE", raising=False)
    monkeypatch.setenv("SHARED_SL_COUNT_NAMESPACE", "EMA21")
    assert engine_module._shared_sl_count_path(trading_day) == legacy_path.relative_to(tmp_path)

    namespaced_path.write_text('{"count": 0}', encoding="utf-8")
    assert engine_module._shared_sl_count_path(trading_day) == namespaced_path.relative_to(tmp_path)


def test_hd_atm_lock_is_separate_from_ema21_lock():
    trading_day = date(2026, 10, 16)

    assert runner_module._atm_lock_path(trading_day, "NIFTY").name == (
        "atm_lock_NIFTY_20261016.json"
    )
    assert runner_module._atm_lock_path(trading_day, "NIFTY", "hd").name == (
        "atm_lock_NIFTY_HD_20261016.json"
    )


def test_hd_ignores_unowned_order_in_orderbook():
    class Broker(ConsoleBroker):
        strategy_tag = "HD"

        def __init__(self):
            super().__init__()
            self.is_replay = False
            self.cancelled = []
            self.stop_orders = []
            self.open_orders = [{
                "symbol": "NIFTY01SEP2624250CE",
                "action": "SELL",
                "quantity": 65,
                "trigger_price": 90.0,
                "orderid": "EMA-SL",
                "strategy": "ema21",
            }]

        def get_open_orders(self):
            return self.open_orders

        def cancel_order(self, order_id):
            self.cancelled.append(order_id)
            return True

        def place_stop_limit_order(self, symbol, side, quantity, trigger_price, limit_price):
            self.stop_orders.append((symbol, side.value, quantity, trigger_price, limit_price))
            return "HD-SL"

    broker = Broker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=HDSignalProvider(),
    )
    position = Position(
        option_symbol="NIFTY01SEP2624250CE",
        option_type="CE",
        quantity=65,
        initial_quantity=65,
        entry_price=100.0,
        entry_time=datetime(2026, 10, 16, 10, 0),
        option_stop_level=90.0,
        option_entry_trigger=100.0,
        option_risk_points=10.0,
    )

    engine._place_protective_stop("CE", position, position.entry_time)

    assert broker.cancelled == []
    assert broker.stop_orders == [
        ("NIFTY01SEP2624250CE", "SELL", 65, 90.0, 90.0)
    ]


def test_hd_does_not_restore_an_unidentified_broker_position(monkeypatch, tmp_path):
    class Broker(ConsoleBroker):
        def get_position_book(self):
            return [{
                "symbol": "NIFTY01SEP2624250CE",
                "quantity": 65,
                "average_price": 100.0,
            }]

        def get_open_orders(self):
            return []

    alerts_path = tmp_path / "trade_alerts_NIFTY_20261016.csv"
    monkeypatch.setattr(runner_module, "_trade_alert_path", lambda day, script: alerts_path)
    broker = Broker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(option_index_symbol="NIFTY"),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=HDSignalProvider(),
    )

    runner_module._restore_open_positions(engine, broker, date(2026, 10, 16))

    assert engine.state.ce.position is None
    assert engine.state.pe.position is None


def test_ema21_does_not_restore_a_position_tagged_for_hd(monkeypatch, tmp_path):
    class Broker(ConsoleBroker):
        strategy_tag = "Strategy"

        def get_position_book(self):
            return [{
                "symbol": "NIFTY01SEP2624250CE",
                "quantity": 65,
                "average_price": 100.0,
                "strategy": "HD",
            }]

        def get_open_orders(self):
            return []

    alerts_path = tmp_path / "trade_alerts_NIFTY_20261016.csv"
    monkeypatch.setattr(runner_module, "_trade_alert_path", lambda day, script: alerts_path)
    broker = Broker()
    engine = BaseStrategyEngine(
        cfg=StrategyConfig(option_index_symbol="NIFTY"),
        risk=RiskConfig(),
        broker=broker,
        signal_provider=EMA21SignalProvider(),
    )

    runner_module._restore_open_positions(engine, broker, date(2026, 10, 16))

    assert engine.state.ce.position is None
    assert engine.state.pe.position is None
