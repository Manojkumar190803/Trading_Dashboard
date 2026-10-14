import json
from datetime import datetime, timedelta

import api_server
from core.dashboard_data import _write_daily_pnl_snapshot


def test_daily_pnl_snapshot_replaces_same_day_and_retains_other_months(tmp_path):
    archive_path = tmp_path / "daily_pnl.json"

    assert _write_daily_pnl_snapshot(
        {
            "positions": [{"pnl": 100}, {"pnl": -25}],
            "orders": {"orders": [
                {"order_status": "complete", "timestamp": "2026-09-18 09:30:00"},
                {"order_status": "complete", "timestamp": "2026-09-18 10:00:00"},
                {"order_status": "rejected"},
            ]},
        },
        archive_path,
        datetime(2026, 9, 18, 10),
    )
    _write_daily_pnl_snapshot(
        {
            "positions": [{"pnl": 15}],
            "orders": {"orders": [{"order_status": "complete", "timestamp": "2026-09-18 10:30:00"}]},
        },
        archive_path,
        datetime(2026, 9, 18, 11),
    )
    _write_daily_pnl_snapshot(
        {
            "positions": [{"pnl": -5}],
            "orders": {"orders": [{"order_status": "complete", "timestamp": "2026-10-01 10:00:00"}]},
        },
        archive_path,
        datetime(2026, 10, 1, 10),
    )

    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    assert archive["2026-09"]["18"]["pnl"] == 15
    assert archive["2026-09"]["18"]["trades"] == 1
    assert archive["2026-10"]["1"]["pnl"] == -5


def test_snapshot_does_not_copy_yesterdays_orders_and_persists_today_zero(tmp_path):
    archive_path = tmp_path / "daily_pnl.json"
    archive_path.write_text(json.dumps({
        "2026-10": {"13": {"pnl": 5057, "trades": 4}},
    }), encoding="utf-8")

    assert _write_daily_pnl_snapshot(
        {
            "positions": [],
            "orders": {"orders": [
                {"order_status": "complete", "timestamp": "2026-10-13 14:00:00"},
            ]},
            "account": {"today_realized_pnl": 0, "realized_pnl": 5057},
        },
        archive_path,
        datetime(2026, 10, 14, 10),
    )

    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    assert archive["2026-10"]["13"]["pnl"] == 5057
    assert archive["2026-10"]["14"]["pnl"] == 0
    assert archive["2026-10"]["14"]["trades"] == 0


def test_live_analytics_overrides_stale_archive_with_valid_zero_day(tmp_path, monkeypatch):
    today = datetime.now()
    month_key = today.strftime("%Y-%m")
    day_key = str(today.day)
    archive_path = tmp_path / "daily_pnl.json"
    archive_path.write_text(json.dumps({
        month_key: {day_key: {"pnl": 5057, "trades": 4}},
    }), encoding="utf-8")
    dashboard_path = tmp_path / "dashboard_data.json"
    dashboard_path.write_text(json.dumps({
        "timestamp": today.isoformat(),
        "positions": [],
        "orders": {"orders": [
            {"order_status": "complete", "timestamp": (today - timedelta(days=1)).isoformat()},
        ]},
        "account": {"today_realized_pnl": 0, "realized_pnl": 5057},
    }), encoding="utf-8")
    monkeypatch.setattr(api_server, "DAILY_PNL_FILE", archive_path)
    monkeypatch.setattr(api_server, "DASHBOARD_DATA_FILE", dashboard_path)
    monkeypatch.setattr(api_server, "_load_daily_pnl_from_database", lambda year, month: {})

    response = api_server.app.test_client().get(
        f"/api/analytics/daily?year={today.year}&month={today.month}"
    )

    assert response.status_code == 200
    day = response.get_json()["days"][day_key]
    assert day["pnl"] == 0
    assert day["trades"] == 0


def test_daily_analytics_returns_requested_month_and_month_summary(tmp_path, monkeypatch):
    archive_path = tmp_path / "daily_pnl.json"
    archive_path.write_text(json.dumps({
        "2020-02": {
            "3": {"pnl": 120, "trades": 2},
            "11": {"pnl": -80, "trades": 1},
            "12": {"pnl": 900, "trades": 0},
        },
        "2020-03": {"1": {"pnl": 400, "trades": 1}},
    }), encoding="utf-8")
    monkeypatch.setattr(api_server, "DAILY_PNL_FILE", archive_path)
    monkeypatch.setattr(api_server, "DASHBOARD_DATA_FILE", tmp_path / "dashboard_data.json")
    monkeypatch.setattr(api_server, "_load_daily_pnl_from_database", lambda year, month: {})

    response = api_server.app.test_client().get("/api/analytics/daily?year=2020&month=2")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["month"] == "February 2020"
    assert payload["days"]["3"]["pnl"] == 120
    assert payload["month_summary"] == {
        "total_pnl": 40,
        "best_day": {"day": 3, "pnl": 120},
        "worst_day": {"day": 11, "pnl": -80},
        "winning_days": 1,
        "losing_days": 1,
        "total_trading_days": 2,
    }


def test_daily_analytics_reset_only_clears_selected_month(tmp_path, monkeypatch):
    archive_path = tmp_path / "daily_pnl.json"
    archive_path.write_text(json.dumps({
        "2020-02": {"3": {"pnl": 120, "trades": 2}},
        "2020-03": {"1": {"pnl": 400, "trades": 1}},
    }), encoding="utf-8")
    monkeypatch.setattr(api_server, "DAILY_PNL_FILE", archive_path)

    response = api_server.app.test_client().post("/api/analytics/daily/reset?year=2020&month=2")

    assert response.status_code == 200
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    assert archive["2020-02"] == {}
    assert archive["2020-03"]["1"]["pnl"] == 400