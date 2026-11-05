"""Approved assistant tools. Python retrieves; the LLM never writes SQL."""

from statistics import median

from dashboard import dashboard_core as core

from assistant.services import (
    AssistantError,
    resolve_scenario,
    resolve_time_range,
)

ENERGY_KEYWORDS = (
    "energy", "kwh", "electricity", "power consumption",
    "الطاقة", "الكهرباء", "كهرباء", "استهلاك",
)
CCTV_KEYWORDS = ("cctv", "camera", "كاميرا", "كاميرات", "المراقبة")
STATUS_KEYWORDS = ("status", "building", "condition", "حالة", "مبنى", "وضع")

SEVERITY_ORDER = {"critical": 0, "warning": 1, "no_data": 2, "normal": 3}


def is_energy_question(question):
    q = question.lower()
    return any(k in q for k in ENERGY_KEYWORDS)


def classify_question(question):
    """Keyword routing. Energy is checked first so it can never be answered
    with other data. The LLM router (step 4) will sit on top of this."""

    q = question.lower()
    if any(k in q for k in ENERGY_KEYWORDS):
        return "energy_consumption"
    if any(k in q for k in CCTV_KEYWORDS):
        return "cctv_availability"
    if any(k in q for k in STATUS_KEYWORDS):
        return "building_status"
    return None


def check_building(building_id, scenario):
    _, db_path, _ = resolve_scenario(scenario)
    conn = core.open_readonly(db_path)
    try:
        row = conn.execute(
            "SELECT building_id, name FROM buildings WHERE building_id = ?",
            (building_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise AssistantError(
            f"Unknown building_id {building_id}.", 404, "unknown_building"
        )
    return {"building_id": row["building_id"], "name": row["name"]}


# ------------------------------------------------------------
# Q6 energy
# ------------------------------------------------------------

def get_energy_consumption_change(building_id, scenario, hours=24):
    """Always an explicit unsupported-data result. Never estimates energy."""

    building = check_building(building_id, scenario)
    window = resolve_time_range(scenario, hours)
    _, db_path, _ = resolve_scenario(scenario)

    conn = core.open_readonly(db_path)
    try:
        metrics = [
            {"name": r["name"], "unit": r["unit"]}
            for r in conn.execute(
                "SELECT name, unit FROM metric_types ORDER BY name"
            )
        ]
    finally:
        conn.close()

    return {
        "status": "unavailable",
        "reason": "no_energy_consumption_telemetry",
        "building": building,
        "data_window": window,
        "available_metrics": metrics,
    }


# ------------------------------------------------------------
# Q1 building status (reuses Day 3 build_overview)
# ------------------------------------------------------------

def get_building_status(building_id, scenario, hours=24):
    building = check_building(building_id, scenario)
    window = resolve_time_range(scenario, hours)
    _, db_path, _ = resolve_scenario(scenario)

    conn = core.open_readonly(db_path)
    try:
        try:
            overview = core.build_overview(
                conn, None, building_id,
                window["start"], window["end_exclusive"],
            )
        except core.DashboardError as exc:
            raise AssistantError(str(exc), 422, "dashboard_error") from exc
    finally:
        conn.close()

    assets = overview["assets"]
    counts = {"normal": 0, "warning": 0, "critical": 0, "no_data": 0}
    for a in assets:
        counts[a["status"]] = counts.get(a["status"], 0) + 1

    attention = [
        {
            "asset_code": a["asset_code"],
            "system_type": a["system_type"],
            "status": a["status"],
            "status_reason": a["status_reason"],
            "warnings": a["warnings"],
            "criticals": a["criticals"],
        }
        for a in assets
        if a["status"] != "normal"
    ]
    attention.sort(key=lambda a: (SEVERITY_ORDER.get(a["status"], 9), a["asset_code"]))

    return {
        "building": building,
        "data_window": window,
        "period": overview["period"],
        "total_assets": len(assets),
        "status_counts": counts,
        "warning_events": sum(a["warnings"] for a in assets),
        "critical_events": sum(a["criticals"] for a in assets),
        "by_system": overview["health"]["by_system"],
        "kpis": [
            {k: kpi.get(k) for k in ("key", "name", "unit", "value", "applicable", "detail")}
            for kpi in overview["kpis"]
        ],
        "attention": attention,
    }


# ------------------------------------------------------------
# Q3 CCTV availability (heartbeat-based, inferred)
# ------------------------------------------------------------

def get_cctv_availability(building_id, scenario, hours=24):
    building = check_building(building_id, scenario)
    window = resolve_time_range(scenario, hours)
    _, db_path, _ = resolve_scenario(scenario)

    start, end = window["start"], window["end_exclusive"]
    window_seconds = int(
        (core.parse_utc_timestamp(end) - core.parse_utc_timestamp(start)).total_seconds()
    )

    conn = core.open_readonly(db_path)
    try:
        cameras = conn.execute(
            """
            SELECT a.asset_id, a.asset_code
            FROM assets a
            JOIN system_types s ON s.system_type_id = a.system_type_id
            JOIN locations l ON l.location_id = a.location_id
            WHERE s.code = 'CCTV' AND l.building_id = ?
            ORDER BY a.asset_code
            """,
            (building_id,),
        ).fetchall()

        results = []
        for cam in cameras:
            heartbeats = [
                r["ts"]
                for r in conn.execute(
                    """
                    SELECT er.ts FROM event_records er
                    JOIN event_types et ON et.event_type_id = er.event_type_id
                    WHERE er.asset_id = ? AND et.name = ?
                    ORDER BY er.ts
                    """,
                    (cam["asset_id"], core.HEARTBEAT_EVENT),
                )
            ]
            in_window = [ts for ts in heartbeats if start <= ts < end]

            interval = None
            if len(heartbeats) >= 2:
                parsed = [core.parse_utc_timestamp(ts) for ts in heartbeats]
                gaps = [
                    (b - a).total_seconds() for a, b in zip(parsed, parsed[1:])
                ]
                interval = int(median(gaps))

            expected = (
                round(window_seconds / interval) if interval else None
            )
            pct = (
                round(min(100.0, len(in_window) / expected * 100), 1)
                if expected
                else None
            )

            state_events = [
                {
                    "event_id": r["event_id"],
                    "event_type": r["name"],
                    "ts": r["ts"],
                    "severity": r["severity"],
                }
                for r in conn.execute(
                    """
                    SELECT er.event_id, et.name, er.ts, er.severity
                    FROM event_records er
                    JOIN event_types et ON et.event_type_id = er.event_type_id
                    WHERE er.asset_id = ?
                      AND et.name IN ('camera_offline', 'camera_online')
                      AND er.ts >= ? AND er.ts < ?
                    ORDER BY er.ts, er.event_id
                    """,
                    (cam["asset_id"], start, end),
                )
            ]

            results.append(
                {
                    "asset_code": cam["asset_code"],
                    "heartbeats_in_window": len(in_window),
                    "expected_heartbeats": expected,
                    "heartbeat_interval_seconds": interval,
                    "availability_pct": pct,
                    "last_heartbeat": in_window[-1] if in_window else None,
                    "state_events": state_events,
                    "offline_events": sum(
                        1 for e in state_events if e["event_type"] == "camera_offline"
                    ),
                }
            )
    finally:
        conn.close()

    total_hb = sum(c["heartbeats_in_window"] for c in results)
    total_expected = sum(c["expected_heartbeats"] or 0 for c in results)
    overall = (
        round(min(100.0, total_hb / total_expected * 100), 1)
        if total_expected
        else None
    )

    disagreements = [
        {
            "asset_code": c["asset_code"],
            "offline_ts": next(
                e["ts"] for e in c["state_events"] if e["event_type"] == "camera_offline"
            ),
        }
        for c in results
        if c["offline_events"] > 0 and c["heartbeats_in_window"] > 0
    ]

    return {
        "building": building,
        "data_window": window,
        "cameras_observed": len(results),
        "cameras_reporting": sum(1 for c in results if c["heartbeats_in_window"] > 0),
        "without_heartbeat": [c["asset_code"] for c in results if c["heartbeats_in_window"] == 0],
        "total_heartbeats": total_hb,
        "total_expected": total_expected,
        "availability_pct": overall,
        "cameras": results,
        "disagreements": disagreements,
        "availability_basis": "inferred_from_heartbeat",
    }