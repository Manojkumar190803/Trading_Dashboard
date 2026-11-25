import json

import api_server


def test_test_trading_endpoint_deduplicates_identical_alerts(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    duplicate = {
        "id": "23-first",
        "timestamp": "2026-11-23T09:20:00",
        "execution_mode": "TEST",
        "instrument_id": "23",
        "instrument_name": "nifty",
        "strategy": "HD",
        "category": "RISK",
        "message": "HD contracts not locked",
    }
    duplicate_copy = {**duplicate, "id": "23-second"}
    lock = {**duplicate, "id": "23-third", "category": "ATM_LOCK", "message": "Contracts locked"}
    repeated_lock = {**lock, "id": "23-fourth", "timestamp": "2026-11-23T13:42:00"}
    (logs / "test_trading_23.json").write_text(json.dumps({
        "instrument_id": "23",
        "instrument_name": "nifty",
        "strategy": "HD",
        "execution_mode": "TEST",
        "alerts": [duplicate, duplicate_copy, lock, repeated_lock],
    }))

    response = api_server.app.test_client().get("/api/test-trading")

    assert response.status_code == 200
    alerts = response.get_json()["alerts"]
    assert [alert["id"] for alert in alerts] == ["23-first", "23-third"]
