import pytest
import threading
import json

from core.dashboard_data import DashboardDataProvider
import core.dashboard_data as dashboard_data_module


class FakeOpenAlgoClient:
    def __init__(self, funds_response):
        self.funds_response = funds_response

    def funds(self):
        return self.funds_response


def make_provider(client):
    provider = DashboardDataProvider.__new__(DashboardDataProvider)
    provider.client = client
    provider.strategy_tag = "test"
    provider._snapshot_lock = threading.Lock()
    return provider


def test_position_tick_updates_active_position_and_account_pnl(tmp_path):
    provider = make_provider(FakeOpenAlgoClient({}))
    snapshot_path = tmp_path / "dashboard_data.json"
    snapshot_path.write_text(json.dumps({
        "timestamp": "2026-11-20T10:00:00",
        "positions": [
            {"symbol": "NIFTY26NOV25000CE", "exchange": "NFO", "quantity": "50", "ltp": 100, "pnl": 250},
            {"symbol": "FLAT", "exchange": "NSE", "quantity": "0", "ltp": 20, "pnl": 0},
        ],
        "account": {"mtm": 500, "pnl": 500},
    }))

    assert provider.write_position_tick("NIFTY26NOV25000CE", 103, str(snapshot_path))

    snapshot = json.loads(snapshot_path.read_text())
    assert snapshot["positions"][0]["ltp"] == 103
    assert snapshot["positions"][0]["pnl"] == 400
    assert snapshot["positions"][1]["ltp"] == 20
    assert snapshot["account"]["mtm"] == 650
    assert snapshot["account"]["pnl"] == 650


def test_openalgo_funds_fields_are_normalized_for_dashboard():
    provider = make_provider(FakeOpenAlgoClient({
        "status": "success",
        "data": {
            "availablecash": "10000000",
            "m2munrealized": "125.5",
            "m2mrealized": "-10",
            "utiliseddebits": "500",
        },
    }))

    account = provider._fetch_account_info()

    assert account["source"] == "openalgo"
    assert account["available_balance"] == 10000000
    assert account["availableMargin"] == 10000000
    assert account["margin"] == 10000000
    assert account["mtm"] == 125.5
    assert account["pnl"] == 125.5
    assert account["realized_pnl"] == -10
    assert account["used_margin"] == 500


def test_openalgo_funds_accept_already_normalized_fields_and_zero_values():
    provider = make_provider(FakeOpenAlgoClient({
        "data": {
            "availableMargin": 0,
            "mtm": 0,
            "used_margin": 0,
        },
    }))

    account = provider._fetch_account_info()

    assert account["availableMargin"] == 0
    assert account["mtm"] == 0
    assert account["used_margin"] == 0


def test_openalgo_funds_failure_is_not_replaced_with_mock_account():
    provider = make_provider(FakeOpenAlgoClient({"status": False, "message": "unauthorized"}))

    with pytest.raises(RuntimeError, match="Could not fetch funds from OpenAlgo"):
        provider._fetch_account_info()


def test_provider_rejects_missing_or_placeholder_api_key():
    with pytest.raises(RuntimeError, match="OPENALGO_API_KEY"):
        DashboardDataProvider(api_key="YOUR_OPENALGO_API_KEY", host="http://localhost:5002")


def test_fetch_broker_name_reads_openalgo_ping(monkeypatch):
    provider = make_provider(FakeOpenAlgoClient({"data": {}}))
    provider.api_key = "test-key"
    provider.host = "http://openalgo.test"

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "success", "data": {"broker": "angel"}}

    def fake_post(url, json, timeout):
        assert url == "http://openalgo.test/api/v1/ping"
        assert json == {"apikey": "test-key"}
        assert timeout == 10
        return FakeResponse()

    monkeypatch.setattr(dashboard_data_module.requests, "post", fake_post)

    assert provider._fetch_broker_name() == "angel"


def test_fetch_broker_name_reports_missing_broker(monkeypatch, caplog):
    provider = make_provider(FakeOpenAlgoClient({"data": {}}))
    provider.api_key = "test-key"
    provider.host = "http://openalgo.test"

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "success", "data": {}}

    monkeypatch.setattr(dashboard_data_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    assert provider._fetch_broker_name() is None
    assert "did not include a broker name" in caplog.text
