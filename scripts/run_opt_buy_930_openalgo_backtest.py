from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd

from core.broker import OpenAlgoBroker
from strategies.opt_buy_930 import OptionCandidate, OptBuy930Config, TradeResult, run_backtest, select_watchlist


IST_START = time(9, 20)
IST_END = time(10, 1)


def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def normalize_history(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    frame.columns = [str(column).lower() for column in frame.columns]
    for candidate in ("timestamp", "time", "date"):
        if "datetime" not in frame.columns and candidate in frame.columns:
            frame = frame.rename(columns={candidate: "datetime"})
    if "datetime" not in frame.columns:
        raise RuntimeError("history is missing datetime")
    frame["datetime"] = pd.to_datetime(frame["datetime"]).dt.tz_localize(None)
    required = {"datetime", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise RuntimeError(f"history is missing columns: {sorted(missing)}")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.dropna(subset=["datetime", "close"]).sort_values("datetime").reset_index(drop=True)


def trading_days(frame: pd.DataFrame) -> list[date]:
    return sorted({stamp.date() for stamp in frame["datetime"] if stamp.weekday() < 5})


def day_window(frame: pd.DataFrame, day: date) -> pd.DataFrame:
    return frame[(frame["datetime"].dt.date == day) & (frame["datetime"].dt.time >= IST_START) & (frame["datetime"].dt.time <= IST_END)]


def build_symbol(root: str, expiry: date, strike: int, side: str) -> str:
    return f"{root}{expiry.strftime('%d%b%y').upper()}{strike}{side}"


def fetch_history(broker: OpenAlgoBroker, symbol: str, exchange: str, start: str, end: str) -> pd.DataFrame:
    return normalize_history(broker.fetch_history(symbol, exchange, "1m", start, end))


def run_openalgo_backtest(start: str, end: str, output_csv: str, output_txt: str, strikes_each_side: int = 8) -> list[TradeResult]:
    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        raise SystemExit("OPENALGO_API_KEY not set (check .env)")
    host = os.getenv("OPENALGO_HOST") or os.getenv("OPENALGO_URL") or "http://127.0.0.1:5002"
    broker = OpenAlgoBroker(api_key=api_key, host=host, dry_run=True)
    profile = broker.discover_index_profile("NIFTY")
    spot = fetch_history(broker, str(profile["spot_symbol"]), str(profile["exchange_spot"]), start, end)
    config = OptBuy930Config(quantity=130, lot_size=int(profile["option_lot_size"]))
    results: list[TradeResult] = []

    for day in trading_days(spot):
        spot_day = day_window(spot, day)
        spot_at_scan = spot_day[spot_day["datetime"].dt.time >= time(9, 25)]
        if spot_at_scan.empty:
            continue
        spot_price = float(spot_at_scan.iloc[0]["close"])
        strike_step = int(profile["strike_step"])
        atm = int(round(spot_price / strike_step) * strike_step)
        expiry = broker.resolve_nearest_expiry(
            str(profile["option_index_symbol"]), day, atm, strike_step, int(profile["weekly_expiry_weekday"])
        )
        if expiry is None:
            continue

        candidate_data: list[tuple[OptionCandidate, pd.DataFrame]] = []
        for offset in range(-strikes_each_side, strikes_each_side + 1):
            strike = atm + offset * strike_step
            for side in ("CE", "PE"):
                symbol = build_symbol(str(profile["option_index_symbol"]), expiry, strike, side)
                try:
                    history = fetch_history(broker, symbol, str(profile["exchange_options"]), start, end)
                except Exception:
                    continue
                scan_rows = history[(history["datetime"].dt.date == day) & (history["datetime"].dt.time >= time(9, 25))]
                if scan_rows.empty:
                    continue
                premium = float(scan_rows.iloc[0]["close"])
                candidate_data.append((OptionCandidate(symbol, side, strike, premium), history))

        candidates = [candidate for candidate, _ in candidate_data]
        try:
            selected_candidates = select_watchlist(candidates, config)
        except (StopIteration, ValueError):
            continue

        histories = {candidate.symbol: history for candidate, history in candidate_data}
        ticks: list[tuple[str, float, datetime]] = []
        for side, candidate in selected_candidates.items():
            history = histories[candidate.symbol]
            rows = day_window(history, day)
            for _, row in rows[rows["datetime"].dt.time >= config.signal_start].iterrows():
                ticks.append((side, float(row["close"]), row["datetime"].to_pydatetime()))
        trade = run_backtest(selected_candidates.values(), ticks, config)
        if trade is not None:
            results.append(trade)

    if output_csv is not None and output_txt is not None:
        fields = ["side", "symbol", "quantity", "entry_time", "entry_price", "stop_loss", "target", "exit_time", "exit_price", "exit_reason", "gross_pnl"]
        with Path(output_csv).open("w", encoding="utf-8", newline="") as handle:
            handle.write(",".join(fields) + "\n")
            for trade in results:
                handle.write(",".join(str(getattr(trade, field) if field != "gross_pnl" else trade.gross_pnl) for field in fields) + "\n")
        with Path(output_txt).open("w", encoding="utf-8") as handle:
            handle.write("\t".join(fields) + "\n")
            for trade in results:
                handle.write("\t".join(str(getattr(trade, field) if field != "gross_pnl" else trade.gross_pnl) for field in fields) + "\n")
    return results


def main() -> None:
    load_environment()
    parser = argparse.ArgumentParser(description="One-week OpenAlgo 1-minute approximation backtest for 9:30 OPT-Buy")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--csv", default="logs/opt_buy_930_week.csv")
    parser.add_argument("--txt", default="logs/opt_buy_930_week.txt")
    parser.add_argument("--terminal-only", action="store_true", help="Print the tradebook without creating output files")
    parser.add_argument("--strikes-each-side", type=int, default=8)
    args = parser.parse_args()
    output_csv = None if args.terminal_only else args.csv
    output_txt = None if args.terminal_only else args.txt
    results = run_openalgo_backtest(args.start, args.end, output_csv, output_txt, args.strikes_each_side)
    fields = ["side", "symbol", "quantity", "entry_time", "entry_price", "stop_loss", "target", "exit_time", "exit_price", "exit_reason", "gross_pnl"]
    print("\t".join(fields))
    for trade in results:
        print("\t".join(str(getattr(trade, field) if field != "gross_pnl" else trade.gross_pnl) for field in fields))
    print(f"Trades: {len(results)}")
    print(f"Gross PnL (INR): {sum(trade.gross_pnl for trade in results):.2f}")


if __name__ == "__main__":
    main()
