import pytest


@pytest.fixture(autouse=True)
def isolate_shared_sl_count(tmp_path, monkeypatch):
    monkeypatch.setenv("SHARED_SL_COUNT_FILE", str(tmp_path / "sl_hits.json"))