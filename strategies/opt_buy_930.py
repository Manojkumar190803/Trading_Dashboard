from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class OptionCandidate:
    symbol: str
    side: str
    strike: int
    premium: float
    tradable: bool = True


@dataclass(frozen=True)
class OptBuy930Config:
    reference_premium: float = 180.0
    max_selection_distance: float = 10.0
    sustain_seconds: float = 10.0
    stop_loss_points: float = 20.0
    target_points: float = 40.0
    quantity: int = 130
    lot_size: int = 65
    tick_size: float = 0.05
    signal_start: time = time(9, 30)
    signal_cutoff: time = time(9, 45)
    profit_check_time: time = time(9, 45)
    hard_exit_time: time = time(10, 0)

    def validate(self) -> None:
        if self.quantity <= 0 or self.lot_size <= 0 or self.quantity % self.lot_size:
            raise ValueError("quantity must be a positive multiple of lot_size")
        if self.sustain_seconds <= 0:
            raise ValueError("sustain_seconds must be positive")
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")
        if self.stop_loss_points <= 0 or self.target_points <= 0:
            raise ValueError("SL and target points must be positive")

    def round_price(self, price: float) -> float:
        steps = round(price / self.tick_size)
        return round(steps * self.tick_size, 10)


@dataclass
class ConfirmationState:
    started_at: Optional[datetime] = None
    last_tick_at: Optional[datetime] = None

    def reset(self) -> None:
        self.started_at = None
        self.last_tick_at = None


@dataclass
class TradeResult:
    side: str
    symbol: str
    quantity: int
    entry_time: datetime
    entry_price: float
    stop_loss: float
    target: float
    exit_time: datetime
    exit_price: float
    exit_reason: str

    @property
    def gross_pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.quantity


@dataclass
class OptBuy930State:
    selected: dict[str, OptionCandidate] = field(default_factory=dict)
    confirmation: dict[str, ConfirmationState] = field(
        default_factory=lambda: {"CE": ConfirmationState(), "PE": ConfirmationState()}
    )
    trade: Optional[TradeResult] = None
    entry_locked: bool = False
    session_status: str = "UNINITIALIZED"


def select_watchlist(
    candidates: Iterable[OptionCandidate],
    config: OptBuy930Config,
) -> dict[str, OptionCandidate]:
    config.validate()
    selected: dict[str, OptionCandidate] = {}
    for candidate in candidates:
        side = candidate.side.upper()
        if side not in ("CE", "PE") or not candidate.tradable:
            continue
        if candidate.premium <= 0:
            continue
        distance = abs(candidate.premium - config.reference_premium)
        current = selected.get(side)
        if distance > config.max_selection_distance:
            continue
        if current is None or (distance, candidate.strike, candidate.symbol) < (
            abs(current.premium - config.reference_premium),
            current.strike,
            current.symbol,
        ):
            selected[side] = candidate
    if set(selected) != {"CE", "PE"}:
        raise ValueError("both CE and PE require a valid candidate within selection range")
    return selected


class OptBuy930Strategy:
    def __init__(self, config: Optional[OptBuy930Config] = None) -> None:
        self.config = config or OptBuy930Config()
        self.config.validate()
        self.state = OptBuy930State()

    def scan(self, candidates: Iterable[OptionCandidate]) -> dict[str, OptionCandidate]:
        if self.state.session_status != "UNINITIALIZED":
            raise RuntimeError("scan may run only once per session")
        self.state.selected = select_watchlist(candidates, self.config)
        self.state.session_status = "WATCHING"
        return dict(self.state.selected)

    def process_tick(self, side: str, price: float, timestamp: datetime) -> Optional[TradeResult]:
        side = side.upper()
        if side not in ("CE", "PE") or price <= 0 or side not in self.state.selected:
            return None
        if self.state.trade is not None or self.state.entry_locked:
            return self.state.trade
        if not self.config.signal_start <= timestamp.time() < self.config.signal_cutoff:
            return None
        confirmation = self.state.confirmation[side]
        if price <= self.config.reference_premium:
            confirmation.reset()
            return None
        if confirmation.started_at is None:
            confirmation.started_at = timestamp
        confirmation.last_tick_at = timestamp
        elapsed = (timestamp - confirmation.started_at).total_seconds()
        if elapsed < self.config.sustain_seconds:
            return None
        self.state.entry_locked = True
        entry_price = self.config.round_price(price)
        self.state.trade = TradeResult(
            side=side,
            symbol=self.state.selected[side].symbol,
            quantity=self.config.quantity,
            entry_time=timestamp,
            entry_price=entry_price,
            stop_loss=self.config.round_price(entry_price - self.config.stop_loss_points),
            target=self.config.round_price(entry_price + self.config.target_points),
            exit_time=timestamp,
            exit_price=entry_price,
            exit_reason="ACTIVE",
        )
        self.state.session_status = "ACTIVE"
        return self.state.trade

    def process_position_tick(self, price: float, timestamp: datetime) -> Optional[TradeResult]:
        trade = self.state.trade
        if trade is None or trade.exit_reason != "ACTIVE":
            return trade
        if price <= trade.stop_loss:
            return self._close(price, timestamp, "STOP_LOSS")
        if price >= trade.target:
            return self._close(price, timestamp, "TARGET")
        return trade

    def process_time(self, price: float, timestamp: datetime) -> Optional[TradeResult]:
        trade = self.state.trade
        if trade is None or trade.exit_reason != "ACTIVE":
            return trade
        if timestamp.time() >= self.config.hard_exit_time:
            return self._close(price, timestamp, "HARD_EXIT")
        if timestamp.time() >= self.config.profit_check_time and price <= trade.entry_price:
            return self._close(price, timestamp, "09:45_EXIT")
        return trade

    def _close(self, price: float, timestamp: datetime, reason: str) -> TradeResult:
        trade = self.state.trade
        if trade is None:
            raise RuntimeError("cannot close without a trade")
        trade.exit_price = self.config.round_price(price)
        trade.exit_time = timestamp
        trade.exit_reason = reason
        self.state.session_status = "TRADE_CLOSED"
        return trade


def _parse_tick(row: dict[str, str]) -> tuple[str, float, datetime]:
    return row["side"].upper(), float(row["price"]), datetime.fromisoformat(row["timestamp"])


def run_backtest(
    candidates: Iterable[OptionCandidate],
    ticks: Iterable[tuple[str, float, datetime]],
    config: Optional[OptBuy930Config] = None,
) -> Optional[TradeResult]:
    strategy = OptBuy930Strategy(config)
    strategy.scan(candidates)
    ordered_ticks = sorted(list(ticks), key=lambda item: item[2])
    for side, price, timestamp in ordered_ticks:
        if strategy.state.trade is None:
            strategy.process_tick(side, price, timestamp)
        else:
            strategy.process_position_tick(price, timestamp)
            strategy.process_time(price, timestamp)
        if strategy.state.trade and strategy.state.trade.exit_reason != "ACTIVE":
            return strategy.state.trade
    if strategy.state.trade and strategy.state.trade.exit_reason == "ACTIVE":
        if ordered_ticks:
            last = ordered_ticks[-1]
            strategy.process_time(last[1], last[2])
    return strategy.state.trade


def write_results(trade: Optional[TradeResult], csv_path: str, txt_path: str) -> None:
    fields = ["side", "symbol", "quantity", "entry_time", "entry_price", "stop_loss", "target", "exit_time", "exit_price", "exit_reason", "gross_pnl"]
    row = None if trade is None else {field: getattr(trade, field) if field != "gross_pnl" else trade.gross_pnl for field in fields}
    with Path(csv_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        if row is not None:
            writer.writerow(row)
    with Path(txt_path).open("w", encoding="utf-8") as handle:
        handle.write("\t".join(fields) + "\n")
        if row is not None:
            handle.write("\t".join(str(row[field]) for field in fields) + "\n")


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Backtest the 9:30 OPT-Buy strategy")
    parser.add_argument("--candidates", required=True, help="CSV: symbol,side,strike,premium[,tradable]")
    parser.add_argument("--ticks", required=True, help="CSV: timestamp,side,price")
    parser.add_argument("--csv", default="opt_buy_930_trades.csv")
    parser.add_argument("--txt", default="opt_buy_930_trades.txt")
    parser.add_argument("--quantity", type=int, default=130)
    parser.add_argument("--sustain-seconds", type=float, default=10.0)
    args = parser.parse_args()
    candidates: list[OptionCandidate] = []
    with Path(args.candidates).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            candidates.append(OptionCandidate(row["symbol"], row["side"], int(row["strike"]), float(row["premium"]), row.get("tradable", "true").lower() == "true"))
    ticks: list[tuple[str, float, datetime]] = []
    with Path(args.ticks).open(newline="", encoding="utf-8") as handle:
        ticks.extend(_parse_tick(row) for row in csv.DictReader(handle))
    config = OptBuy930Config(quantity=args.quantity, sustain_seconds=args.sustain_seconds)
    trade = run_backtest(candidates, ticks, config)
    write_results(trade, args.csv, args.txt)
    print("No trade" if trade is None else f"{trade.side} {trade.symbol} {trade.exit_reason} PnL={trade.gross_pnl:.2f}")


if __name__ == "__main__":
    _cli()
