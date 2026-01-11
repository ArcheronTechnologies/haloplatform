"""
Database connection management for SQLite.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

from allabolag_scraper.config import ScraperConfig


def init_db(config: ScraperConfig) -> sqlite3.Connection:
    """Initialize the database with schema."""
    conn = sqlite3.connect(config.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Load and execute schema
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path) as f:
        conn.executescript(f.read())
    conn.commit()

    return conn


@contextmanager
def get_connection(config: ScraperConfig):
    """Context manager for database connections."""
    conn = sqlite3.connect(config.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
