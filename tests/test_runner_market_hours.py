import csv
from datetime import date, datetime, time

import pytest

import core.runner as runner
from core.models import StrategyAlert, StrategyConfig


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
