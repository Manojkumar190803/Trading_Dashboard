"""Tests for core.broker implementations."""

import builtins
from types import SimpleNamespace

import pandas as pd
import pytest

from core.broker import (
    BrokerInterface,
    ConsoleBroker,
    HistoricalReplayBroker,
    OpenAlgoBroker,
)
from core.models import OrderSide


class _StubClient:
    def __init__(self):
        self.quotes_response = {"status": "success", "data": {"ltp": 123.45}}
        self.placeorder_response = {"status": "success", "orderid": "OID-1"}
        self.history_response = pd.DataFrame(
            {
                "datetime": pd.to_datetime(["2026-08-08 09:20:00"]),
                "open": [1],
                "high": [2],
                "low": [0.5],
                "close": [1.5],
                "volume": [100],
            }
        )
        self.last_placeorder_kwargs = None

    def quotes(self, symbol: str, exchange: str):
        return self.quotes_response

    def placeorder(self, **kwargs):
        self.last_placeorder_kwargs = kwargs
        return self.placeorder_response

    def history(self, **kwargs):
        return self.history_response


@pytest.fixture
def fake_openalgo(monkeypatch):
    holder = {}

    def _api(**kwargs):
        holder["api_kwargs"] = kwargs
        holder["client"] = _StubClient()
        return holder["client"]

    monkeypatch.setitem(__import__("sys").modules, "openalgo", SimpleNamespace(api=_api))
    return holder


def test_broker_interface_raises_not_implemented():
    broker = BrokerInterface()
    with pytest.raises(NotImplementedError):
        broker.get_ltp("ABC")
    with pytest.raises(NotImplementedError):
        broker.place_stop_limit_order("ABC", OrderSide.BUY, 1, 100.0, 100.5)
    with pytest.raises(NotImplementedError):
        broker.place_market_order("ABC", OrderSide.SELL, 1)


def test_console_broker_basic_paths(capsys):
    broker = ConsoleBroker(ltp_fallback=222.5)
    assert broker.get_ltp("SYM") == 222.5
    assert broker.place_stop_limit_order("SYM", OrderSide.BUY, 10, 100.0, 100.5) == "SL-L-SYM-OrderSide.BUY-10"
    assert broker.place_market_order("SYM", OrderSide.SELL, 5) == "MKT-SYM-OrderSide.SELL-5"
    out = capsys.readouterr().out
    assert "get_ltp" in out
    assert "place_stop_limit_order" in out
    assert "place_market_order" in out


def test_openalgo_broker_import_error(monkeypatch):
    monkeypatch.delitem(__import__("sys").modules, "openalgo", raising=False)
    original_import = builtins.__import__

    def _raise_on_openalgo(name, *args, **kwargs):
        if name == "openalgo":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _raise_on_openalgo)
    with pytest.raises(RuntimeError, match="openalgo package not installed"):
        OpenAlgoBroker(api_key="k", host="h")


def test_openalgo_broker_init_and_dry_run_order_paths(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    assert fake_openalgo["api_kwargs"] == {"api_key": "k", "host": "h"}
    assert broker.place_stop_limit_order("NIFTYCE", OrderSide.BUY, 2, 10.0, 10.5).startswith("DRY-SL-L-")
    assert broker.place_market_order("NIFTYCE", OrderSide.SELL, 2).startswith("DRY-MKT-")


def test_openalgo_broker_get_ltp_paths(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    client = fake_openalgo["client"]

    client.quotes_response = {"status": "success", "data": {"ltp": 100.126}}
    assert broker.get_ltp("NIFTY08AUG2625000CE") == 100.13

    client.quotes_response = {"status": "success", "ltp": 99.991}
    assert broker.get_ltp("NIFTY") == 99.99

    client.quotes_response = {"status": "error", "message": "bad"}
    assert broker.get_ltp("NIFTY") == 0.0

    def _boom(*_args, **_kwargs):
        raise RuntimeError("oops")

    client.quotes = _boom
    assert broker.get_ltp("NIFTY") == 0.0


def test_openalgo_broker_live_order_and_extract_paths(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=False)
    client = fake_openalgo["client"]

    oid = broker.place_stop_limit_order("NIFTY08AUG2625000CE", OrderSide.BUY, 2, 12.0, 12.5)
    assert oid == "OID-1"
    assert client.last_placeorder_kwargs["price_type"] == "SL"

    client.placeorder_response = {"status": "success", "data": {"orderid": "OID-2"}}
    oid2 = broker.place_market_order("NIFTY", OrderSide.SELL, 3)
    assert oid2 == "OID-2"
    assert client.last_placeorder_kwargs["price_type"] == "MARKET"

    client.placeorder_response = "OID-3"
    assert broker.place_market_order("NIFTY", OrderSide.SELL, 1) == "OID-3"

    client.placeorder_response = {"status": "error", "reason": "rejected"}
    with pytest.raises(RuntimeError, match="Order rejected"):
        broker.place_market_order("NIFTY", OrderSide.SELL, 1)

    def _raise(*_args, **_kwargs):
        raise ValueError("fail")

    client.placeorder = _raise
    with pytest.raises(ValueError, match="fail"):
        broker.place_stop_limit_order("NIFTY", OrderSide.BUY, 1, 1.0, 1.5)

    with pytest.raises(ValueError, match="fail"):
        broker.place_market_order("NIFTY", OrderSide.SELL, 1)


def test_openalgo_fetch_history_paths(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h")
    client = fake_openalgo["client"]

    df = broker.fetch_history("NIFTY", "NFO", "3m", "2026-08-01", "2026-08-08")
    assert not df.empty

    client.history_response = {"status": "error"}
    with pytest.raises(RuntimeError, match="history returned error"):
        broker.fetch_history("NIFTY", "NFO", "3m", "2026-08-01", "2026-08-08")

    client.history_response = pd.DataFrame()
    with pytest.raises(RuntimeError, match="No history data"):
        broker.fetch_history("NIFTY", "NFO", "3m", "2026-08-01", "2026-08-08")


def test_openalgo_exchange_inference(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", exchange_options="OPTX")
    assert broker._infer_exchange("ANYCE") == "OPTX"
    assert broker._infer_exchange("ANYPE") == "OPTX"
    assert broker._infer_exchange("NIFTY") == "NSE_INDEX"


def test_historical_replay_broker_paths():
    broker = HistoricalReplayBroker()
    assert broker.get_ltp("UNKNOWN") == 0.0

    bar = pd.Series({"close": 123.4})
    broker.set_current_bar("SYM", bar)
    assert broker.get_ltp("SYM") == 123.4
    assert broker.place_market_order("SYM", OrderSide.BUY, 2) == "BT-MKT-SYM-BUY-2"
    assert broker.place_stop_limit_order("SYM", OrderSide.SELL, 3, 10.0, 9.5) == "BT-SL-L-SYM-SELL-3"