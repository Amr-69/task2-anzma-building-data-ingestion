from datetime import datetime
from pathlib import Path
import sqlite3

import pytest

from assistant.incident_tools import (
    get_corrective_priorities,
    get_network_issues,
    get_recent_faults,
    rank_incidents,
)
from assistant.services import resolve_scenario


def _db(scenario: str) -> Path:
    _, db_path, _ = resolve_scenario(scenario)
    return Path(db_path)


def _building_id(scenario: str) -> str:
    db_path = _db(scenario)
    uri = f"file:{db_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row = conn.execute(
            "SELECT building_id FROM buildings ORDER BY building_id LIMIT 1"
        ).fetchone()

    assert row is not None
    return row[0]


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_s1_returns_hvac_incident():
    building_id = _building_id("S1")
    packet = get_recent_faults(building_id, "S1", hours=24)

    hvac_incidents = [
        incident
        for incident in packet["incidents"]
        if incident["asset_code"] == "HVAC-AHU-02"
        and incident["metric"] == "supply_air_temp"
    ]

    assert len(hvac_incidents) == 1
    incident = hvac_incidents[0]
    assert incident["severity"] in {"critical", "warning"}
    assert _utc(incident["start_ts"]) == _utc("2026-11-01T10:10:00Z")


def test_baseline_has_no_incidents_but_has_events():
    building_id = _building_id("baseline")

    fault_packet = get_recent_faults(building_id, "baseline", hours=24)
    network_packet = get_network_issues(building_id, "baseline", hours=24)

    assert fault_packet["incidents"] == []
    assert len(network_packet["events"]) > 0


def test_six_hour_window_excludes_s1_incident():
    building_id = _building_id("S1")
    packet = get_recent_faults(building_id, "S1", hours=6)

    hvac_incidents = [
        incident
        for incident in packet["incidents"]
        if incident["asset_code"] == "HVAC-AHU-02"
        and incident["metric"] == "supply_air_temp"
    ]

    assert hvac_incidents == []


def test_s3_returns_packet_loss_incident():
    building_id = _building_id("S3")
    packet = get_recent_faults(building_id, "S3", hours=24)

    network_incidents = [
        incident
        for incident in packet["incidents"]
        if incident["asset_code"] == "NET-SW-2"
        and incident["metric"] == "packet_loss_pct"
    ]

    assert len(network_incidents) == 1
    incident = network_incidents[0]
    assert incident["severity"] in {"critical", "warning"}
    assert _utc(incident["start_ts"]) == _utc("2026-11-01T18:00:00Z")


def test_s1_has_no_packet_loss_incident():
    building_id = _building_id("S1")
    packet = get_network_issues(building_id, "S1", hours=24)

    packet_loss_incidents = [
        incident
        for incident in packet["incidents"]
        if incident["metric"] == "packet_loss_pct"
    ]

    assert packet_loss_incidents == []
    assert len(packet["events"]) > 0


def test_priorities_use_approved_catalog_ids():
    building_id = _building_id("S1")
    packet = get_corrective_priorities(building_id, "S1", hours=24)
    ranked = packet["ranked"]

    assert len(ranked) > 0
    approved = {"SAT-1", "SAT-2", "SAT-3", "PL-1", "PL-2", "PL-3"}

    for incident in ranked:
        assert incident["actions"], "Every ranked incident must propose actions"
        for action in incident["actions"]:
            assert action["id"] in approved
            assert isinstance(action["reason"], str)
            assert action["reason"]


def test_baseline_priorities_are_empty():
    building_id = _building_id("baseline")
    packet = get_corrective_priorities(building_id, "baseline", hours=24)

    assert packet["ranked"] == []


@pytest.mark.parametrize("scenario", ["S1", "S3"])
def test_severity_is_valid(scenario):
    building_id = _building_id(scenario)
    packet = get_recent_faults(building_id, scenario, hours=24)

    assert len(packet["incidents"]) > 0
    for incident in packet["incidents"]:
        assert incident["severity"] in {"critical", "warning"}


def test_ranking_is_deterministic_b_c_a():
    incidents = [
        {
            "asset_code": "A",
            "metric": "m",
            "severity": "warning",
            "peak_z": 2.0,
            "duration_minutes": 30,
            "status": "open",
            "start_ts": "2026-11-01T10:00:00Z",
        },
        {
            "asset_code": "B",
            "metric": "m",
            "severity": "critical",
            "peak_z": 3.0,
            "duration_minutes": 40,
            "status": "open",
            "start_ts": "2026-11-01T11:00:00Z",
        },
        {
            "asset_code": "C",
            "metric": "m",
            "severity": "critical",
            "peak_z": 3.0,
            "duration_minutes": 40,
            "status": "open",
            "start_ts": "2026-11-01T12:00:00Z",
        },
    ]

    ranked = rank_incidents(incidents)

    assert [item["asset_code"] for item in ranked] == ["B", "C", "A"]
    assert rank_incidents(incidents) == ranked