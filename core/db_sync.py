"""Best-effort PostgreSQL persistence for live trading data.

Every public function swallows its own errors so a database outage can never
interrupt order handling. Nothing is written unless DB_URL is configured.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger("core.db_sync")

_RETRY_AFTER_SECONDS = 30.0
_SNAPSHOT_MIN_INTERVAL = 10.0
_ACCOUNT_MIN_INTERVAL = 60.0

_init_lock = threading.Lock()
_next_init_attempt = 0.0
_executor: Optional[ThreadPoolExecutor] = None
_last_snapshot_at = 0.0
_last_account_at = 0.0
_OPTION_SYMBOL = re.compile(r"[A-Z]+\d{2}[A-Z]{3}\d{2}\d+(?:CE|PE)")


def _ready() -> bool:
    global _next_init_attempt
    if not os.getenv("DB_URL"):
        return False
    from core.db_connection import DatabaseConnection, init_db_connection

    if DatabaseConnection.is_initialized():
        return True
    with _init_lock:
        if DatabaseConnection.is_initialized():
            return True
        if time.monotonic() < _next_init_attempt:
            return False
        try:
            init_db_connection()
            return True
        except Exception as exc:
            _next_init_attempt = time.monotonic() + _RETRY_AFTER_SECONDS
            logger.warning("database unavailable, retrying in %ss: %s", int(_RETRY_AFTER_SECONDS), exc)
            return False


def _submit(function, *args) -> None:
    global _executor
    if not os.getenv("DB_URL"):
        return
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db-sync")
    _executor.submit(_safe, function, *args)


def _safe(function, *args) -> None:
    try:
        if _ready():
            function(*args)
    except Exception:
        logger.exception("database write failed: %s", getattr(function, "__name__", function))


def _decimal(value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    try:
        if value is None or value == "":
            return default
        return Decimal(str(round(float(value), 2)))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return datetime.now()


# ── engine hooks (run on a background thread) ─────────────────────────

def save_alert(strategy_name: str, ts: datetime, category: str, message: str) -> None:
    _submit(_write_alert, strategy_name, ts, category, message)


def _write_alert(strategy_name: str, ts: datetime, category: str, message: str) -> None:
    from core.db_utils import record_log

    if category in {"ERROR", "FAILED"}:
        level = "ERROR"
    elif category in {"RISK", "REJECT", "UNCERTAIN_ENTRY", "CANCEL"}:
        level = "WARNING"
    else:
        level = "INFO"
    match = _OPTION_SYMBOL.search(message)
    record_log(
        level=level,
        category=category,
        message=message,
        symbol=match.group(0) if match else None,
        strategy_name=strategy_name,
        timestamp=_parse_time(ts),
    )


def save_exit_trade(
    strategy_name: str,
    symbol: str,
    entry_time: datetime,
    entry_price: float,
    exit_time: datetime,
    exit_price: float,
    quantity: int,
    pnl: float,
    remaining_quantity: int,
    is_hard_sl: bool,
    reason: str,
    initial_sl_points: Optional[float],
    trailing_step_rr: Optional[float],
) -> None:
    _submit(
        _write_exit_trade, strategy_name, symbol, entry_time, entry_price, exit_time,
        exit_price, quantity, pnl, remaining_quantity, is_hard_sl, reason,
        initial_sl_points, trailing_step_rr,
    )


def _write_exit_trade(
    strategy_name, symbol, entry_time, entry_price, exit_time, exit_price, quantity,
    pnl, remaining_quantity, is_hard_sl, reason, initial_sl_points, trailing_step_rr,
) -> None:
    from core.db_utils import record_trade

    if remaining_quantity > 0:
        status = "PARTIAL_EXIT"
    elif is_hard_sl:
        status = "SL_HIT"
    else:
        status = "EXIT"
    cost = entry_price * quantity
    record_trade(
        strategy_name=strategy_name,
        symbol=symbol,
        entry_time=_parse_time(entry_time),
        entry_price=entry_price,
        entry_qty=quantity,
        entry_side="BUY",
        exit_time=_parse_time(exit_time),
        exit_price=exit_price,
        exit_qty=quantity,
        pnl=pnl,
        pnl_percentage=round(pnl / cost * 100, 2) if cost else None,
        status=status,
        initial_sl_points=initial_sl_points,
        trailing_step_rr=trailing_step_rr,
        notes=reason,
    )


def save_strategy_config(strategy_name: str, cfg: Any, risk: Any) -> None:
    payload = asdict(cfg) if is_dataclass(cfg) else dict(vars(cfg))
    payload["max_sl_per_day"] = getattr(risk, "max_sl_per_day", None)
    _submit(_write_strategy_config, strategy_name, str(cfg.option_index_symbol), payload)


def _write_strategy_config(strategy_name: str, symbol: str, payload: dict) -> None:
    from core.db_connection import DatabaseSession
    from core.db_models import StrategyConfig

    with DatabaseSession() as session:
        row = session.query(StrategyConfig).filter_by(strategy_name=strategy_name, symbol=symbol).first()
        if row is None:
            row = StrategyConfig(strategy_name=strategy_name, symbol=symbol, config_json="{}")
            session.add(row)
        row.config_json = json.dumps(payload, default=str)
        row.initial_sl_points = payload.get("max_option_risk_points")
        row.trailing_step_rr = payload.get("trailing_step_rr")
        row.max_positions = payload.get("max_losing_trades_per_day")
        row.is_active = True


# ── broker snapshot sync (called by the dashboard exporter) ───────────

def sync_dashboard_snapshot(data: dict) -> None:
    """Mirror the broker snapshot into orders, positions, account_summary and daily_pnl."""
    global _last_snapshot_at, _last_account_at
    if not os.getenv("DB_URL"):
        return
    now = time.monotonic()
    if now - _last_snapshot_at < _SNAPSHOT_MIN_INTERVAL:
        return
    _last_snapshot_at = now
    include_account = now - _last_account_at >= _ACCOUNT_MIN_INTERVAL
    if include_account:
        _last_account_at = now
    _safe(_write_snapshot, data, include_account)


def _write_snapshot(data: dict, include_account: bool) -> None:
    orders_data = data.get("orders") or []
    orders = orders_data.get("orders", []) if isinstance(orders_data, dict) else orders_data
    positions = [p for p in (data.get("positions") or []) if isinstance(p, dict)]
    orders = [o for o in orders if isinstance(o, dict)]
    _upsert_orders(orders)
    _upsert_positions(positions, orders)
    _write_daily_total(data)
    if include_account:
        _write_account(data.get("account") or {}, positions)


def _upsert_orders(orders: list[dict]) -> None:
    from core.db_connection import DatabaseSession
    from core.db_models import Order, OrderSide, OrderStatus

    order_ids = [str(o.get("orderid") or o.get("order_id") or "") for o in orders]
    order_ids = [i for i in order_ids if i]
    if not order_ids:
        return
    status_map = {
        "complete": OrderStatus.FILLED,
        "completed": OrderStatus.FILLED,
        "cancelled": OrderStatus.CANCELLED,
        "canceled": OrderStatus.CANCELLED,
        "rejected": OrderStatus.REJECTED,
    }
    with DatabaseSession() as session:
        existing = {
            row.broker_order_id: row
            for row in session.query(Order).filter(Order.broker_order_id.in_(order_ids)).all()
        }
        for order in orders:
            order_id = str(order.get("orderid") or order.get("order_id") or "")
            if not order_id:
                continue
            quantity = int(_float(order.get("quantity")))
            filled = int(_float(order.get("filled_quantity")))
            status = status_map.get(str(order.get("order_status", "")).lower())
            if status is None:
                status = OrderStatus.PARTIAL_FILL if 0 < filled < quantity else OrderStatus.PENDING
            price = _float(order.get("price")) or _float(order.get("trigger_price")) or _float(order.get("average_price"))
            row = existing.get(order_id)
            if row is None:
                order_time = _parse_time(order.get("timestamp"))
                row = Order(
                    broker_order_id=order_id,
                    strategy_name=str(order.get("strategy") or "UNKNOWN")[:100],
                    symbol=str(order.get("symbol") or "")[:50],
                    side=OrderSide.SELL if str(order.get("action", "")).upper() == "SELL" else OrderSide.BUY,
                    qty=quantity,
                    order_price=_decimal(price, Decimal("0")),
                    order_type=str(order.get("pricetype") or "MARKET")[:20],
                    order_time=order_time,
                    status=status,
                )
                session.add(row)
            row.filled_qty = filled
            row.filled_price = _decimal(order.get("average_price")) if filled else None
            row.status = status
            row.rejection_reason = str(order.get("rejection_reason") or "") or None
            if status in (OrderStatus.FILLED, OrderStatus.PARTIAL_FILL) and row.fill_time is None:
                row.fill_time = _parse_time(order.get("timestamp"))


def _upsert_positions(positions: list[dict], orders: list[dict]) -> None:
    from sqlalchemy import func

    from core.db_connection import DatabaseSession
    from core.db_models import OrderSide, Position

    strategy_by_symbol = {
        str(o.get("symbol")): str(o.get("strategy"))
        for o in orders
        if o.get("symbol") and o.get("strategy")
    }
    today = date.today()
    open_symbols: set[str] = set()
    with DatabaseSession() as session:
        for position in positions:
            symbol = str(position.get("symbol") or "")
            if not symbol:
                continue
            quantity = int(_float(position.get("quantity")))
            is_open = quantity != 0
            if is_open:
                open_symbols.add(symbol)
            row = session.query(Position).filter(
                Position.symbol == symbol,
                func.date(Position.opened_at) == today,
            ).order_by(Position.id.desc()).first()
            average = _decimal(position.get("average_price"), Decimal("0"))
            pnl = _decimal(position.get("pnl"), Decimal("0"))
            if row is None:
                row = Position(
                    strategy_name=strategy_by_symbol.get(symbol, "BROKER")[:100],
                    symbol=symbol[:50],
                    qty=abs(quantity),
                    side=OrderSide.SELL if quantity < 0 else OrderSide.BUY,
                    entry_price=average,
                    is_active=is_open,
                )
                session.add(row)
            if is_open:
                row.qty = abs(quantity)
                row.is_active = True
                row.closed_at = None
                row.unrealized_pnl = pnl
            else:
                row.is_active = False
                row.realized_pnl = pnl
                row.unrealized_pnl = None
                row.closed_at = row.closed_at or datetime.utcnow()
            row.current_price = _decimal(position.get("ltp")) or row.current_price
        stale = session.query(Position).filter(Position.is_active.is_(True))
        if open_symbols:
            stale = stale.filter(~Position.symbol.in_(open_symbols))
        for row in stale.all():
            row.is_active = False
            row.closed_at = datetime.utcnow()


def _write_daily_total(data: dict) -> None:
    from core.dashboard_data import _extract_daily_pnl_snapshot_data
    from core.db_utils import record_daily_pnl

    today = date.today()
    pnl, trades, has_data = _extract_daily_pnl_snapshot_data(data, today)
    if not has_data:
        return
    values = [
        _float(p.get("pnl"))
        for p in (data.get("positions") or [])
        if isinstance(p, dict) and p.get("pnl") is not None
    ]
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    record_daily_pnl(
        strategy_name="ALL",
        trade_date=datetime.combine(today, datetime.min.time()),
        total_trades=trades,
        winning_trades=len(wins),
        losing_trades=len(losses),
        gross_pnl=pnl,
        net_pnl=pnl,
        win_rate=round(len(wins) / len(values) * 100, 2) if values else None,
        avg_win=sum(wins) / len(wins) if wins else None,
        avg_loss=sum(losses) / len(losses) if losses else None,
        best_trade=max(values) if values else None,
        worst_trade=min(values) if values else None,
    )


def _write_account(account: dict, positions: list[dict]) -> None:
    from core.db_connection import DatabaseSession
    from core.db_models import AccountSummary

    available = _float(account.get("available_balance") or account.get("availablecash"))
    used = _float(account.get("used_margin") or account.get("utiliseddebits"))
    with DatabaseSession() as session:
        session.add(AccountSummary(
            total_balance=_decimal(available + used),
            available_balance=_decimal(available),
            blocked_balance=_decimal(account.get("collateral"), Decimal("0")),
            total_margin=_decimal(available + used),
            available_margin=_decimal(account.get("available_margin") or available),
            used_margin=_decimal(used),
            mtm=_decimal(account.get("mtm"), Decimal("0")),
            unrealized_pnl=_decimal(account.get("m2munrealized"), Decimal("0")),
            realized_pnl=_decimal(account.get("realized_pnl") or account.get("m2mrealized"), Decimal("0")),
            open_positions_count=sum(1 for p in positions if _float(p.get("quantity")) != 0),
            buying_power=_decimal(available),
        ))
