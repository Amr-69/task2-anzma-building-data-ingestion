
"""Build an evidence packet for one incident from the database (read-only)."""

import sqlite3
import statistics
from datetime import datetime, timedelta

from alerting import config
from alerting.ai.actions import candidate_actions


FMT = "%Y-%m-%dT%H:%M:%SZ"


def _ts(value):
    return datetime.strptime(value, FMT)


def _fetch(db_path, inc):
    con = sqlite3.connect(str(db_path))

    try:
        con.execute("PRAGMA query_only = ON")

        asset_id, name, atype, loc, floor, system = con.execute(
            """SELECT a.asset_id, a.name, a.asset_type, l.name, l.floor, s.code
               FROM assets a
               JOIN locations l ON l.location_id = a.location_id
               JOIN system_types s ON s.system_type_id = a.system_type_id
               WHERE a.asset_code = ?""",
            (inc["asset_code"],),
        ).fetchone()

        unit = con.execute(
            "SELECT unit FROM metric_types WHERE name = ?",
            (inc["metric"],),
        ).fetchone()[0]

        first = inc["points"][0]["ts"]
        last = inc["last_abnormal_ts"]

        before = [
            row[0]
            for row in con.execute(
                """SELECT t.value
                   FROM telemetry_records t
                   JOIN metric_types m ON m.metric_id = t.metric_id
                   WHERE t.asset_id = ?
                     AND m.name = ?
                     AND t.ts < ?
                   ORDER BY t.ts DESC
                   LIMIT ?""",
                (asset_id, inc["metric"], first, config.WINDOW),
            )
        ]

        lo = (_ts(first) - timedelta(minutes=30)).strftime(FMT)
        hi = (_ts(last) + timedelta(minutes=30)).strftime(FMT)

        events = [
            {
                "event_id": row[0],
                "type": row[1],
                "severity": row[2],
                "ts": row[3],
                "details": row[4],
            }
            for row in con.execute(
                """SELECT e.event_id, et.name, e.severity, e.ts, e.details
                   FROM event_records e
                   JOIN event_types et
                     ON et.event_type_id = e.event_type_id
                   WHERE e.asset_id = ?
                     AND e.ts BETWEEN ? AND ?
                   ORDER BY e.ts
                   LIMIT 5""",
                (asset_id, lo, hi),
            )
        ]

    finally:
        con.close()

    asset = {
        "code": inc["asset_code"],
        "name": name,
        "type": atype,
        "system": system,
        "location": loc,
        "floor": floor,
    }

    return asset, unit, before, events


def _severity_explanation(inc):
    """Generate a factual severity explanation from detection results."""

    severity = inc["severity"]
    escalated_by = inc.get("escalated_by")
    points = inc["points"]

    critical_points = [
        point for point in points
        if point.get("level") == "critical"
    ]

    if critical_points:
        return (
            "Critical severity was assigned because at least one "
            "reading met a Critical-level detection condition."
        )

    if severity == "critical" and escalated_by == "sustained":
        required = config.SUSTAINED_READINGS

        return (
            "Critical severity was assigned because warning-level "
            "threshold violations persisted for at least "
            f"{required} readings. The critical threshold itself "
            "was not crossed."
        )

    if severity == "critical":
        return (
            "The detection engine classified this incident as Critical. "
            "Review the recorded detection and escalation reasons "
            "for further details."
        )

    if severity == "warning":
        return (
            "Warning severity was assigned because abnormal readings "
            "were detected without meeting the Critical-level "
            "classification conditions."
        )

    return (
        "The incident severity was supplied by the detection engine. "
        "No additional severity explanation is available."
    )


def build_evidence(db_path, inc):
    asset, unit, before, events = _fetch(db_path, inc)

    points = inc["points"]

    high = (
        config.THRESHOLDS[inc["metric"]]["direction"] == "high"
    )

    pick = max if high else min
    peak = pick(points, key=lambda point: point["value"])

    key_readings = []

    for point in (points[0], peak, points[-1]):
        if point["telemetry_id"] not in [
            reading["telemetry_id"] for reading in key_readings
        ]:
            key_readings.append(
                {
                    key: point[key]
                    for key in ("telemetry_id", "ts", "value", "z")
                }
            )

    duration = (
        int(
            (
                _ts(points[-1]["ts"]) - _ts(points[0]["ts"])
            ).total_seconds() // 60
        )
        + 5
    )

    normal = None

    if before:
        normal = {
            "median": round(statistics.median(before), 2),
            "min": min(before),
            "max": max(before),
            "count": len(before),
        }

    return {
        "asset": asset,
        "metric": inc["metric"],
        "unit": unit,

        "thresholds": config.THRESHOLDS[inc["metric"]],

        "severity": inc["severity"],
        "status": inc["status"],

        "escalated_by": inc.get("escalated_by"),
        "sustained": inc.get("sustained", False),
        "sustained_readings_required": config.SUSTAINED_READINGS,
        "severity_explanation": _severity_explanation(inc),

        "detection_reasons": sorted(
            {
                reason
                for point in points
                for reason in point["reasons"]
            }
        ),

        "readings_in_incident": len(points),
        "duration_minutes": duration,

        "normal_before": normal,
        "key_readings": key_readings,

        "all_telemetry_ids": [
            point["telemetry_id"] for point in points
        ],

        "related_events": events,
        "candidate_actions": candidate_actions(inc["metric"]),
    }
