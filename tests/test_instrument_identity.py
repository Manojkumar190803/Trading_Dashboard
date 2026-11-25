from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import pytest

from core.db_models import Instrument, create_all_tables


def test_legacy_instrument_name_constraint_migrates_to_name_strategy_pair():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE instruments (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                broker_symbol VARCHAR(100) NOT NULL,
                strategy VARCHAR(50) NOT NULL,
                monitoring_start_time VARCHAR(5) NOT NULL,
                monitoring_end_time VARCHAR(5) NOT NULL,
                entry_cutoff_time VARCHAR(5),
                lot_size_adjustment FLOAT NOT NULL DEFAULT 1.0,
                calculated_lot_size INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT uq_instrument_name UNIQUE (name)
            )
        """))
        connection.execute(text(
            "CREATE UNIQUE INDEX ix_instruments_name ON instruments (name)"
        ))
        connection.execute(text("""
            INSERT INTO instruments (
                id, name, broker_symbol, strategy, monitoring_start_time,
                monitoring_end_time, calculated_lot_size, created_at, updated_at
            ) VALUES (
                1, 'NIFTY', 'NIFTY', '21EMA', '09:15', '15:30', 65,
                '2026-11-23', '2026-11-23'
            )
        """))

    create_all_tables(engine)

    constraints = inspect(engine).get_unique_constraints("instruments")
    assert any(
        constraint["column_names"] == ["name", "strategy"]
        for constraint in constraints
    )
    assert not any(
        constraint["column_names"] == ["name"]
        for constraint in constraints
    )

    with Session(engine) as session:
        session.add(Instrument(
            name="NIFTY",
            broker_symbol="NIFTY",
            strategy="HD",
            monitoring_start_time="09:15",
            monitoring_end_time="15:30",
            calculated_lot_size=65,
        ))
        session.commit()

        session.add(Instrument(
            name="NIFTY",
            broker_symbol="NIFTY",
            strategy="HD",
            monitoring_start_time="09:15",
            monitoring_end_time="15:30",
            calculated_lot_size=65,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
