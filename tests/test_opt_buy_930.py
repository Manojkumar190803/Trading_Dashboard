from datetime import datetime
import sys
import runpy

import pytest

from strategies.opt_buy_930 import (
    OptionCandidate,
    OptBuy930Config,
    OptBuy930Strategy,
    run_backtest,
    select_watchlist,
    write_results,
)


def candidate_set():
    return [
        OptionCandidate("CE-ATM", "CE", 24450, 181.0),
        OptionCandidate("CE-OTM", "CE", 24500, 180.5),
        OptionCandidate("PE-ATM", "PE", 24450, 179.0),
        OptionCandidate("PE-BAD", "PE", 24350, 175.0),
    ]


def ts(seconds: int, minute: int = 30):
    return datetime(2026, 8, 24, 9, minute, seconds)


def test_selection_prefers_closest_valid_candidate_per_side():
    selected = select_watchlist(candidate_set(), OptBuy930Config())
    assert selected["CE"].symbol == "CE-OTM"
    assert selected["PE"].symbol == "PE-ATM"


def test_selection_rejects_missing_side_and_invalid_config():
    with pytest.raises(ValueError, match="both CE and PE"):
        select_watchlist([candidate_set()[0]], OptBuy930Config())
    with pytest.raises(ValueError, match="multiple of lot_size"):
        OptBuy930Strategy(OptBuy930Config(quantity=131))
    with pytest.raises(ValueError, match="sustain_seconds"):
        OptBuy930Strategy(OptBuy930Config(sustain_seconds=0))
    with pytest.raises(ValueError, match="tick_size"):
        OptBuy930Strategy(OptBuy930Config(tick_size=0))
    with pytest.raises(ValueError, match="SL and target"):
        OptBuy930Strategy(OptBuy930Config(stop_loss_points=0))
    with pytest.raises(ValueError, match="both CE and PE"):
        select_watchlist(
            [
                OptionCandidate("BAD", "XX", 1, 180),
                OptionCandidate("CLOSED", "CE", 1, 180, False),
                OptionCandidate("ZERO", "CE", 1, 0),
                OptionCandidate("FAR", "CE", 1, 100),
            ],
            OptBuy930Config(),
        )


def test_confirmation_requires_ten_seconds_and_resets_at_threshold():
    strategy = OptBuy930Strategy()
    strategy.scan(candidate_set())
    assert strategy.process_tick("CE", 180.1, ts(0)) is None
    assert strategy.process_tick("CE", 180.0, ts(5)) is None
    assert strategy.process_tick("CE", 180.1, ts(6)) is None
    trade = strategy.process_tick("CE", 181.0, ts(16))
    assert trade is not None
    assert trade.entry_price == 181.0
    assert trade.quantity == 130


def test_scan_is_single_use_and_inactive_operations_are_idempotent():
    strategy = OptBuy930Strategy()
    strategy.scan(candidate_set())
    with pytest.raises(RuntimeError, match="once"):
        strategy.scan(candidate_set())
    assert strategy.process_position_tick(180, ts(0)) is None
    assert strategy.process_time(180, ts(0)) is None
    assert strategy.process_tick("CE", 0, ts(0)) is None


def test_ticks_outside_signal_window_do_not_enter():
    strategy = OptBuy930Strategy()
    strategy.scan(candidate_set())
    assert strategy.process_tick("CE", 181, datetime(2026, 8, 24, 9, 29, 59)) is None
    assert strategy.process_tick("CE", 181, datetime(2026, 8, 24, 9, 45)) is None


def test_first_confirmed_side_locks_out_other_side():
    strategy = OptBuy930Strategy(OptBuy930Config(sustain_seconds=1))
    strategy.scan(candidate_set())
    assert strategy.process_tick("PE", 181, ts(0)) is None
    trade = strategy.process_tick("PE", 181, ts(1))
    assert trade is not None and trade.side == "PE"
    assert strategy.process_tick("CE", 181, ts(2)) is trade


def test_position_stop_target_and_time_exits():
    stop_strategy = OptBuy930Strategy(OptBuy930Config(sustain_seconds=1))
    stop_strategy.scan(candidate_set())
    stop_strategy.process_tick("CE", 181, ts(0))
    trade = stop_strategy.process_tick("CE", 181, ts(1))
    assert stop_strategy.process_position_tick(160, ts(2)).exit_reason == "STOP_LOSS"
    assert trade.stop_loss == 161.0 and trade.target == 221.0

    target_strategy = OptBuy930Strategy(OptBuy930Config(sustain_seconds=1))
    target_strategy.scan(candidate_set())
    target_strategy.process_tick("CE", 181, ts(0))
    target_strategy.process_tick("CE", 181, ts(1))
    assert target_strategy.process_position_tick(221, ts(2)).exit_reason == "TARGET"

    time_strategy = OptBuy930Strategy(OptBuy930Config(sustain_seconds=1))
    time_strategy.scan(candidate_set())
    time_strategy.process_tick("CE", 181, ts(0))
    time_strategy.process_tick("CE", 181, ts(1))
    assert time_strategy.process_time(181, datetime(2026, 8, 24, 9, 45)).exit_reason == "09:45_EXIT"

    hold_strategy = OptBuy930Strategy(OptBuy930Config(sustain_seconds=1))
    hold_strategy.scan(candidate_set())
    hold_strategy.process_tick("CE", 181, ts(0))
    hold_strategy.process_tick("CE", 181, ts(1))
    assert hold_strategy.process_position_tick(200, ts(2)).exit_reason == "ACTIVE"
    assert hold_strategy.process_time(200, datetime(2026, 8, 24, 9, 45)).exit_reason == "ACTIVE"


def test_hard_exit_and_invalid_events():
    strategy = OptBuy930Strategy(OptBuy930Config(sustain_seconds=1))
    strategy.scan(candidate_set())
    strategy.process_tick("CE", 181, ts(0))
    strategy.process_tick("CE", 181, ts(1))
    assert strategy.process_time(200, datetime(2026, 8, 24, 10, 0)).exit_reason == "HARD_EXIT"
    assert strategy.process_tick("XX", 200, ts(2)) is None


def test_backtest_and_result_exports(tmp_path):
    trade = run_backtest(
        candidate_set(),
        [("CE", 180.1, ts(0)), ("CE", 181, ts(10)), ("CE", 221, ts(11))],
    )
    assert trade is not None and trade.exit_reason == "TARGET"
    csv_path, txt_path = tmp_path / "trade.csv", tmp_path / "trade.txt"
    write_results(trade, str(csv_path), str(txt_path))
    assert "gross_pnl" in csv_path.read_text()
    assert "\t" in txt_path.read_text()


def test_no_trade_is_exported():
    trade = run_backtest(candidate_set(), [])
    assert trade is None


def test_close_without_trade_is_rejected():
    with pytest.raises(RuntimeError, match="without a trade"):
        OptBuy930Strategy()._close(180, ts(0), "TEST")


def test_cli_reads_csv_and_writes_requested_outputs(tmp_path, monkeypatch, capsys):
    candidates = tmp_path / "candidates.csv"
    candidates.write_text("symbol,side,strike,premium,tradable\nCE,CE,24450,180,true\nPE,PE,24450,180,true\n")
    ticks = tmp_path / "ticks.csv"
    ticks.write_text("timestamp,side,price\n2026-08-24T09:30:00,CE,181\n2026-08-24T09:30:10,CE,181\n2026-08-24T09:30:11,CE,221\n")
    output_csv = tmp_path / "result.csv"
    output_txt = tmp_path / "result.txt"
    monkeypatch.setattr(sys, "argv", ["opt_buy_930", "--candidates", str(candidates), "--ticks", str(ticks), "--csv", str(output_csv), "--txt", str(output_txt)])
    from strategies.opt_buy_930 import _cli
    _cli()
    assert "TARGET" in capsys.readouterr().out
    assert output_csv.exists() and output_txt.exists()


def test_module_entrypoint(tmp_path, monkeypatch, capsys):
    candidates = tmp_path / "candidates.csv"
    candidates.write_text("symbol,side,strike,premium\nCE,CE,24450,180\nPE,PE,24450,180\n")
    ticks = tmp_path / "ticks.csv"
    ticks.write_text("timestamp,side,price\n2026-08-24T09:30:00,CE,181\n2026-08-24T09:30:10,CE,181\n")
    monkeypatch.setattr(sys, "argv", ["opt_buy_930", "--candidates", str(candidates), "--ticks", str(ticks)])
    runpy.run_module("strategies.opt_buy_930", run_name="__main__")
    assert "ACTIVE" in capsys.readouterr().out
