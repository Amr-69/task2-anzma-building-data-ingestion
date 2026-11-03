
"""Verification for the Day 3 dashboard.

Run from the project folder:

    python test_dashboard.py

Every expected number below is recomputed independently from the raw tables with
plain SELECTs and Python arithmetic, not with the SQL used by dashboard_core.py.
The committed database is only read. The "data changes" test works on a temporary
copy.
"""

import hashlib
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dashboard import dashboard_core as core

DB = core.DB_PATH
DOC = Path(__file__).resolve().parent / "KPI_DEFINITIONS.md"


def raw(db_path=DB):
    conn = sqlite3.connect(
        Path(db_path).resolve().as_uri() + "?mode=ro",
        uri=True,
    )
    conn.row_factory = sqlite3.Row
    return conn


def kpi(overview, key):
    return next(k for k in overview["kpis"] if k["key"] == key)


def expected_from_raw(conn, system=None, building=None, start=None, end=None):
    """Independently recompute the numbers reported by the dashboard."""

    assets = [
        dict(r) for r in conn.execute(
            """
            SELECT
                a.asset_id,
                a.asset_code,
                a.asset_type,
                st.code AS system_type,
                l.building_id
            FROM assets a, system_types st, locations l
            WHERE st.system_type_id = a.system_type_id
              AND l.location_id = a.location_id
            """
        )
    ]

    assets = [
        a for a in assets
        if (system is None or a["system_type"] == system)
        and (building is None or a["building_id"] == building)
    ]

    ids = {a["asset_id"] for a in assets}

    def in_period(ts):
        return (
            (start is None or ts >= start)
            and (end is None or ts < end)
        )

    events = [
        dict(r) for r in conn.execute(
            """
            SELECT
                e.asset_id,
                e.ts,
                e.severity,
                et.name AS event_type
            FROM event_records e, event_types et
            WHERE et.event_type_id = e.event_type_id
            """
        )
    ]

    events = [
        e for e in events
        if e["asset_id"] in ids and in_period(e["ts"])
    ]

    tele = [
        dict(r) for r in conn.execute(
            """
            SELECT
                t.asset_id,
                t.ts,
                t.value,
                m.name AS metric
            FROM telemetry_records t, metric_types m
            WHERE m.metric_id = t.metric_id
            """
        )
    ]

    tele = [
        t for t in tele
        if t["asset_id"] in ids and in_period(t["ts"])
    ]

    warn = sum(1 for e in events if e["severity"] == "warning")
    crit = sum(1 for e in events if e["severity"] == "critical")

    def mean(metric):
        vals = [
            t["value"] for t in tele
            if t["metric"] == metric
        ]
        return round(sum(vals) / len(vals), 2) if vals else None

    return {
        "assets": len(assets),
        "warn": warn,
        "crit": crit,
        "temp": mean("zone_temp"),
        "loss": mean("packet_loss_pct"),
        "events": len(events),
        "telemetry": len(tele),
        "heartbeats": sum(
            1 for e in events
            if e["event_type"] == "heartbeat"
        ),
    }


class DashboardTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = core.open_readonly()
        cls.raw = raw()
        cls.before_hash = hashlib.sha256(DB.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.raw.close()

    # ---------- KPIs equal an independent recomputation ----------

    def test_default_period_matches_raw_tables(self):
        o = core.build_overview(self.conn)
        e = expected_from_raw(self.raw)

        self.assertEqual(
            kpi(o, "monitored_assets")["value"], e["assets"]
        )
        self.assertEqual(
            kpi(o, "alerts_raised")["value"], e["warn"] + e["crit"]
        )
        self.assertEqual(
            kpi(o, "critical_alerts")["value"], e["crit"]
        )
        self.assertEqual(
            kpi(o, "avg_zone_temp")["value"], e["temp"]
        )
        self.assertEqual(
            kpi(o, "avg_packet_loss")["value"], e["loss"]
        )
        self.assertEqual(
            o["period"]["telemetry_records"], e["telemetry"]
        )
        self.assertEqual(
            o["period"]["event_records"], e["events"]
        )

        hours = o["period"]["hours"]
        self.assertAlmostEqual(
            kpi(o, "alert_rate_per_hour")["value"],
            round((e["warn"] + e["crit"]) / hours, 2),
            places=2,
        )

    def test_every_filter_combination_matches_raw_tables(self):
        for system in [None] + core.SYSTEM_CODES:
            for building in (None, 1):
                with self.subTest(system=system, building=building):
                    o = core.build_overview(
                        self.conn, system, building
                    )
                    e = expected_from_raw(
                        self.raw, system, building
                    )

                    self.assertEqual(
                        kpi(o, "monitored_assets")["value"],
                        e["assets"],
                    )
                    self.assertEqual(
                        kpi(o, "alerts_raised")["value"],
                        e["warn"] + e["crit"],
                    )
                    self.assertEqual(
                        kpi(o, "critical_alerts")["value"],
                        e["crit"],
                    )
                    self.assertEqual(
                        kpi(o, "avg_zone_temp")["value"],
                        e["temp"],
                    )
                    self.assertEqual(
                        kpi(o, "avg_packet_loss")["value"],
                        e["loss"],
                    )

    def test_custom_period_and_exclusive_end(self):
        start = "2026-11-01T06:00:00Z"
        end = "2026-11-01T18:00:00Z"

        o = core.build_overview(
            self.conn, None, None, start, end
        )
        e = expected_from_raw(
            self.raw, start=start, end=end
        )

        self.assertEqual(
            kpi(o, "alerts_raised")["value"],
            e["warn"] + e["crit"],
        )
        self.assertEqual(
            o["period"]["telemetry_records"],
            e["telemetry"],
        )
        self.assertEqual(o["period"]["hours"], 12.0)

        # An event exactly at the end instant must be excluded.
        # AC-RDR-PARK warning is at 2026-11-01T07:05:00Z.
        before = core.build_overview(
            self.conn,
            "ACCESS_CONTROL",
            None,
            "2026-11-01T07:00:00Z",
            "2026-11-01T07:05:00Z",
        )
        at = core.build_overview(
            self.conn,
            "ACCESS_CONTROL",
            None,
            "2026-11-01T07:00:00Z",
            "2026-11-01T07:05:01Z",
        )

        self.assertEqual(
            kpi(before, "alerts_raised")["value"], 0
        )
        self.assertEqual(
            kpi(at, "alerts_raised")["value"], 1
        )

    def test_heartbeat_compliance(self):
        o = core.build_overview(self.conn, "CCTV")
        e = expected_from_raw(self.raw, "CCTV")
        k = kpi(o, "heartbeat_compliance")

        self.assertEqual(e["heartbeats"], 150)
        self.assertEqual(k["value"], 100.0)
        self.assertIn(
            "150 received, 150 expected",
            k["detail"],
        )

        # A period without a whole hour has no expectation to compare with.
        short = core.build_overview(
            self.conn,
            "CCTV",
            None,
            "2026-11-01T10:10:00Z",
            "2026-11-01T10:50:00Z",
        )

        self.assertIsNone(
            kpi(short, "heartbeat_compliance")["value"]
        )

    def test_heartbeat_compliance_clips_to_dataset_coverage(self):
        """Do not expect heartbeats outside the available dataset period."""

        o = core.build_overview(
            self.conn,
            None,
            None,
            "2026-10-29T23:55:00Z",
            "2026-11-02T00:55:01Z",
        )

        k = kpi(o, "heartbeat_compliance")

        self.assertEqual(k["value"], 100.0)
        self.assertEqual(
            k["detail"],
            "175 received, 175 expected",
        )

    # ---------- meaningful combinations only ----------

    def test_not_applicable_kpis(self):
        cctv = core.build_overview(self.conn, "CCTV")

        self.assertFalse(
            kpi(cctv, "avg_zone_temp")["applicable"]
        )
        self.assertFalse(
            kpi(cctv, "avg_packet_loss")["applicable"]
        )
        self.assertTrue(
            kpi(cctv, "heartbeat_compliance")["applicable"]
        )

        hvac = core.build_overview(self.conn, "HVAC")

        self.assertTrue(
            kpi(hvac, "avg_zone_temp")["applicable"]
        )
        self.assertFalse(
            kpi(hvac, "avg_packet_loss")["applicable"]
        )
        self.assertFalse(
            kpi(hvac, "heartbeat_compliance")["applicable"]
        )
        self.assertFalse(
            hvac["trends"]["bandwidth"]["applicable"]
        )

    # ---------- status rules and health summary ----------

    def test_status_rules(self):
        o = core.build_overview(self.conn)
        by_code = {
            a["asset_code"]: a for a in o["assets"]
        }

        self.assertEqual(
            by_code["HVAC-AHU-02"]["status"], "critical"
        )
        self.assertEqual(
            by_code["HVAC-AHU-01"]["status"], "warning"
        )
        self.assertEqual(
            by_code["CCTV-LOBBY"]["status"], "normal"
        )
        self.assertEqual(
            by_code["AC-RDR-LOBBY"]["liveness"], "none"
        )
        self.assertEqual(
            by_code["CCTV-LOBBY"]["liveness"], "heartbeat"
        )
        self.assertEqual(
            by_code["NET-CORE-01"]["liveness"], "telemetry"
        )

    def test_no_data_status_in_empty_period(self):
        o = core.build_overview(
            self.conn,
            None,
            None,
            "2026-11-03T00:00:00Z",
            "2026-11-03T01:00:00Z",
        )
        by_code = {
            a["asset_code"]: a for a in o["assets"]
        }

        self.assertEqual(
            by_code["HVAC-AHU-01"]["status"], "no_data"
        )
        self.assertEqual(
            by_code["CCTV-LOBBY"]["status"], "no_data"
        )
        self.assertEqual(
            by_code["AC-RDR-LOBBY"]["status"], "normal"
        )
        self.assertEqual(
            kpi(o, "alerts_raised")["value"], 0
        )

    def test_health_summary_is_consistent(self):
        o = core.build_overview(self.conn)
        total = 0

        for row in o["health"]["by_system"]:
            self.assertEqual(
                row["normal"]
                + row["warning"]
                + row["critical"]
                + row["no_data"],
                row["assets"],
            )
            total += row["assets"]

        self.assertEqual(
            total,
            kpi(o, "monitored_assets")["value"],
        )
        self.assertEqual(
            o["health"]["overall"]["assets"],
            total,
        )

        normal = sum(
            1 for a in o["assets"]
            if a["status"] == "normal"
        )

        self.assertEqual(
            kpi(o, "healthy_assets_pct")["value"],
            round(normal * 100 / total, 1),
        )

    def test_trends_add_up_to_kpis(self):
        o = core.build_overview(self.conn)
        t = o["trends"]

        self.assertEqual(
            sum(t["warnings"]) + sum(t["criticals"]),
            kpi(o, "alerts_raised")["value"],
        )
        self.assertEqual(
            sum(t["criticals"]),
            kpi(o, "critical_alerts")["value"],
        )
        self.assertEqual(
            len(t["hours"]),
            len(t["warnings"]),
        )
        self.assertEqual(
            len(t["hours"]),
            len(t["zone_temp"]["values"]),
        )

    # ---------- validation ----------

    def test_invalid_requests_are_rejected(self):
        bad = [
            dict(system_type="BOILER"),
            dict(building_id=999),
            dict(start_time="2026-11-01T10:00:00"),
            dict(start_time="2026-02-31T00:00:00Z"),
            dict(start_time="2026-11-01T24:00:00Z"),
            dict(start_time="2026-11-01T10:00:00.5Z"),
            dict(
                start_time="2026-11-02T00:00:00Z",
                end_time="2026-11-01T00:00:00Z",
            ),
            dict(
                start_time="2026-11-01T00:00:00Z",
                end_time="2026-11-01T00:00:00Z",
            ),
            dict(
                start_time="2026-09-01T00:00:00Z",
                end_time="2026-11-01T00:00:00Z",
            ),
        ]

        for kwargs in bad:
            with self.subTest(**kwargs):
                with self.assertRaises(core.DashboardError):
                    core.build_overview(self.conn, **kwargs)

    def test_timestamp_rules_match_the_ingestion_api(self):
        """dashboard_core must accept and reject exactly what main.py does."""

        try:
            from main import parse_utc_timestamp as api_parse
        except ImportError:
            self.skipTest(
                "FastAPI is not installed in this environment"
            )

        samples = [
            "2026-11-01T10:00:00Z",
            "2026-11-01T10:00:00",
            "2026-02-31T00:00:00Z",
            "2026-11-01T24:00:00Z",
            "2026-11-01T10:00:00.5Z",
            "2026-11-01T10:00:00+02:00",
            "2026-11-01 10:00:00Z",
            "",
            "not a time",
        ]

        for value in samples:
            with self.subTest(value=value):
                results = []

                for parse in (
                    api_parse,
                    core.parse_utc_timestamp,
                ):
                    try:
                        parse(value)
                        results.append("ok")
                    except ValueError:
                        results.append("error")

                self.assertEqual(results[0], results[1])

    # ---------- derived, not hardcoded ----------

    def test_database_is_opened_read_only(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.conn.execute(
                "INSERT INTO buildings (name) VALUES ('x')"
            )

    def test_committed_database_is_unchanged_by_the_dashboard(self):
        for system in [None, "HVAC", "CCTV"]:
            core.build_overview(self.conn, system)

        self.assertEqual(
            hashlib.sha256(DB.read_bytes()).hexdigest(),
            self.before_hash,
        )

    def test_kpis_follow_the_data(self):
        """Change a copy of the database and watch the KPIs move."""

        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy.db"
            shutil.copy(DB, copy)

            ro = core.open_readonly(copy)
            base = core.build_overview(
                ro,
                "HVAC",
                None,
                "2026-11-01T00:00:00Z",
                "2026-11-02T01:00:00Z",
            )
            ro.close()

            rw = sqlite3.connect(copy)
            rw.execute("PRAGMA foreign_keys = ON")

            asset = rw.execute(
                """
                SELECT asset_id FROM assets
                WHERE asset_code = 'HVAC-ZN-1E'
                """
            ).fetchone()[0]

            ev = rw.execute(
                """
                SELECT event_type_id FROM event_types
                WHERE name = 'high_temperature'
                """
            ).fetchone()[0]

            met = rw.execute(
                """
                SELECT metric_id FROM metric_types
                WHERE name = 'zone_temp'
                """
            ).fetchone()[0]

            rw.execute(
                """
                INSERT INTO event_records
                    (asset_id, event_type_id, ts, severity, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    asset,
                    ev,
                    "2026-11-01T12:00:00Z",
                    "critical",
                    "test",
                ),
            )

            rw.execute(
                """
                INSERT INTO telemetry_records
                    (asset_id, metric_id, ts, value)
                VALUES (?, ?, ?, ?)
                """,
                (
                    asset,
                    met,
                    "2026-11-01T12:01:00Z",
                    99.0,
                ),
            )

            rw.commit()
            rw.close()

            ro = core.open_readonly(copy)
            after = core.build_overview(
                ro,
                "HVAC",
                None,
                "2026-11-01T00:00:00Z",
                "2026-11-02T01:00:00Z",
            )
            ro.close()

        self.assertEqual(
            kpi(after, "critical_alerts")["value"],
            kpi(base, "critical_alerts")["value"] + 1,
        )
        self.assertEqual(
            kpi(after, "alerts_raised")["value"],
            kpi(base, "alerts_raised")["value"] + 1,
        )
        self.assertGreater(
            kpi(after, "avg_zone_temp")["value"],
            kpi(base, "avg_zone_temp")["value"],
        )
        self.assertLess(
            kpi(after, "healthy_assets_pct")["value"],
            kpi(base, "healthy_assets_pct")["value"],
        )

        status = {
            a["asset_code"]: a["status"]
            for a in after["assets"]
        }

        self.assertEqual(
            status["HVAC-ZN-1E"],
            "critical",
        )

    # ---------- documentation matches the code ----------

    def test_every_kpi_is_documented(self):
        self.assertTrue(
            DOC.is_file(),
            "KPI_DEFINITIONS.md is missing",
        )

        text = DOC.read_text(encoding="utf-8")

        for key, meta in core.KPI_DEFINITIONS.items():
            with self.subTest(kpi=key):
                self.assertIn(meta["name"], text)

        self.assertGreaterEqual(
            len(core.KPI_DEFINITIONS),
            6,
        )

    def test_hourly_slot_helper(self):
        parse = core.parse_utc_timestamp

        self.assertEqual(
            core.hourly_slots(
                parse("2026-11-01T00:00:00Z"),
                parse("2026-11-01T01:00:00Z"),
            ),
            1,
        )

        self.assertEqual(
            core.hourly_slots(
                parse("2026-11-01T00:00:01Z"),
                parse("2026-11-01T00:59:59Z"),
            ),
            0,
        )

        self.assertEqual(
            core.hourly_slots(
                parse("2026-10-31T23:55:00Z"),
                parse("2026-11-02T00:55:01Z"),
            ),
            25,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
