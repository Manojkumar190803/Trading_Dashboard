"""
Database connection and session management.
Handles SQLAlchemy connection pooling and session lifecycle.
"""

import os
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
import logging

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Manages database connection and session creation"""
    
    _engine = None
    _session_factory = None
    
    @classmethod
    def initialize(
        cls,
        db_url: Optional[str] = None,
        pool_size: int = 10,
        max_overflow: int = 20,
        echo: bool = False
    ):
        """
        Initialize database connection
        
        Args:
            db_url: PostgreSQL connection string (uses DB_URL env if not provided)
            pool_size: Number of connections to maintain
            max_overflow: Additional connections allowed when pool exhausted
            echo: Print SQL queries if True
        """
        if cls._engine is not None:
            logger.warning("Database already initialized")
            return
        
        # Use provided URL or fall back to environment variable
        connection_url = db_url or os.getenv("DB_URL")
        
        if not connection_url:
            raise ValueError(
                "Database URL not provided. Set DB_URL environment variable or pass db_url parameter"
            )
        
        try:
            cls._engine = create_engine(
                connection_url,
                poolclass=QueuePool,
                pool_size=pool_size,
                max_overflow=max_overflow,
                echo=echo,
                pool_pre_ping=True,  # Verify connections before using
                pool_recycle=3600,   # Recycle connections every hour
            )
            
            # Test connection
            with cls._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            cls._session_factory = sessionmaker(bind=cls._engine, expire_on_commit=False)
            logger.info(f"✅ Database initialized: {connection_url.split('@')[1] if '@' in connection_url else 'connected'}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {str(e)}")
            cls._engine = None
            cls._session_factory = None
            raise

    @classmethod
    def get_session(cls) -> Session:
        """Get a new database session"""
        if cls._session_factory is None:
            raise RuntimeError("Database not initialized. Call DatabaseConnection.initialize() first")
        return cls._session_factory()

    @classmethod
    def get_engine(cls):
        """Get SQLAlchemy engine"""
        if cls._engine is None:
            raise RuntimeError("Database not initialized. Call DatabaseConnection.initialize() first")
        return cls._engine

    @classmethod
    def close_all(cls):
        """Close all database connections"""
        if cls._engine is not None:
            cls._engine.dispose()
            cls._engine = None
            cls._session_factory = None
            logger.info("Database connections closed")

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if database is initialized"""
        return cls._engine is not None


# Context manager for sessions
class DatabaseSession:
    """Context manager for database sessions"""
    
    def __init__(self):
        self.session: Optional[Session] = None
    
    def __enter__(self) -> Session:
        self.session = DatabaseConnection.get_session()
        return self.session
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            if exc_type:
                self.session.rollback()
            else:
                self.session.commit()
            self.session.close()


def init_db_connection():
    """Initialize database connection (call this at application startup)"""
    from core.db_models import create_all_tables
    
    db_url = os.getenv(
        "DB_URL",
        "postgresql://astro:astro@host.docker.internal:5432/TRADING_SETUPS"
    )
    
    DatabaseConnection.initialize(db_url=db_url)
    engine = DatabaseConnection.get_engine()
    
    # Create all tables
    create_all_tables(engine)


if __name__ == "__main__":
    # Test connection
    init_db_connection()
    
    with DatabaseSession() as session:
        result = session.execute(text("SELECT 1"))
        print(f"✅ Test query passed: {result.scalar()}")
