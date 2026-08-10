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
        self.optionchain_response = {
            "status": "success",
            "data": {
                "underlying": "NIFTY",
                "lot_size": 75,
                "records": [
                    {"expiry": "2026-08-11", "strike": 24600},
                    {"expiry": "2026-08-11", "strike": 24650},
                    {"expiry": "2026-08-11", "strike": 24700},
                ],
            },
        }

    def quotes(self, symbol: str, exchange: str):
        return self.quotes_response

    def placeorder(self, **kwargs):
        self.last_placeorder_kwargs = kwargs
        return self.placeorder_response

    def history(self, **kwargs):
        return self.history_response

    def optionchain(self, **kwargs):
        return self.optionchain_response


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
    assert broker._infer_exchange("SENSEX") == "BSE_INDEX"


def test_discover_index_profile_from_optionchain(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    client = fake_openalgo["client"]
    client.optionchain_response = {
        "status": "success",
        "data": {
            "underlying": "NIFTY",
            "lot_size": 65,
            "records": [
                {"expiry": "2026-08-11", "strike": 25000},
                {"expiry": "2026-08-11", "strike": 25050},
                {"expiry": "2026-08-11", "strike": 25100},
            ],
        },
    }

    profile = broker.discover_index_profile("Nifty")
    assert profile["spot_symbol"] == "NIFTY"
    assert profile["option_index_symbol"] == "NIFTY"
    assert profile["exchange_spot"] == "NSE_INDEX"
    assert profile["exchange_options"] == "NFO"
    assert profile["strike_step"] == 50
    assert profile["option_lot_size"] == 65
    assert profile["weekly_expiry_weekday"] == 1


def test_discover_index_profile_alias_banknifty(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    client = fake_openalgo["client"]
    client.optionchain_response = {
        "status": "success",
        "data": {
            "underlying": "BANKNIFTY",
            "market_lot": 30,
            "records": [
                {"expiry": "2026-08-13", "strike": 56000},
                {"expiry": "2026-08-13", "strike": 56100},
            ],
        },
    }

    profile = broker.discover_index_profile("NIFTY BANK")
    assert profile["spot_symbol"] == "BANKNIFTY"
    assert profile["option_index_symbol"] == "BANKNIFTY"
    assert profile["exchange_spot"] == "NSE_INDEX"
    assert profile["exchange_options"] == "NFO"
    assert profile["strike_step"] == 100
    assert profile["option_lot_size"] == 30
    assert profile["weekly_expiry_weekday"] == 3


def test_discover_index_profile_fails_when_payload_not_found(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    client = fake_openalgo["client"]
    client.optionchain_response = {"status": "error", "message": "missing"}

    with pytest.raises(RuntimeError, match="Could not discover instrument metadata"):
        broker.discover_index_profile("NIFTY")


def test_discover_index_profile_falls_back_when_strike_missing_for_known_script(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    client = fake_openalgo["client"]
    client.optionchain_response = {
        "status": "success",
        "data": {"underlying": "NIFTY", "lot_size": 65, "records": [{"expiry": "2026-08-11"}]},
    }

    profile = broker.discover_index_profile("NIFTY")
    assert profile["strike_step"] == 50
    assert profile["option_lot_size"] == 65


def test_discover_index_profile_falls_back_when_lot_missing_for_known_script(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    client = fake_openalgo["client"]
    client.optionchain_response = {
        "status": "success",
        "data": {
            "underlying": "NIFTY",
            "records": [{"expiry": "2026-08-11", "strike": 25000}, {"expiry": "2026-08-11", "strike": 25050}],
        },
    }

    profile = broker.discover_index_profile("NIFTY")
    assert profile["strike_step"] == 50
    assert profile["option_lot_size"] == 65


def test_discover_index_profile_requires_strike_step_for_unknown_script(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    client = fake_openalgo["client"]
    client.optionchain_response = {
        "status": "success",
        "data": {"underlying": "MIDCAP", "lot_size": 10, "records": [{"expiry": "2026-08-11"}]},
    }

    with pytest.raises(RuntimeError, match="strike-step"):
        broker.discover_index_profile("MIDCAP")


def test_discover_index_profile_requires_lot_size_for_unknown_script(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    client = fake_openalgo["client"]
    client.optionchain_response = {
        "status": "success",
        "data": {
            "underlying": "MIDCAP",
            "records": [{"expiry": "2026-08-11", "strike": 25000}, {"expiry": "2026-08-11", "strike": 25050}],
        },
    }

    with pytest.raises(RuntimeError, match="lot-size"):
        broker.discover_index_profile("MIDCAP")


def test_discover_payload_handles_method_errors_and_later_success(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)

    class _Client:
        def optionchain(self, **kwargs):
            raise RuntimeError("boom")

        def searchscrip(self, **kwargs):
            return {"status": "error"}

        def search(self, **kwargs):
            return None

        def instruments(self, **kwargs):
            return {"status": "success", "data": {"lot_size": 10, "strike_step": 100}}

    broker.client = _Client()
    payload, err = broker._discover_payload("NIFTY", "NSE_INDEX", "NFO")
    assert err is None
    assert isinstance(payload, dict)
    assert payload["status"] == "success"


def test_discover_index_profile_optionchain_with_expiry_date_required(fake_openalgo, caplog):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    client = fake_openalgo["client"]

    def _optionchain(**kwargs):
        if "expiry_date" not in kwargs:
            raise TypeError("missing required argument: expiry_date")
        return {
            "status": "success",
            "data": {
                "Underlying": "NIFTY",
                "LotSize": "65",
                "StrikeInterval": "50",
            },
        }

    def _expiry(**kwargs):
        return {
            "status": "success",
            "data": [{"Expiry": "2026-08-11"}],
        }

    client.optionchain = _optionchain
    client.expiry = _expiry

    caplog.clear()
    profile = broker.discover_index_profile("NIFTY")

    assert profile["spot_symbol"] == "NIFTY"
    assert profile["option_index_symbol"] == "NIFTY"
    assert profile["strike_step"] == 50
    assert profile["option_lot_size"] == 65
    assert "missing strike/lot metadata" not in caplog.text


def test_discover_index_profile_full_known_fallback_logs_info_not_warning(fake_openalgo, caplog):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)
    client = fake_openalgo["client"]
    client.optionchain_response = {
        "status": "success",
        "data": {"underlying": "NIFTY", "lotsize": None, "strike": None},
    }

    with caplog.at_level("INFO"):
        profile = broker.discover_index_profile("NIFTY")

    assert profile["strike_step"] == 50
    assert profile["option_lot_size"] == 65
    # For known scripts with both fields missing, this should be informational, not warning noise.
    warns = [r for r in caplog.records if r.levelname == "WARNING" and "missing strike/lot metadata" in r.message]
    infos = [r for r in caplog.records if r.levelname == "INFO" and "missing strike/lot metadata" in r.message]
    assert not warns
    assert infos


def test_discovery_helper_parsers_cover_edge_cases(fake_openalgo):
    broker = OpenAlgoBroker(api_key="k", host="h", dry_run=True)

    assert broker._normalize_script_name("nifty 50") == "NIFTY"
    assert broker._normalize_script_name("Nifty-Bank") == "BANKNIFTY"
    assert broker._symbol_aliases("UNKNOWN") == ["UNKNOWN"]

    assert broker._is_usable_payload(None) is False
    assert broker._is_usable_payload({"status": "error"}) is False
    assert broker._is_usable_payload({"status": "success"}) is True

    assert broker._coerce_number("1,234.5") == 1234.5
    assert broker._coerce_number("abc") is None
    assert broker._coerce_number(object()) is None

    numeric = broker._extract_numeric_fields({"data": [{"lotsize": "65"}, {"marketlot": 30}, {"lot_size": "x"}]})
    assert numeric["lot_size"] == 65
    assert numeric["market_lot"] == 30

    numeric_ci = broker._extract_numeric_fields({"data": [{"LotSize": "65"}, {"MarketLot": "30"}]})
    assert numeric_ci["lot_size"] == 65
    assert numeric_ci["market_lot"] == 30

    assert broker._extract_strike_step({"strike_interval": "50"}) == 50
    assert broker._extract_strike_step({"StrikeInterval": "100"}) == 100
    assert broker._extract_strike_step({"data": [{"strike": 25000}, {"strike": 25100}]}) == 100
    assert broker._extract_strike_step({"data": [[25000, 25050, 25100]]}) == 50
    assert broker._extract_strike_step({"data": [{"strike": 25000}]}) is None

    assert broker._extract_symbol({"data": [{"name": "NIFTY 50"}]}) == "NIFTY"
    assert broker._extract_symbol({"data": [{"name": "OTHER"}]}) is None

    assert broker._extract_option_root({"data": [{"underlying_symbol": "Nifty"}]}) == "NIFTY"
    assert broker._extract_option_root(["noop", 1]) is None
    assert broker._infer_index_root("NIFTY11AUG2625100CE") == "NIFTY"
    assert broker._infer_index_root("Nifty Bank") == "BANKNIFTY"
    assert broker._infer_index_root("SENSEX10SEP2682700PE") == "SENSEX"
    assert broker._infer_index_root("   ") is None
    assert broker._infer_index_root("random") is None

    assert broker._extract_weekly_expiry_weekday({"data": [{"expiry_weekday": 4}]}) == 4
    assert broker._extract_weekly_expiry_weekday({"data": [{"exp": ""}]}) == 1
    assert broker._extract_weekly_expiry_weekday(["11-08-2026", "18-08-2026"]) == 1

    assert broker._parse_date("11-08-2026") is not None
    assert broker._parse_date("11Aug26") is not None
    assert broker._parse_date(123) is None
    assert broker._parse_date("") is None
    assert broker._parse_date("invalid") is None


def test_historical_replay_broker_paths():
    broker = HistoricalReplayBroker()
    assert broker.get_ltp("UNKNOWN") == 0.0

    bar = pd.Series({"close": 123.4})
    broker.set_current_bar("SYM", bar)
    assert broker.get_ltp("SYM") == 123.4
    assert broker.place_market_order("SYM", OrderSide.BUY, 2) == "BT-MKT-SYM-BUY-2"
    assert broker.place_stop_limit_order("SYM", OrderSide.SELL, 3, 10.0, 9.5) == "BT-SL-L-SYM-SELL-3"