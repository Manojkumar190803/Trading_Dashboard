from datetime import date, datetime, time

import pandas as pd
import pytest

from core.models import StrategyConfig
from demo_hd_signal_backtest import (
    print_spot_report,
    run_backtest,
    trace_spot_rules,
)
from strategies.hd import HDSignalProvider


def test_spot_trace_reports_valid_signal_and_requested_fields(capsys):
    candles = pd.DataFrame(
        [
            {
                "datetime": datetime(2026, 10, 15, 9, 27),
                "open": 25000.0,
                "high": 25020.0,
                "low": 24990.0,
                "close": 25010.0,
                "rsi3": 25.0,
                "spot_ema13": 101.0,
                "spot_ema20": 100.0,
                "spot_ema50": 99.0,
                "spot_ema100": 98.0,
                "spot_ema200": 97.0,
            },
            {
                "datetime": datetime(2026, 10, 15, 9, 30),
                "open": 25010.0,
                "high": 25020.0,
                "low": 25000.0,
                "close": 25015.0,
                "rsi3": 19.0,
                "spot_ema13": 101.0,
                "spot_ema20": 100.0,
                "spot_ema50": 99.0,
                "spot_ema100": 98.0,
                "spot_ema200": 97.0,
            },
            {
                "datetime": datetime(2026, 10, 15, 9, 33),
                "open": 25015.0,
                "high": 25025.5,
                "low": 25014.0,
                "close": 25025.0,
                "rsi3": 25.0,
                "spot_ema13": 101.0,
                "spot_ema20": 100.0,
                "spot_ema50": 99.0,
                "spot_ema100": 98.0,
                "spot_ema200": 97.0,
            },
        ]
    )
    cfg = StrategyConfig(
        entry_cutoff=time(14, 40),
        max_option_risk_points=20.0,
    )

    events = trace_spot_rules(candles, HDSignalProvider(), cfg)

    assert [event["event"] for event in events] == ["SIGNAL"]
    signal = events[-1]
    assert signal["result"] == "HD CAME"
    assert signal["rsi_value"] == pytest.approx(19.0)
    assert signal["spot_trigger"] == 25025.5
    assert signal["stop_level"] == 25014.0
    assert signal["spot_risk_points"] == pytest.approx(11.5)
    assert signal["spot_close"] == 25025.0
    assert signal["spot_ema100"] == 98.0
    assert signal["spot_ema200"] == 97.0
    assert {
        "date",
        "time",
        "rsi_value",
        "spot_ema13",
        "spot_ema20",
        "spot_ema50",
        "spot_ema100",
        "spot_ema200",
        "spot_close",
        "side",
        "result",
    }.issubset(signal)
    print_spot_report(pd.DataFrame(events))
    report = capsys.readouterr().out
    for column in ("DATE", "TIME", "RSI DIP", "EMA13", "EMA20", "EMA50", "EMA100", "EMA200", "CLOSE", "SIDE", "RESULT"):
        assert column in report

    invalid_alert = candles.copy()
    invalid_alert.loc[2, ["open", "close"]] = [25025.0, 25015.0]
    rejected = trace_spot_rules(invalid_alert, HDSignalProvider(), cfg)
    assert len(rejected) == 1
    assert rejected[0]["result"] == "HD DID NOT COME"

    after_cutoff = StrategyConfig(entry_cutoff=time(9, 33))
    after_cutoff_attempt = trace_spot_rules(candles, HDSignalProvider(), after_cutoff)
    assert len(after_cutoff_attempt) == 1
    assert after_cutoff_attempt[0]["result"] == "HD DID NOT COME"


def test_backtest_fetches_only_spot_and_prints_without_creating_files(tmp_path, capsys, monkeypatch):
    day = date(2026, 10, 15)
    timestamps = pd.date_range("2026-10-15 09:15", periods=30, freq="3min")
    spot = pd.DataFrame({
        "datetime": timestamps,
        "open": [25000.0 + index for index in range(len(timestamps))],
        "high": [25010.0 + index for index in range(len(timestamps))],
        "low": [24990.0 + index for index in range(len(timestamps))],
        "close": [25005.0 + index for index in range(len(timestamps))],
        "volume": [1000] * len(timestamps),
    })
    class FakeHistoryBroker:
        def __init__(self):
            self.history_symbols = []

        def fetch_history(self, symbol, exchange, interval, start_date, end_date):
            self.history_symbols.append(symbol)
            return spot

    broker = FakeHistoryBroker()
    monkeypatch.chdir(tmp_path)
    cfg = StrategyConfig(
        spot_symbol="NIFTY",
        option_index_symbol="NIFTY",
        market_open=time(9, 15),
        market_close=time(15, 30),
        atm_lock_time=time(9, 20),
    )

    results = run_backtest(day, day, cfg, broker)

    assert broker.history_symbols == ["NIFTY"]
    assert results.empty
    assert list(tmp_path.iterdir()) == []

    print_spot_report(results)
    report = capsys.readouterr().out
    assert "HD SIGNAL ATTEMPTS" in report
    assert "No RSI(3) dips occurred" in report
    assert "None" not in report


def test_backtest_ignores_weekend_spot_rows():
    day = date(2026, 11, 8)
    weekend_spot = pd.DataFrame({
        "datetime": pd.date_range("2026-11-08 09:15", periods=3, freq="3min"),
        "open": [25000.0, 25001.0, 25002.0],
        "high": [25010.0, 25011.0, 25012.0],
        "low": [24990.0, 24991.0, 24992.0],
        "close": [25005.0, 25006.0, 25007.0],
        "volume": [1000] * 3,
    })

    class WeekendHistoryBroker:
        def fetch_history(self, symbol, exchange, interval, start_date, end_date):
            return weekend_spot

    results = run_backtest(
        day,
        day,
        StrategyConfig(
            spot_symbol="NIFTY",
            option_index_symbol="NIFTY",
            market_open=time(9, 15),
            market_close=time(15, 30),
            atm_lock_time=time(9, 20),
        ),
        WeekendHistoryBroker(),
    )

    assert results.empty


def test_backtest_keeps_failed_rsi_attempt_with_all_requested_fields(monkeypatch):
    day = date(2026, 10, 15)
    history = pd.DataFrame(
        [{
            "datetime": datetime(2026, 10, 15, 9, 15),
            "open": 25000.0,
            "high": 25010.0,
            "low": 24990.0,
            "close": 25005.0,
            "volume": 1000,
        }]
    )
    attempt_candles = pd.DataFrame(
        [
            {
                "datetime": datetime(2026, 10, 15, 9, 27),
                "open": 25000.0,
                "high": 25020.0,
                "low": 24990.0,
                "close": 25010.0,
                "rsi3": 25.0,
                "ema13": 101.0,
                "ema20": 100.0,
                "ema50": 99.0,
                "ema100": 98.0,
                "ema200": 97.0,
            },
            {
                "datetime": datetime(2026, 10, 15, 9, 30),
                "open": 25010.0,
                "high": 25020.0,
                "low": 25000.0,
                "close": 25015.0,
                "rsi3": 19.0,
                "ema13": 101.0,
                "ema20": 100.0,
                "ema50": 99.0,
                "ema100": 98.0,
                "ema200": 97.0,
            },
            {
                "datetime": datetime(2026, 10, 15, 9, 33),
                "open": 25025.0,
                "high": 25025.5,
                "low": 25014.0,
                "close": 25015.0,
                "rsi3": 25.0,
                "ema13": 101.0,
                "ema20": 100.0,
                "ema50": 99.0,
                "ema100": 98.0,
                "ema200": 97.0,
            },
        ]
    )

    class FakeHistoryBroker:
        def fetch_history(self, symbol, exchange, interval, start_date, end_date):
            return history

    monkeypatch.setattr(
        "demo_hd_signal_backtest._warmup_and_slice",
        lambda _history, _day, _cfg: attempt_candles,
    )

    results = run_backtest(
        day,
        day,
        StrategyConfig(
            spot_symbol="NIFTY",
            option_index_symbol="NIFTY",
            market_open=time(9, 15),
            market_close=time(15, 30),
            atm_lock_time=time(9, 20),
        ),
        FakeHistoryBroker(),
    )

    assert results["event"].tolist() == ["SETUP_ATTEMPT"]
    assert results["result"].tolist() == ["HD DID NOT COME"]
    assert results["rsi_value"].tolist() == [19.0]
    assert all(results[f"spot_ema{period}"].iloc[0] is not None for period in (13, 20, 50, 100, 200))
