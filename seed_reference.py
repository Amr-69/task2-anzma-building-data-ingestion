
import sys
from collections import Counter

from db import DB_PATH, get_connection
from reference_data import (
    BUILDING,
    LOCATIONS,
    ASSETS,
    METRIC_TYPES,
    EVENT_TYPES,
    SYSTEM_CODES,
    METRICS_BY_ASSET_TYPE,
    validate,
)


# Explicitly recognized asset types that produce discrete events
# rather than periodic telemetry.
EVENT_ONLY_ASSET_TYPES = {
    "card_reader",
    "barrier_reader",
    "camera",
    "fire_panel",
    "smoke_detector",
}

KNOWN_ASSET_TYPES = (
    set(METRICS_BY_ASSET_TYPE)
    | EVENT_ONLY_ASSET_TYPES
)

# Every table here must be empty before initial seeding.
# system_types is excluded because init_db.py already populates it.
PROTECTED_TABLES = (
    "buildings",
    "locations",
    "assets",
    "metric_types",
    "event_types",
    "telemetry_records",
    "event_records",
)


def validate_reference_data():
    """Validate reference definitions before touching the database."""

    errors = validate()

    for code, name, asset_type, system, location_id in ASSETS:
        if asset_type not in KNOWN_ASSET_TYPES:
            errors.append(
                f"{code}: unrecognized asset type '{asset_type}'"
            )

    if not BUILDING.get("building_id") or not BUILDING.get("name"):
        errors.append("invalid building definition")

    return errors


def get_expected_counts():
    return {
        "buildings": 1,
        "locations": len(LOCATIONS),
        "assets": len(ASSETS),
        "metric_types": len(METRIC_TYPES),
        "event_types": len(EVENT_TYPES),
    }


def seed_database(conn):
    """Insert all reference data in the current transaction."""

    # Resolve system IDs from their unique codes.
    system_rows = conn.execute(
        """
        SELECT system_type_id, code
        FROM system_types
        """
    ).fetchall()

    system_id_by_code = {
        row["code"]: row["system_type_id"]
        for row in system_rows
    }

    if (
        len(system_id_by_code) != len(SYSTEM_CODES)
        or set(system_id_by_code) != set(SYSTEM_CODES)
    ):
        raise RuntimeError(
            "Database system_types do not exactly match "
            "the five approved system codes."
        )

    # Refuse to overwrite or mix with existing data.
    existing_counts = {
        table: conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in PROTECTED_TABLES
    }

    populated = {
        table: count
        for table, count in existing_counts.items()
        if count != 0
    }

    if populated:
        raise RuntimeError(
            "Seeding refused because existing records were found: "
            f"{populated}. No records were overwritten."
        )

    # 1. Insert the building using its approved ID.
    conn.execute(
        """
        INSERT INTO buildings (building_id, name)
        VALUES (?, ?)
        """,
        (
            BUILDING["building_id"],
            BUILDING["name"],
        ),
    )

    # 2. Insert locations connected to the building.
    conn.executemany(
        """
        INSERT INTO locations
            (location_id, building_id, floor, name)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                location_id,
                BUILDING["building_id"],
                floor,
                name,
            )
            for location_id, floor, name in LOCATIONS
        ],
    )

    # 3. Insert assets connected to their system and location.
    conn.executemany(
        """
        INSERT INTO assets
            (
                asset_code,
                name,
                asset_type,
                system_type_id,
                location_id
            )
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                asset_code,
                name,
                asset_type,
                system_id_by_code[system_code],
                location_id,
            )
            for (
                asset_code,
                name,
                asset_type,
                system_code,
                location_id,
            ) in ASSETS
        ],
    )

    # 4. Insert telemetry metric definitions.
    conn.executemany(
        """
        INSERT INTO metric_types (name, unit)
        VALUES (?, ?)
        """,
        METRIC_TYPES,
    )

    # 5. Insert discrete event definitions.
    conn.executemany(
        """
        INSERT INTO event_types (name)
        VALUES (?)
        """,
        [(name,) for name in EVENT_TYPES],
    )


def verify_database(conn):
    """Verify counts and relationships before committing."""

    expected_counts = get_expected_counts()

    for table, expected in expected_counts.items():
        actual = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

        if actual != expected:
            raise RuntimeError(
                f"{table}: expected {expected} rows, "
                f"found {actual}."
            )

    # Verify that every location belongs to the approved building.
    wrong_locations = conn.execute(
        """
        SELECT COUNT(*)
        FROM locations
        WHERE building_id != ?
        """,
        (BUILDING["building_id"],),
    ).fetchone()[0]

    if wrong_locations != 0:
        raise RuntimeError(
            f"{wrong_locations} locations have an incorrect building."
        )

    # Verify that every asset connects to a location and a system.
    connected_assets = conn.execute(
        """
        SELECT COUNT(*)
        FROM assets AS a
        JOIN locations AS l
            ON a.location_id = l.location_id
        JOIN system_types AS s
            ON a.system_type_id = s.system_type_id
        """
    ).fetchone()[0]

    if connected_assets != len(ASSETS):
        raise RuntimeError(
            "Not all assets have valid location and system relationships."
        )

    # Verify the actual asset distribution by system.
    rows = conn.execute(
        """
        SELECT s.code, COUNT(*) AS asset_count
        FROM assets AS a
        JOIN system_types AS s
            ON a.system_type_id = s.system_type_id
        GROUP BY s.code
        """
    ).fetchall()

    actual_distribution = {
        row["code"]: row["asset_count"]
        for row in rows
    }

    expected_distribution = dict(
        Counter(asset[3] for asset in ASSETS)
    )

    if actual_distribution != expected_distribution:
        raise RuntimeError(
            "Asset distribution does not match reference data."
        )

    # Verify SQLite foreign-key integrity.
    violations = conn.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if violations:
        raise RuntimeError(
            f"Foreign-key violations detected: {len(violations)}"
        )

    return actual_distribution


def main():
    print("Validating reference data...")

    errors = validate_reference_data()

    if errors:
        for error in errors:
            print("ERROR:", error)

        raise RuntimeError(
            "Reference data validation failed."
        )

    if not DB_PATH.exists():
        raise RuntimeError(
            f"Database not found: {DB_PATH}. "
            "Run the approved initialization process first."
        )

    conn = get_connection()

    try:
        # Acquire a write transaction before checking and inserting.
        conn.execute("BEGIN IMMEDIATE")

        seed_database(conn)

        distribution = verify_database(conn)

        # Commit only after every verification succeeds.
        conn.commit()

        print()
        print("REFERENCE DATA SEEDED SUCCESSFULLY")
        print("-----------------------------------")
        print("Building:", BUILDING["name"])
        print("Buildings: 1")
        print("Locations:", len(LOCATIONS))
        print("Assets:", len(ASSETS))
        print("Metric types:", len(METRIC_TYPES))
        print("Event types:", len(EVENT_TYPES))

        print()
        print("Assets per system:")

        for system, count in sorted(distribution.items()):
            print(f"  {system}: {count}")

        print()
        print("Foreign-key integrity: PASSED")
        print("Asset relationships: PASSED")
        print("Transaction: COMMITTED")
        print("Database:", DB_PATH)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print()
        print("SEEDING FAILED")
        print("ERROR:", exc)
        print("Transaction rolled back; no partial seed was committed.")
        sys.exit(1)
