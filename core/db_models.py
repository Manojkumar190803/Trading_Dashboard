"""
SQLAlchemy ORM models for trading database.
Supports: Trades, Positions, Orders, Strategy Configs, Daily P&L, Logs, Account Summary
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Boolean, 
    DECIMAL, ForeignKey, Index, Enum, UniqueConstraint, inspect, text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class TradeStatus(str, enum.Enum):
    """Trade execution status"""
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    SL_HIT = "SL_HIT"
    BE_HIT = "BE_HIT"
    CANCELLED = "CANCELLED"


class OrderStatus(str, enum.Enum):
    """Order status values"""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL_FILL = "PARTIAL_FILL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderSide(str, enum.Enum):
    """Buy or Sell"""
    BUY = "BUY"
    SELL = "SELL"


class Trade(Base):
    """Individual trade records (entry/exit)"""
    __tablename__ = "trades"
    __table_args__ = (
        Index("idx_symbol_date", "symbol", "trade_date"),
        Index("idx_strategy_date", "strategy_name", "trade_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(100), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    
    # Entry details
    entry_time = Column(DateTime, nullable=False)
    entry_price = Column(DECIMAL(10, 2), nullable=False)
    entry_qty = Column(Integer, nullable=False)
    entry_side = Column(Enum(OrderSide), nullable=False)
    
    # Exit details
    exit_time = Column(DateTime, nullable=True)
    exit_price = Column(DECIMAL(10, 2), nullable=True)
    exit_qty = Column(Integer, nullable=True)
    
    # P&L
    pnl = Column(DECIMAL(12, 2), nullable=True)
    pnl_percentage = Column(Float, nullable=True)
    
    # Stop loss & take profit
    initial_sl_points = Column(Float, nullable=True)
    breakeven_rr = Column(Float, nullable=True)
    trailing_step_rr = Column(Float, nullable=True)
    
    # Trade metadata
    status = Column(Enum(TradeStatus), nullable=False, default=TradeStatus.ENTRY)
    trade_date = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Trade {self.strategy_name} {self.symbol} {self.entry_price} {self.entry_side}>"


class Position(Base):
    """Current open positions"""
    __tablename__ = "positions"
    __table_args__ = (
        Index("idx_symbol_active", "symbol", "is_active"),
        Index("idx_strategy_active", "strategy_name", "is_active"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(100), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    
    # Position details
    qty = Column(Integer, nullable=False)
    side = Column(Enum(OrderSide), nullable=False)
    entry_price = Column(DECIMAL(10, 2), nullable=False)
    current_price = Column(DECIMAL(10, 2), nullable=True)
    
    # P&L tracking
    unrealized_pnl = Column(DECIMAL(12, 2), nullable=True)
    realized_pnl = Column(DECIMAL(12, 2), nullable=False, default=0)
    
    # Stop loss & controls
    sl_price = Column(DECIMAL(10, 2), nullable=True)
    tp_price = Column(DECIMAL(10, 2), nullable=True)
    trailing_sl_price = Column(DECIMAL(10, 2), nullable=True)
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    opened_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Position {self.strategy_name} {self.symbol} {self.qty}@{self.entry_price}>"


class Order(Base):
    """Pending/filled/cancelled orders"""
    __tablename__ = "orders"
    __table_args__ = (
        Index("idx_symbol_status", "symbol", "status"),
        Index("idx_strategy_status", "strategy_name", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    broker_order_id = Column(String(100), unique=True, nullable=True, index=True)
    strategy_name = Column(String(100), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    
    # Order details
    side = Column(Enum(OrderSide), nullable=False)
    qty = Column(Integer, nullable=False)
    order_price = Column(DECIMAL(10, 2), nullable=False)
    order_type = Column(String(20), nullable=False)  # LIMIT, MARKET, etc.
    
    # Execution
    filled_qty = Column(Integer, nullable=False, default=0)
    filled_price = Column(DECIMAL(10, 2), nullable=True)
    status = Column(Enum(OrderStatus), nullable=False, index=True)
    
    # Timestamps
    order_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    fill_time = Column(DateTime, nullable=True)
    
    rejection_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Order {self.symbol} {self.side} {self.qty} {self.status}>"


class StrategyConfig(Base):
    """Strategy configuration parameters"""
    __tablename__ = "strategy_configs"
    __table_args__ = (
        UniqueConstraint("strategy_name", "symbol", name="uq_strategy_symbol"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(100), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    
    # Config parameters (JSON-like storage as TEXT)
    config_json = Column(Text, nullable=False)  # Stores JSON config
    
    # Common parameters
    initial_sl_points = Column(Float, nullable=True)
    breakeven_rr = Column(Float, nullable=True)
    trailing_step_rr = Column(Float, nullable=True)
    daily_loss_limit = Column(DECIMAL(12, 2), nullable=True)
    max_positions = Column(Integer, nullable=True)
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<StrategyConfig {self.strategy_name} {self.symbol}>"


class DailyPnL(Base):
    """Daily P&L summary"""
    __tablename__ = "daily_pnl"
    __table_args__ = (
        UniqueConstraint("strategy_name", "trade_date", name="uq_strategy_date"),
        Index("idx_dailypnl_strategy_date", "strategy_name", "trade_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(100), nullable=False, index=True)
    trade_date = Column(DateTime, nullable=False, index=True)
    
    # Daily totals
    total_trades = Column(Integer, nullable=False, default=0)
    winning_trades = Column(Integer, nullable=False, default=0)
    losing_trades = Column(Integer, nullable=False, default=0)
    
    # P&L
    gross_pnl = Column(DECIMAL(12, 2), nullable=False, default=0)
    net_pnl = Column(DECIMAL(12, 2), nullable=False, default=0)
    
    # Metrics
    win_rate = Column(Float, nullable=True)
    avg_win = Column(DECIMAL(12, 2), nullable=True)
    avg_loss = Column(DECIMAL(12, 2), nullable=True)
    best_trade = Column(DECIMAL(12, 2), nullable=True)
    worst_trade = Column(DECIMAL(12, 2), nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<DailyPnL {self.strategy_name} {self.trade_date} ₹{self.net_pnl}>"


class Log(Base):
    """Event logs and alerts"""
    __tablename__ = "logs"
    __table_args__ = (
        Index("idx_timestamp", "timestamp"),
        Index("idx_level_timestamp", "level", "timestamp"),
        Index("idx_symbol_timestamp", "symbol", "timestamp"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Log details
    level = Column(String(20), nullable=False)  # INFO, WARNING, ERROR, ALERT
    category = Column(String(50), nullable=False)  # ENTRY, EXIT, SL, ALERT, etc.
    symbol = Column(String(50), nullable=True, index=True)
    strategy_name = Column(String(100), nullable=True, index=True)
    
    # Message
    message = Column(Text, nullable=False)
    
    # Additional context
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    
    # Metadata
    metadata_json = Column(Text, nullable=True)  # Additional JSON data
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<Log {self.level} {self.category} {self.symbol}>"


class AccountSummary(Base):
    """Account balance and margin summary"""
    __tablename__ = "account_summary"
    __table_args__ = (
        Index("idx_account_timestamp", "timestamp"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Balance
    total_balance = Column(DECIMAL(14, 2), nullable=False)
    available_balance = Column(DECIMAL(14, 2), nullable=False)
    blocked_balance = Column(DECIMAL(14, 2), nullable=False)
    
    # Margin
    total_margin = Column(DECIMAL(14, 2), nullable=False)
    available_margin = Column(DECIMAL(14, 2), nullable=False)
    used_margin = Column(DECIMAL(14, 2), nullable=False)
    
    # P&L
    mtm = Column(DECIMAL(14, 2), nullable=False)  # Mark-to-market
    unrealized_pnl = Column(DECIMAL(14, 2), nullable=False)
    realized_pnl = Column(DECIMAL(14, 2), nullable=False)
    
    # Positions
    open_positions_count = Column(Integer, nullable=False, default=0)
    
    # Additional metrics
    buying_power = Column(DECIMAL(14, 2), nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<AccountSummary {self.timestamp} Balance:₹{self.total_balance}>"


class Instrument(Base):
    """Trading instruments configured for monitoring and strategies"""
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("name", name="uq_instrument_name"),
        Index("idx_instrument_status", "status"),
        Index("idx_instrument_strategy", "strategy"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    broker_symbol = Column(String(100), nullable=False)
    strategy = Column(String(50), nullable=False, index=True)
    
    # Monitoring times (stored as string HH:MM format)
    monitoring_start_time = Column(String(5), nullable=False)  # e.g., "09:15"
    monitoring_end_time = Column(String(5), nullable=False)    # e.g., "15:30"
    entry_cutoff_time = Column(String(5), nullable=True, default="14:40")
    
    # Lot configuration
    lot_size_adjustment = Column(Float, nullable=False, default=1.0)
    calculated_lot_size = Column(Integer, nullable=False)
    
    # Premium constraints
    premium_min_price = Column(Float, nullable=True)
    premium_max_price = Column(Float, nullable=True)
    premium_option_strike = Column(Integer, nullable=True)  # ATM strike price for options
    max_initial_risk_points = Column(Float, nullable=True, default=20.0)
    
    # Product type (SPOT, OPTION, etc.)
    product_type = Column(String(20), nullable=False, default="SPOT")
    
    # Status
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)  # ACTIVE, PAUSED, ARCHIVED
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Instrument {self.name} {self.strategy} Lot:{self.calculated_lot_size}>"


# Utility function to create all tables
def create_all_tables(engine):
    """Create tables and add supported columns to existing instrument tables."""
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    if "instruments" in inspector.get_table_names():
        existing_columns = {column["name"] for column in inspector.get_columns("instruments")}
        column_definitions = {
            "entry_cutoff_time": "VARCHAR(5) DEFAULT '14:40'",
            "max_initial_risk_points": "FLOAT DEFAULT 20.0",
        }
        with engine.begin() as connection:
            for column_name, definition in column_definitions.items():
                if column_name not in existing_columns:
                    connection.execute(
                        text(f"ALTER TABLE instruments ADD COLUMN {column_name} {definition}")
                    )

    print("✅ Database schema created successfully!")
