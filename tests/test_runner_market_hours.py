import csv
from datetime import date, datetime, time

import pytest
import pandas as pd

import core.runner as runner
from core.broker import ConsoleBroker
from core.engine import BaseStrategyEngine
from core.models import RiskConfig, StrategyAlert, StrategyConfig
from strategies.ema21 import EMA21SignalProvider
from strategies.hd import HDSignalProvider


class _FixedDateTime(datetime):
    _now_value = datetime(2026, 8, 10, 10, 0)

    @classmethod
    def now(cls, tz=None):
        return cls._now_value


@pytest.mark.parametrize(
    "runner_obj",
    [
        runner.LiveFeedRunner(engine=object(), broker=object(), cfg=StrategyConfig()),  # type: ignore[arg-type]
        runner.MultiEngineLiveFeedRunner(engines=[], broker=object(), cfg=StrategyConfig()),  # type: ignore[arg-type]
    ],
)
def test_is_market_open_weekday_windows(monkeypatch, runner_obj):
    monkeypatch.setattr(runner, "datetime", _FixedDateTime)

    _FixedDateTime._now_value = datetime(2026, 8, 10, 9, 19)
    assert runner_obj._is_market_open() is False

    _FixedDateTime._now_value = datetime(2026, 8, 10, 9, 20)
    assert runner_obj._is_market_open() is True

    _FixedDateTime._now_value = datetime(2026, 8, 10, 15, 14)
    assert runner_obj._is_market_open() is True

    _FixedDateTime._now_value = datetime(2026, 8, 10, 15, 15)
    assert runner_obj._is_market_open() is False


def test_is_market_open_weekend_closed(monkeypatch):
    cfg = StrategyConfig(market_open=time(9, 20), market_close=time(15, 15))
    runner_obj = runner.LiveFeedRunner(engine=object(), broker=object(), cfg=cfg)  # type: ignore[arg-type]

    monkeypatch.setattr(runner, "datetime", _FixedDateTime)
    _FixedDateTime._now_value = datetime(2026, 8, 9, 10, 30)  # Sunday

    assert runner_obj._is_market_open() is False


def test_hd_dashboard_monitoring_window_controls_runner_hours(monkeypatch):
    cfg = StrategyConfig(market_open=time(9, 30), market_close=time(15, 0))
    runner_obj = runner.LiveFeedRunner(engine=object(), broker=object(), cfg=cfg)  # type: ignore[arg-type]
    monkeypatch.setattr(runner, "datetime", _FixedDateTime)

    _FixedDateTime._now_value = datetime(2026, 8, 10, 9, 29)
    assert runner_obj._is_market_open() is False

    _FixedDateTime._now_value = datetime(2026, 8, 10, 9, 30)
    assert runner_obj._is_market_open() is True

    _FixedDateTime._now_value = datetime(2026, 8, 10, 14, 59)
    assert runner_obj._is_market_open() is True

    _FixedDateTime._now_value = datetime(2026, 8, 10, 15, 0)
    assert runner_obj._is_market_open() is False


def test_hd_lock_schedule_uses_hourly_boundaries_from_market_open():
    lock_time = time(9, 20)
    assert runner._scheduled_hd_lock_time(
        datetime(2026, 8, 10, 9, 19),
        lock_time,
    ) is None
    assert runner._scheduled_hd_lock_time(
        datetime(2026, 8, 10, 9, 20),
        lock_time,
    ) == datetime(2026, 8, 10, 9, 20)
    assert runner._scheduled_hd_lock_time(
        datetime(2026, 8, 10, 10, 20),
        lock_time,
    ) == datetime(2026, 8, 10, 10, 20)
    assert runner._scheduled_hd_lock_time(
        datetime(2026, 8, 10, 10, 28),
        lock_time,
    ) == datetime(2026, 8, 10, 10, 20)


def test_live_hd_runner_rechecks_contracts_hourly(monkeypatch, tmp_path):
    class ChainBroker(ConsoleBroker):
        spot_price = 25020.0

        def get_ltp(self, symbol):
            return self.spot_price if symbol == "NIFTY" else 150.0

        def search_symbols(self, query, exchange):
            root, strike, option_type = query.split()
            return [{
                "symbol": f"{option_type}-{strike}",
                "name": root,
                "strike": int(strike),
                "instrumenttype": option_type,
                "expiry": "25-AUG-26",
            }]

    monkeypatch.chdir(tmp_path)
    cfg = StrategyConfig()
    broker = ChainBroker()
    engine = BaseStrategyEngine(cfg, RiskConfig(), broker, HDSignalProvider())
    live_runner = runner.LiveFeedRunner(engine, broker, cfg)

    live_runner._try_lock_atm(datetime(2026, 8, 10, 9, 20))
    assert (engine.state.ce_symbol, engine.state.pe_symbol) == (
        "CE-24950",
        "PE-25050",
    )

    broker.spot_price = 25120.0
    live_runner._try_lock_atm(datetime(2026, 8, 10, 10, 19))
    assert (engine.state.ce_symbol, engine.state.pe_symbol) == (
        "CE-24950",
        "PE-25050",
    )

    live_runner._try_lock_atm(datetime(2026, 8, 10, 10, 20))
    assert (engine.state.ce_symbol, engine.state.pe_symbol) == (
        "CE-25050",
        "PE-25150",
    )
    assert engine.state.atm_locked_at == datetime(2026, 8, 10, 10, 20)


def test_multi_runner_uses_hd_contract_selection_when_hd_is_not_first(
    monkeypatch,
    tmp_path,
):
    class ChainBroker(ConsoleBroker):
        spot_price = 25020.0

        def get_ltp(self, symbol):
            return self.spot_price if symbol == "NIFTY" else 150.0

        def search_symbols(self, query, exchange):
            root, strike, option_type = query.split()
            return [{
                "symbol": f"{option_type}-{strike}",
                "name": root,
                "strike": int(strike),
                "instrumenttype": option_type,
                "expiry": "25-AUG-26",
            }]

    monkeypatch.chdir(tmp_path)
    cfg = StrategyConfig()
    broker = ChainBroker()
    other_engine = BaseStrategyEngine(
        cfg,
        RiskConfig(),
        broker,
        EMA21SignalProvider(),
    )
    hd_engine = BaseStrategyEngine(cfg, RiskConfig(), broker, HDSignalProvider())
    live_runner = runner.MultiEngineLiveFeedRunner(
        [("ema21", other_engine), ("hd", hd_engine)],
        broker,
        cfg,
    )

    live_runner._try_lock_atm(datetime(2026, 8, 10, 9, 20))
    assert (other_engine.state.ce_symbol, other_engine.state.pe_symbol) == (
        "CE-24950",
        "PE-25050",
    )

    broker.spot_price = 25120.0
    live_runner._try_lock_atm(datetime(2026, 8, 10, 10, 20))
    assert (other_engine.state.ce_symbol, other_engine.state.pe_symbol) == (
        "CE-25050",
        "PE-25150",
    )


def test_attach_spot_ema_context_uses_latest_non_future_spot_candle():
    option_data = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-08-10 09:23", "2026-08-10 09:20"]),
            "close": [101.0, 100.0],
        }
    )
    spot_data = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-08-10 09:20", "2026-08-10 09:26"]),
            "ema13": [10.0, 20.0],
            "ema20": [9.0, 19.0],
            "ema50": [8.0, 18.0],
        }
    )

    result = runner._attach_spot_ema_context(option_data, spot_data)

    assert result["datetime"].tolist() == option_data["datetime"].tolist()
    assert result["spot_ema13"].tolist() == [10.0, 10.0]
    assert result["spot_ema20"].tolist() == [9.0, 9.0]
    assert result["spot_ema50"].tolist() == [8.0, 8.0]


def test_load_persisted_trade_alerts_restores_entry_and_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    alerts_path = tmp_path / "logs" / "trade_alerts_NIFTY_20260810.csv"
    alerts_path.parent.mkdir()
    with alerts_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("timestamp", "strategy", "category", "message"))
        writer.writerow(("2026-08-10 10:00:00", "StubStrategy", "ENTRY", "Entered CE"))
        writer.writerow(("2026-08-10 10:30:00", "StubStrategy", "EXIT", "Exited CE"))

    class Engine:
        strategy_name = "StubStrategy"
        cfg = StrategyConfig(option_index_symbol="NIFTY")
        alerts: list[StrategyAlert] = []

    engine = Engine()
    runner._load_persisted_trade_alerts(engine, date(2026, 8, 10))  # type: ignore[arg-type]

    assert [(alert.category, alert.message) for alert in engine.alerts] == [
        ("ENTRY", "Entered CE"),
        ("EXIT", "Exited CE"),
    ]
