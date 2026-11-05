"""Day 4 based tools: recent faults, network issues, corrective priorities.

Python detects, ranks and selects actions. The LLM never does any of this.
"""

from alerting.ai import actions, evidence
from alerting.detection import engine
from dashboard import dashboard_core as core

from assistant.services import resolve_scenario, resolve_time_range
from assistant.tools import check_building

NETWORK_METRICS = ("packet_loss_pct", "bandwidth_mbps", "cpu_load_pct")
SEVERITY_RANK = {"critical": 0, "warning": 1}


def _summarize(index, inc, ev):
    points = inc.get("points", [])
    worst = max(points, key=lambda p: abs(p.get("z") or 0)) if points else None
    ids, reasons = actions.select_actions(ev)
    text = {c["id"]: c["text"] for c in ev.get("candidate_actions", [])}

    return {
        "incident_index": index,
        "asset_code": inc["asset_code"],
        "metric": inc["metric"],
        "unit": ev.get("unit"),
        "severity": str(ev.get("severity", "")).lower(),
        "status": inc.get("status"),
        "start_ts": inc["start_ts"],
        "detected_ts": inc.get("detected_ts"),
        "duration_minutes": ev.get("duration_minutes"),
        "readings_in_incident": ev.get("readings_in_incident"),
        "peak_value": worst.get("value") if worst else None,
        "peak_z": round(abs(worst.get("z") or 0), 2) if worst else None,
        "peak_telemetry_id": worst.get("telemetry_id") if worst else None,
        "thresholds": ev.get("thresholds"),
        "detection_reasons": ev.get("detection_reasons"),
        "key_readings": ev.get("key_readings"),
        "normal_before": ev.get("normal_before"),
        "actions": [
            {"id": i, "text": text.get(i), "reason": reasons.get(i)} for i in ids
        ],
    }


def _incidents(scenario, window):
    """Day 4 incidents whose start falls inside the window."""

    _, db_path, _ = resolve_scenario(scenario)
    found = []
    for index, inc in enumerate(engine.detect(db_path)):
        if window["start"] <= inc["start_ts"] < window["end_exclusive"]:
            ev = evidence.build_evidence(db_path, inc)
            found.append(_summarize(index, inc, ev))
    return found


def _events(scenario, building_id, window, system=None):
    """Recorded warning/critical events (Day 2/3), read-only."""

    _, db_path, _ = resolve_scenario(scenario)
    sql = """
        SELECT er.event_id, a.asset_code, s.code AS system_type,
               et.name AS event_type, er.ts, er.severity
        FROM event_records er
        JOIN assets a ON a.asset_id = er.asset_id
        JOIN system_types s ON s.system_type_id = a.system_type_id
        JOIN locations l ON l.location_id = a.location_id
        JOIN event_types et ON et.event_type_id = er.event_type_id
        WHERE l.building_id = ?
          AND er.severity IN ('warning', 'critical')
          AND er.ts >= ? AND er.ts < ?
    """
    params = [building_id, window["start"], window["end_exclusive"]]
    if system:
        sql += " AND s.code = ?"
        params.append(system)
    sql += " ORDER BY er.ts, er.event_id"

    conn = core.open_readonly(db_path)
    try:
        rows = [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()
    return rows


def _counts(events):
    return {
        "critical": sum(1 for e in events if e["severity"] == "critical"),
        "warning": sum(1 for e in events if e["severity"] == "warning"),
    }


def rank_incidents(incidents):
    """Deterministic priority: severity, peak deviation, duration,
    open before resolved, then asset code and metric as a fixed tie-break."""

    def key(i):
        return (
            SEVERITY_RANK.get(i["severity"], 9),
            -(i["peak_z"] or 0),
            -(i["duration_minutes"] or 0),
            1 if i["status"] == "resolved" else 0,
            i["asset_code"],
            i["metric"],
        )

    ranked = sorted(incidents, key=key)
    for position, item in enumerate(ranked, start=1):
        item["priority"] = position
    return ranked


def get_recent_faults(building_id, scenario, hours=24):
    building = check_building(building_id, scenario)
    window = resolve_time_range(scenario, hours)
    events = _events(scenario, building_id, window)
    return {
        "building": building,
        "data_window": window,
        "incidents": _incidents(scenario, window),
        "events": events,
        "event_counts": _counts(events),
    }


def get_network_issues(building_id, scenario, hours=24):
    building = check_building(building_id, scenario)
    window = resolve_time_range(scenario, hours)
    incidents = [i for i in _incidents(scenario, window) if i["metric"] in NETWORK_METRICS]
    events = _events(scenario, building_id, window, system="NETWORKING")
    return {
        "building": building,
        "data_window": window,
        "metrics_checked": list(NETWORK_METRICS),
        "incidents": incidents,
        "events": events,
        "event_counts": _counts(events),
    }


def get_corrective_priorities(building_id, scenario, hours=24):
    building = check_building(building_id, scenario)
    window = resolve_time_range(scenario, hours)
    ranked = rank_incidents(_incidents(scenario, window))
    events = _events(scenario, building_id, window)
    return {
        "building": building,
        "data_window": window,
        "ranked": ranked,
        "events": events,
        "event_counts": _counts(events),
        "ranking_basis": [
            "severity", "peak deviation", "duration", "open before resolved",
        ],
    }