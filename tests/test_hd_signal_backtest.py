from datetime import date, datetime, time

import pandas as pd
import pytest

from core.models import StrategyConfig
from demo_hd_signal_backtest import print_spot_report, run_backtest, trace_spot_rules
from strategies.hd import HDSignalProvider


def test_spot_trace_reports_rsi_alert_and_directional_signal():
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
            },
        ]
    )
    cfg = StrategyConfig(
        entry_cutoff=time(14, 40),
        max_option_risk_points=20.0,
    )

    events = trace_spot_rules(candles, HDSignalProvider(), cfg)

    assert [event["event"] for event in events] == [
        "RSI_CROSS_BELOW_20",
        "ALERT_CANDLE",
        "SIGNAL",
    ]
    signal = events[-1]
    assert signal["result"] == "SPOT RULE SIGNAL"
    assert signal["spot_trigger"] == 25025.5
    assert signal["stop_level"] == 25014.0
    assert signal["spot_risk_points"] == pytest.approx(11.5)
    assert signal["spot_close"] == 25025.0


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
    assert list(tmp_path.iterdir()) == []

    print_spot_report(results)
    report = capsys.readouterr().out
    assert "HD NIFTY SPOT RULE CHECK" in report
    assert "SPOT SIGNAL RULE TIMELINE" in report
    assert "None" not in report