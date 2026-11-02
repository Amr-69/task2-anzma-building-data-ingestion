import sqlite3
import sys

from db import SCHEMA_PATH

passed = 0
failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}")


def accepts(name, conn, sql, params=()):
    try:
        conn.execute(sql, params)
        check(name, True)
    except sqlite3.Error as e:
        print(f"      ({e})")
        check(name, False)


def rejects(name, conn, sql, params=()):
    try:
        conn.execute(sql, params)
        check(name, False)
    except sqlite3.IntegrityError:
        check(name, True)


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def main():
    conn = make_db()
    check("foreign keys are enabled",
          conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1)

    # ---- valid records must be accepted ----
    accepts("insert building", conn, "INSERT INTO buildings VALUES (1, 'Test Building')")
    accepts("insert location", conn, "INSERT INTO locations VALUES (1, 1, 1, 'Floor 1 Lobby')")
    accepts("insert system type", conn, "INSERT INTO system_types VALUES (1, 'HVAC')")
    accepts("insert asset", conn,
            "INSERT INTO assets VALUES (1, 'HVAC-001', 'AHU 1', 'air_handler', 1, 1)")
    accepts("insert metric type", conn, "INSERT INTO metric_types VALUES (1, 'supply_air_temp', 'C')")
    accepts("insert event type", conn, "INSERT INTO event_types VALUES (1, 'filter_alarm')")
    accepts("insert telemetry", conn,
            "INSERT INTO telemetry_records(asset_id, metric_id, ts, value) "
            "VALUES (1, 1, '2026-11-02T10:00:00Z', 21.5)")
    accepts("same asset+metric at a different time is allowed", conn,
            "INSERT INTO telemetry_records(asset_id, metric_id, ts, value) "
            "VALUES (1, 1, '2026-11-02T10:01:00Z', 21.7)")
    accepts("insert event", conn,
            "INSERT INTO event_records(asset_id, event_type_id, ts, severity, details) "
            "VALUES (1, 1, '2026-11-02T10:00:00Z', 'warning', 'test')")

    # ---- invalid records must be rejected ----
    rejects("telemetry with unknown asset", conn,
            "INSERT INTO telemetry_records(asset_id, metric_id, ts, value) "
            "VALUES (999, 1, '2026-11-02T11:00:00Z', 1.0)")
    rejects("telemetry with unknown metric", conn,
            "INSERT INTO telemetry_records(asset_id, metric_id, ts, value) "
            "VALUES (1, 999, '2026-11-02T11:00:00Z', 1.0)")
    rejects("duplicate telemetry", conn,
            "INSERT INTO telemetry_records(asset_id, metric_id, ts, value) "
            "VALUES (1, 1, '2026-11-02T10:00:00Z', 22.0)")
    rejects("telemetry timestamp with space instead of T", conn,
            "INSERT INTO telemetry_records(asset_id, metric_id, ts, value) "
            "VALUES (1, 1, '2026-11-02 12:00:00', 1.0)")
    rejects("telemetry timestamp with month 13", conn,
            "INSERT INTO telemetry_records(asset_id, metric_id, ts, value) "
            "VALUES (1, 1, '2026-13-01T12:00:00Z', 1.0)")
    rejects("telemetry with NULL value", conn,
            "INSERT INTO telemetry_records(asset_id, metric_id, ts, value) "
            "VALUES (1, 1, '2026-11-02T13:00:00Z', NULL)")
    rejects("event with unknown asset", conn,
            "INSERT INTO event_records(asset_id, event_type_id, ts, severity) "
            "VALUES (999, 1, '2026-11-02T11:00:00Z', 'info')")
    rejects("duplicate event", conn,
            "INSERT INTO event_records(asset_id, event_type_id, ts, severity) "
            "VALUES (1, 1, '2026-11-02T10:00:00Z', 'info')")
    rejects("event with invalid severity", conn,
            "INSERT INTO event_records(asset_id, event_type_id, ts, severity) "
            "VALUES (1, 1, '2026-11-02T11:00:00Z', 'banana')")
    rejects("event timestamp in wrong format", conn,
            "INSERT INTO event_records(asset_id, event_type_id, ts, severity) "
            "VALUES (1, 1, '02/11/2026 11:00', 'info')")
    rejects("invalid system type code", conn,
            "INSERT INTO system_types VALUES (99, 'BANANA')")
    rejects("asset with unknown location", conn,
            "INSERT INTO assets VALUES (2, 'HVAC-002', 'AHU 2', 'air_handler', 1, 999)")
    rejects("asset with unknown system type", conn,
            "INSERT INTO assets VALUES (3, 'HVAC-003', 'AHU 3', 'air_handler', 99, 1)")
    rejects("duplicate asset code", conn,
            "INSERT INTO assets VALUES (4, 'HVAC-001', 'Copy', 'air_handler', 1, 1)")
    rejects("location with unknown building", conn,
            "INSERT INTO locations VALUES (2, 999, 1, 'Ghost Room')")
    rejects("deleting an asset that has records", conn,
            "DELETE FROM assets WHERE asset_id = 1")

    print()
    if failed == 0:
        print(f"ALL {passed} CHECKS PASSED")
    else:
        print(f"{failed} CHECK(S) FAILED, {passed} passed")
        sys.exit(1)


if __name__ == "__main__":
    main()