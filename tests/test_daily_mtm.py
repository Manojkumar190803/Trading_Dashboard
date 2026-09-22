from frontend._shared import _daily_mtm_value


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