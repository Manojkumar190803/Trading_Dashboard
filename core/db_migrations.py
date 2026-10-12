"""
Database migration and schema initialization script.
Run this to create or update the database schema.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect
from core.db_connection import DatabaseConnection, init_db_connection
from core.db_models import Base, create_all_tables

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_schema_exists():
    """Check if database schema exists"""
    engine = DatabaseConnection.get_engine()
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    expected_tables = {
        'trades', 'positions', 'orders', 'strategy_configs',
        'daily_pnl', 'logs', 'account_summary'
    }
    
    existing_tables = set(tables)
    missing_tables = expected_tables - existing_tables
    
    return {
        'total_expected': len(expected_tables),
        'total_existing': len(existing_tables),
        'missing_tables': missing_tables,
        'all_tables': list(existing_tables)
    }


def create_schema():
    """Create database schema"""
    logger.info("Creating database schema...")
    try:
        engine = DatabaseConnection.get_engine()
        create_all_tables(engine)
        logger.info("✅ Schema created successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create schema: {str(e)}")
        return False


def print_schema_info():
    """Print database schema information"""
    inspector = inspect(DatabaseConnection.get_engine())
    
    print("\n" + "="*60)
    print("DATABASE SCHEMA INFORMATION")
    print("="*60)
    
    for table_name in sorted(inspector.get_table_names()):
        columns = inspector.get_columns(table_name)
        print(f"\n📋 TABLE: {table_name}")
        print(f"   Columns ({len(columns)}):")
        
        for col in columns:
            col_type = str(col['type'])
            nullable = "NULL" if col['nullable'] else "NOT NULL"
            print(f"     • {col['name']:<20} {col_type:<15} {nullable}")
        
        # Print indexes
        indexes = inspector.get_indexes(table_name)
        if indexes:
            print(f"   Indexes ({len(indexes)}):")
            for idx in indexes:
                print(f"     • {idx['name']}: {', '.join(idx['column_names'])}")
        
        # Print constraints
        constraints = inspector.get_unique_constraints(table_name)
        if constraints:
            print(f"   Unique Constraints ({len(constraints)}):")
            for cons in constraints:
                print(f"     • {cons['name']}: {', '.join(cons['column_names'])}")


def migrate():
    """Run database migration"""
    logger.info("Starting database migration...")
    
    try:
        # Initialize connection
        logger.info("Connecting to database...")
        init_db_connection()
        
        # Check existing schema
        logger.info("Checking existing schema...")
        schema_info = check_schema_exists()
        
        print(f"\n📊 Schema Status:")
        print(f"   Expected tables: {schema_info['total_expected']}")
        print(f"   Existing tables: {schema_info['total_existing']}")
        
        if schema_info['missing_tables']:
            print(f"   Missing tables: {', '.join(schema_info['missing_tables'])}")
            print("\n Creating missing tables...")
            create_schema()
        else:
            logger.info("✅ All tables already exist")
        
        # Print schema info
        print_schema_info()
        
        print("\n" + "="*60)
        logger.info("✅ Migration completed successfully")
        print("="*60 + "\n")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {str(e)}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Database migration tool")
    parser.add_argument("--db-url", help="Database URL (overrides DB_URL env variable)")
    parser.add_argument("--create", action="store_true", help="Force create all tables")
    parser.add_argument("--info", action="store_true", help="Show schema information only")
    
    args = parser.parse_args()
    
    # Set database URL if provided
    if args.db_url:
        os.environ["DB_URL"] = args.db_url
    elif "DB_URL" not in os.environ:
        # Use default only if not set in environment
        db_url = "postgresql://astro:astro@host.docker.internal:5432/TRADING_SETUPS"
        logger.info(f"Using default database URL (set DB_URL env to override)")
        os.environ["DB_URL"] = db_url
    
    try:
        # Initialize connection
        init_db_connection()
        
        if args.info:
            # Show schema info only
            print_schema_info()
        elif args.create:
            # Force create all tables
            logger.info("Force creating all tables...")
            create_schema()
            print_schema_info()
        else:
            # Normal migration
            migrate()
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)
