"""
Database utility functions for recording trades, positions, orders, and logs.
Used by core/runner.py and core/engine.py to persist trading data.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

logger = logging.getLogger("core.db_utils")


def record_trade(
    strategy_name: str,
    symbol: str,
    entry_time: datetime,
    entry_price: float,
    entry_qty: int,
    entry_side: str,
    exit_time: Optional[datetime] = None,
    exit_price: Optional[float] = None,
    exit_qty: Optional[int] = None,
    pnl: Optional[float] = None,
    pnl_percentage: Optional[float] = None,
    status: str = "ENTRY",
    initial_sl_points: Optional[float] = None,
    breakeven_rr: Optional[float] = None,
    trailing_step_rr: Optional[float] = None,
    notes: Optional[str] = None,
):
    """
    Record a trade to the database.
    
    Args:
        strategy_name: Name of the strategy
        symbol: Trading symbol
        entry_time: Entry timestamp
        entry_price: Entry price
        entry_qty: Entry quantity
        entry_side: BUY or SELL
        exit_time: Exit timestamp (optional)
        exit_price: Exit price (optional)
        exit_qty: Exit quantity (optional)
        pnl: Profit/loss amount (optional)
        pnl_percentage: P&L percentage (optional)
        status: Trade status (ENTRY, EXIT, SL_HIT, etc.)
        initial_sl_points: Initial stop loss in points
        breakeven_rr: Breakeven milestone RR
        trailing_step_rr: Trailing step RR
        notes: Additional notes
    """
    try:
        from core.db_connection import DatabaseSession
        from core.db_models import Trade, TradeStatus
        
        with DatabaseSession() as session:
            trade = Trade(
                strategy_name=strategy_name,
                symbol=symbol,
                entry_time=entry_time,
                entry_price=Decimal(str(entry_price)),
                entry_qty=entry_qty,
                entry_side=entry_side,
                exit_time=exit_time,
                exit_price=Decimal(str(exit_price)) if exit_price else None,
                exit_qty=exit_qty,
                pnl=Decimal(str(pnl)) if pnl else None,
                pnl_percentage=pnl_percentage,
                status=TradeStatus(status) if status else TradeStatus.ENTRY,
                initial_sl_points=initial_sl_points,
                breakeven_rr=breakeven_rr,
                trailing_step_rr=trailing_step_rr,
                notes=notes,
                trade_date=entry_time,
            )
            session.add(trade)
            session.commit()
            
            logger.debug(f"✅ Recorded trade: {strategy_name} {symbol} @{entry_price}")
            return trade.id
    
    except Exception as e:
        logger.error(f"Failed to record trade: {e}")
        return None


def update_position(
    strategy_name: str,
    symbol: str,
    qty: int,
    side: str,
    entry_price: float,
    current_price: Optional[float] = None,
    sl_price: Optional[float] = None,
    tp_price: Optional[float] = None,
    unrealized_pnl: Optional[float] = None,
):
    """
    Update or create a position record.
    
    Args:
        strategy_name: Strategy name
        symbol: Trading symbol
        qty: Quantity
        side: BUY or SELL
        entry_price: Entry price
        current_price: Current market price
        sl_price: Stop loss price
        tp_price: Take profit price
        unrealized_pnl: Unrealized P&L
    """
    try:
        from core.db_connection import DatabaseSession
        from core.db_models import Position
        
        with DatabaseSession() as session:
            # Check if position exists
            position = session.query(Position).filter(
                Position.strategy_name == strategy_name,
                Position.symbol == symbol,
                Position.is_active == True
            ).first()
            
            if position:
                # Update existing position
                position.qty = qty
                position.current_price = Decimal(str(current_price)) if current_price else position.current_price
                position.sl_price = Decimal(str(sl_price)) if sl_price else position.sl_price
                position.tp_price = Decimal(str(tp_price)) if tp_price else position.tp_price
                position.unrealized_pnl = Decimal(str(unrealized_pnl)) if unrealized_pnl else position.unrealized_pnl
                session.commit()
                logger.debug(f"Updated position: {strategy_name} {symbol}")
            else:
                # Create new position
                position = Position(
                    strategy_name=strategy_name,
                    symbol=symbol,
                    qty=qty,
                    side=side,
                    entry_price=Decimal(str(entry_price)),
                    current_price=Decimal(str(current_price)) if current_price else Decimal(str(entry_price)),
                    sl_price=Decimal(str(sl_price)) if sl_price else None,
                    tp_price=Decimal(str(tp_price)) if tp_price else None,
                    unrealized_pnl=Decimal(str(unrealized_pnl)) if unrealized_pnl else None,
                    is_active=True,
                )
                session.add(position)
                session.commit()
                logger.debug(f"Created position: {strategy_name} {symbol}")
            
            return position.id
    
    except Exception as e:
        logger.error(f"Failed to update position: {e}")
        return None


def close_position(strategy_name: str, symbol: str, realized_pnl: float = 0):
    """Close an active position."""
    try:
        from core.db_connection import DatabaseSession
        from core.db_models import Position
        from datetime import datetime
        
        with DatabaseSession() as session:
            position = session.query(Position).filter(
                Position.strategy_name == strategy_name,
                Position.symbol == symbol,
                Position.is_active == True
            ).first()
            
            if position:
                position.is_active = False
                position.closed_at = datetime.utcnow()
                position.realized_pnl = Decimal(str(realized_pnl))
                session.commit()
                logger.debug(f"Closed position: {strategy_name} {symbol}")
                return True
        
        return False
    
    except Exception as e:
        logger.error(f"Failed to close position: {e}")
        return False


def record_log(
    level: str,
    category: str,
    message: str,
    symbol: Optional[str] = None,
    strategy_name: Optional[str] = None,
    trade_id: Optional[int] = None,
    order_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Record a log entry to the database.
    
    Args:
        level: Log level (INFO, WARNING, ERROR, ALERT)
        category: Log category (ENTRY, EXIT, SL, ALERT, etc.)
        message: Log message
        symbol: Trading symbol (optional)
        strategy_name: Strategy name (optional)
        trade_id: Associated trade ID (optional)
        order_id: Associated order ID (optional)
        metadata: Additional metadata as dict (optional)
    """
    try:
        from core.db_connection import DatabaseSession
        from core.db_models import Log
        import json
        
        with DatabaseSession() as session:
            log = Log(
                level=level,
                category=category,
                message=message,
                symbol=symbol,
                strategy_name=strategy_name,
                trade_id=trade_id,
                order_id=order_id,
                metadata_json=json.dumps(metadata) if metadata else None,
                timestamp=datetime.utcnow(),
            )
            session.add(log)
            session.commit()
            
            logger.debug(f"Recorded log: {level} {category} {symbol or 'N/A'}")
            return log.id
    
    except Exception as e:
        logger.error(f"Failed to record log: {e}")
        return None


def record_daily_pnl(
    strategy_name: str,
    trade_date: datetime,
    total_trades: int,
    winning_trades: int,
    losing_trades: int,
    gross_pnl: float,
    net_pnl: float,
    win_rate: Optional[float] = None,
    avg_win: Optional[float] = None,
    avg_loss: Optional[float] = None,
    best_trade: Optional[float] = None,
    worst_trade: Optional[float] = None,
):
    """Record daily P&L summary."""
    try:
        from core.db_connection import DatabaseSession
        from core.db_models import DailyPnL
        from sqlalchemy import func
        
        with DatabaseSession() as session:
            # Check if already exists for this date
            existing = session.query(DailyPnL).filter(
                DailyPnL.strategy_name == strategy_name,
                func.date(DailyPnL.trade_date) == trade_date.date()
            ).first()
            
            if existing:
                # Update
                existing.total_trades = total_trades
                existing.winning_trades = winning_trades
                existing.losing_trades = losing_trades
                existing.gross_pnl = Decimal(str(gross_pnl))
                existing.net_pnl = Decimal(str(net_pnl))
                existing.win_rate = win_rate
                existing.avg_win = Decimal(str(avg_win)) if avg_win else None
                existing.avg_loss = Decimal(str(avg_loss)) if avg_loss else None
                existing.best_trade = Decimal(str(best_trade)) if best_trade else None
                existing.worst_trade = Decimal(str(worst_trade)) if worst_trade else None
                session.commit()
                logger.debug(f"Updated daily P&L: {strategy_name} {trade_date.date()}")
            else:
                # Create
                daily_pnl = DailyPnL(
                    strategy_name=strategy_name,
                    trade_date=trade_date,
                    total_trades=total_trades,
                    winning_trades=winning_trades,
                    losing_trades=losing_trades,
                    gross_pnl=Decimal(str(gross_pnl)),
                    net_pnl=Decimal(str(net_pnl)),
                    win_rate=win_rate,
                    avg_win=Decimal(str(avg_win)) if avg_win else None,
                    avg_loss=Decimal(str(avg_loss)) if avg_loss else None,
                    best_trade=Decimal(str(best_trade)) if best_trade else None,
                    worst_trade=Decimal(str(worst_trade)) if worst_trade else None,
                )
                session.add(daily_pnl)
                session.commit()
                logger.debug(f"Recorded daily P&L: {strategy_name} {trade_date.date()}")
            
            return True
    
    except Exception as e:
        logger.error(f"Failed to record daily P&L: {e}")
        return False


def get_recent_trades(strategy_name: str, symbol: str, days: int = 1) -> list:
    """Get recent trades for a symbol."""
    try:
        from core.db_connection import DatabaseSession
        from core.db_models import Trade
        from datetime import timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        with DatabaseSession() as session:
            trades = session.query(Trade).filter(
                Trade.strategy_name == strategy_name,
                Trade.symbol == symbol,
                Trade.trade_date >= cutoff_date
            ).all()
            
            return trades
    
    except Exception as e:
        logger.error(f"Failed to fetch recent trades: {e}")
        return []


if __name__ == "__main__":
    # Test database functions
    logging.basicConfig(level=logging.INFO)
    
    from datetime import datetime
    
    # Initialize database
    from core.db_connection import init_db_connection
    init_db_connection()
    
    print("✅ Database utility module loaded")
