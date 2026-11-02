import argparse
import sys

from db import DB_PATH, SCHEMA_PATH, get_connection

SYSTEM_TYPES = ["HVAC", "NETWORKING", "ACCESS_CONTROL", "CCTV", "FIRE_ALARM"]


def main():
    parser = argparse.ArgumentParser(description="Create the SQLite database.")
    parser.add_argument("--reset", action="store_true",
                        help="Delete the existing database file first.")
    args = parser.parse_args()

    if DB_PATH.exists():
        if not args.reset:
            print(f"ERROR: {DB_PATH} already exists. Use --reset to recreate it.")
            sys.exit(1)
        DB_PATH.unlink()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        with conn:
            conn.executemany("INSERT INTO system_types(code) VALUES (?)",
                             [(c,) for c in SYSTEM_TYPES])
        print(f"Created {DB_PATH}")
        print("foreign_keys pragma:", conn.execute("PRAGMA foreign_keys").fetchone()[0])
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in tables:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()