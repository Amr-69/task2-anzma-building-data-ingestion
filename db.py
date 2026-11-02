import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "anzma_building.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def get_connection(db_path=DB_PATH):
    """Open a connection with foreign keys ON (SQLite has them OFF by default)."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn