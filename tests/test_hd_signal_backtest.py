from datetime import date, datetime, time

import pandas as pd
import pytest

from core.models import StrategyConfig
from demo_hd_signal_backtest import (
    OUTPUT_COLUMNS,
    print_proxy_report,
    run_backtest,
    trace_spot_proxy_rules,
)
from strategies.hd import HDSignalProvider


def _spot_history(day: date) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "datetime": datetime.combine(day, time(9, 21)),
                "open": 25000.0,
                "high": 25010.0,
                "low": 24990.0,
                "close": 25005.0,
                "volume": 1000,
            },
            {
                "datetime": datetime.combine(day, time(9, 24)),
                "open": 25005.0,
                "high": 25015.0,
                "low": 25000.0,
                "close": 25010.0,
                "volume": 1000,
            },
        ]
    )


def _proxy_candles(day: date) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "datetime": datetime.combine(day, time(9, 27)),
                "open": 25000.0,
                "high": 25010.0,
                "low": 24990.0,
                "close": 25005.0,
                "rsi3": 25.0,
                "spot_ema13": 101.0,
                "spot_ema20": 100.0,
                "spot_ema50": 99.0,
            },
            {
                "datetime": datetime.combine(day, time(9, 30)),
                "open": 25005.0,
                "high": 25015.0,
                "low": 24995.0,
                "close": 25000.0,
                "rsi3": 19.0,
                "spot_ema13": 101.0,
                "spot_ema20": 100.0,
                "spot_ema50": 99.0,
            },
            {
                "datetime": datetime.combine(day, time(9, 33)),
                "open": 25010.0,
                "high": 25030.0,
                "low": 25009.0,
                "close": 25029.0,
                "rsi3": 25.0,
                "spot_ema13": 101.0,
                "spot_ema20": 100.0,
                "spot_ema50": 99.0,
            },
            {
                "datetime": datetime.combine(day, time(9, 36)),
                "open": 25030.0,
                "high": 25040.0,
                "low": 25020.0,
                "close": 25035.0,
                "rsi3": 26.0,
                "spot_ema13": 101.0,
                "spot_ema20": 100.0,
                "spot_ema50": 99.0,
            },
        ]
    )


def test_spot_proxy_uses_spot_rsi_ohlc_and_trend():
    day = date(2026, 10, 15)
    events = trace_spot_proxy_rules(
        _proxy_candles(day),
        "NIFTY",
        HDSignalProvider(),
        StrategyConfig(entry_cutoff=time(14, 40)),
    )

    assert [event["event"] for event in events] == ["HD"]
    signal = events[0]
    assert signal["result"] == "HD"
    assert signal["spot_symbol"] == "NIFTY"
    assert signal["rsi_dip"] == 19.0
    assert signal["spot_open"] == 25010.0
    assert signal["spot_close"] == 25029.0
    assert signal["trend"] == "BULLISH"
    assert signal["entry_trigger"] == 25031.0
    assert signal["entry_price"] == 25031.0
    assert signal["quantity"] == 1.0
    assert signal["stop_loss"] == 25008.0
    assert signal["exit_price"] == 25035.0
    assert signal["max_rr_achieved"] == 0.39
    assert signal["exit_rr"] == 0.17
    assert signal["pnl_inr_proxy"] == 4.0
    assert signal["trade_status"] == "CLOSED_SESSION"
    assert signal["exit_time"] == "09:36:00"
    assert "side" not in signal
    assert "spot_ema100" not in signal
    assert "spot_ema200" not in signal
    assert set(OUTPUT_COLUMNS).issubset(signal)


def test_spot_proxy_marks_invalid_alert_candle_as_no_signal():
    candles = _proxy_candles(date(2026, 10, 15))
    candles.loc[2, ["open", "high", "low", "close"]] = [
        25010.0,
        25020.0,
        25009.0,
        25011.0,
    ]

    events = trace_spot_proxy_rules(
        candles,
        "NIFTY",
        HDSignalProvider(),
        StrategyConfig(),
    )

    assert len(events) == 1
    assert events[0]["event"] == "RSI_DIP"
    assert events[0]["result"] == "RSI dipped below 20"
    assert "not followed by a valid alert candle" in events[0]["detail"]


def test_spot_proxy_emits_hd_when_spot_trend_is_bearish():
    candles = _proxy_candles(date(2026, 10, 15))
    for column, values in (
        ("spot_ema13", [99.0, 99.0, 99.0, 99.0]),
        ("spot_ema20", [100.0, 100.0, 100.0, 100.0]),
        ("spot_ema50", [101.0, 101.0, 101.0, 101.0]),
    ):
        candles[column] = values

    events = trace_spot_proxy_rules(
        candles,
        "NIFTY",
        HDSignalProvider(),
        StrategyConfig(),
    )

    assert [event["event"] for event in events] == ["HD"]
    assert events[0]["result"] == "HD"
    assert events[0]["trend"] == "BEARISH"
    assert "side" not in events[0]
    assert events[0]["entry_trigger"] == 25008.0
    assert events[0]["entry_price"] is None
    assert events[0]["stop_loss"] == 25031.0
    assert events[0]["trade_status"] == "NOT_FILLED"
    assert events[0]["pnl_inr_proxy"] == 0.0


def test_spot_proxy_applies_buffered_stop_loss():
    candles = _proxy_candles(date(2026, 10, 15))
    candles.loc[3, ["open", "high", "low", "close"]] = [
        25030.0,
        25040.0,
        25007.0,
        25007.5,
    ]

    events = trace_spot_proxy_rules(
        candles,
        "NIFTY",
        HDSignalProvider(),
        StrategyConfig(),
    )

    assert events[0]["entry_price"] == 25031.0
    assert events[0]["stop_loss"] == 25008.0
    assert events[0]["exit_price"] == 25008.0
    assert events[0]["max_rr_achieved"] == 0.39
    assert events[0]["exit_rr"] == -1.0
    assert events[0]["pnl_inr_proxy"] == -23.0
    assert events[0]["trade_status"] == "CLOSED_SL"


def test_spot_proxy_trails_to_breakeven_at_1_5r_then_advances_half_r():
    candles = _proxy_candles(date(2026, 10, 15))
    candles.loc[3, ["open", "high", "low", "close"]] = [
        25030.0,
        25066.0,
        25020.0,
        25060.0,
    ]
    later_candles = pd.DataFrame(
        [
            {
                "datetime": datetime(2026, 10, 15, 9, 39),
                "open": 25060.0,
                "high": 25080.0,
                "low": 25045.0,
                "close": 25070.0,
                "rsi3": 30.0,
                "spot_ema13": 101.0,
                "spot_ema20": 100.0,
                "spot_ema50": 99.0,
            },
            {
                "datetime": datetime(2026, 10, 15, 9, 42),
                "open": 25050.0,
                "high": 25055.0,
                "low": 25040.0,
                "close": 25045.0,
                "rsi3": 30.0,
                "spot_ema13": 101.0,
                "spot_ema20": 100.0,
                "spot_ema50": 99.0,
            },
        ]
    )
    candles = pd.concat([candles, later_candles], ignore_index=True)

    events = trace_spot_proxy_rules(
        candles,
        "NIFTY",
        HDSignalProvider(),
        StrategyConfig(),
    )

    assert events[0]["entry_price"] == 25031.0
    assert events[0]["trailing_stop"] == 25042.5
    assert events[0]["exit_price"] == 25042.5
    assert events[0]["max_rr_achieved"] == 2.13
    assert events[0]["exit_rr"] == 0.5
    assert events[0]["pnl_inr_proxy"] == 11.5
    assert events[0]["trade_status"] == "CLOSED_SL"


def test_spot_proxy_pnl_uses_configured_quantity():
    events = trace_spot_proxy_rules(
        _proxy_candles(date(2026, 10, 15)),
        "NIFTY",
        HDSignalProvider(),
        StrategyConfig(),
        quantity=3,
    )

    assert events[0]["quantity"] == 3
    assert events[0]["pnl_inr_proxy"] == 12.0
    assert events[0]["max_rr_achieved"] == 0.39
    assert events[0]["exit_rr"] == 0.17


def test_spot_proxy_report_labels_results_as_proxy(capsys):
    events = trace_spot_proxy_rules(
        _proxy_candles(date(2026, 10, 15)),
        "NIFTY",
        HDSignalProvider(),
        StrategyConfig(),
    )

    print_proxy_report(pd.DataFrame(events))
    report = capsys.readouterr().out
    assert "NOT OPTION-CANDLE HD SIGNALS" in report
    for column in (
        "SPOT",
        "CLOSE",
        "RSI DIP",
        "ENTRY",
        "SL",
        "TRAIL SL",
        "EXIT",
        "MAX R",
        "EXIT R",
        "P&L INR PROXY",
        "TRADE",
        "RESULT",
    ):
        assert column in report
    assert "EMA100" not in report
    assert "EMA200" not in report
    assert "SIDE" not in report


def test_backtest_fetches_only_spot_history_and_returns_spot_fields(
    tmp_path,
    monkeypatch,
):
    day = date(2026, 10, 15)

    class SpotOnlyBroker:
        def __init__(self):
            self.history_calls = []

        def fetch_history(self, symbol, exchange, interval, start_date, end_date):
            self.history_calls.append((symbol, exchange, interval))
            assert symbol == "NIFTY"
            return _spot_history(day)

        def search_symbols(self, *_args):
            raise AssertionError("spot proxy must not search option symbols")

    broker = SpotOnlyBroker()
    monkeypatch.chdir(tmp_path)
    cfg = StrategyConfig(
        spot_symbol="NIFTY",
        exchange_spot="NSE_INDEX",
        market_open=time(9, 15),
        market_close=time(15, 30),
        atm_lock_time=time(9, 20),
    )

    results = run_backtest(day, day, cfg, broker)

    assert broker.history_calls == [("NIFTY", "NSE_INDEX", "3m")]
    assert results.empty
    assert list(results.columns) == OUTPUT_COLUMNS
    assert not any("option" in column for column in results.columns)
    assert list(tmp_path.iterdir()) == []


def test_backtest_ignores_weekend_spot_rows():
    day = date(2026, 11, 8)

    class WeekendHistoryBroker:
        def __init__(self):
            self.history_symbols = []

        def fetch_history(self, symbol, exchange, interval, start_date, end_date):
            self.history_symbols.append(symbol)
            return pd.DataFrame(
                [
                    {
                        "datetime": datetime.combine(day, time(9, 21)),
                        "open": 25000.0,
                        "high": 25010.0,
                        "low": 24990.0,
                        "close": 25005.0,
                        "volume": 1000,
                    }
                ]
            )

    broker = WeekendHistoryBroker()
    results = run_backtest(
        day,
        day,
        StrategyConfig(
            spot_symbol="NIFTY",
            market_open=time(9, 15),
            market_close=time(15, 30),
            atm_lock_time=time(9, 20),
        ),
        broker,
    )

    assert results.empty
    assert broker.history_symbols == ["NIFTY"]
