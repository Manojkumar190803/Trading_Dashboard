"""Tests for replay option symbol fallback helpers in core.runner."""

from datetime import datetime

import pandas as pd

import core.runner as runner


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