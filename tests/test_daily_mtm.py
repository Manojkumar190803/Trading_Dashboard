from frontend._shared import _daily_mtm_value, _select_live_pnl


def test_daily_mtm_starts_at_zero_and_tracks_same_day_changes():
    state = {}

    assert _daily_mtm_value(1000.0, "2026-09-18", state) == 0.0
    assert _daily_mtm_value(1250.0, "2026-09-18", state) == 250.0
    assert _daily_mtm_value(900.0, "2026-09-18", state) == -100.0


def test_daily_mtm_resets_baseline_on_new_day():
    state = {}

    _daily_mtm_value(1000.0, "2026-09-18", state)

    assert _daily_mtm_value(1800.0, "2026-09-19", state) == 0.0
    assert _daily_mtm_value(1700.0, "2026-09-19", state) == -100.0


def test_live_pnl_prefers_position_book_for_open_positions():
    funds = {"realized_mtm": 13.0, "unrealized_mtm": 0.0}
    positions = [{"symbol": "NIFTY29SEP2623400CE", "quantity": 130, "pnl": 2340.0}]

    assert _select_live_pnl(funds, positions) == 2340.0


def test_live_pnl_uses_funds_when_no_positions_are_open():
    funds = {"realized_mtm": 13.0, "unrealized_mtm": 0.0}

    assert _select_live_pnl(funds, []) == 13.0