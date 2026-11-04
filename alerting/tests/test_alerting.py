
"""Focused regression tests for Day 4 alerting."""

import sqlite3
from pathlib import Path

import pytest

from alerting.ai.evidence import build_evidence
from alerting.ai.explain import explain_incident
from alerting.ai.validator import validate
from alerting.detection.engine import (
    analyze_series,
    detect,
    directional_z,
    threshold_level,
)


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "data" / "anzma_building.db"
SCENARIOS = ROOT / "alerting" / "scenarios" / "generated"


# --------------------------------------------------
# Threshold detection
# --------------------------------------------------

@pytest.mark.parametrize(
    "metric,value,expected",
    [
        ("cpu_load_pct", 90.0, None),
        ("cpu_load_pct", 91.0, "warning"),
        ("cpu_load_pct", 96.0, "critical"),
        ("fan_speed_pct", 20.0, None),
        ("fan_speed_pct", 19.0, "warning"),
        ("fan_speed_pct", 9.0, "critical"),
    ],
)
def test_threshold_boundaries(metric, value, expected):
    assert threshold_level(metric, value) == expected


def test_directional_z_score():
    high_z = directional_z("cpu_load_pct", 30, [10] * 12)
    low_z = directional_z("fan_speed_pct", 30, [50] * 12)

    assert high_z > 0
    assert low_z > 0


# --------------------------------------------------
# Incident lifecycle
# --------------------------------------------------

def test_incident_opens_and_resolves():
    rows = []

    # Twelve normal readings establish the baseline.
    for i in range(12):
        rows.append((i + 1, f"2026-11-01T00:{i * 5:02d}:00Z", 50.0))

    # Two abnormal fan-speed readings.
    rows.extend([
        (13, "2026-11-01T01:00:00Z", 5.0),
        (14, "2026-11-01T01:05:00Z", 5.0),
    ])

    # Three normal readings resolve the incident.
    rows.extend([
        (15, "2026-11-01T01:10:00Z", 50.0),
        (16, "2026-11-01T01:15:00Z", 50.0),
        (17, "2026-11-01T01:20:00Z", 50.0),
    ])

    incidents = analyze_series("TEST-FAN", "fan_speed_pct", rows)

    assert len(incidents) == 1
    assert incidents[0]["status"] == "resolved"
    assert incidents[0]["severity"] == "critical"
    assert len(incidents[0]["points"]) == 2


# --------------------------------------------------
# Scenario regression
# --------------------------------------------------

@pytest.mark.parametrize(
    "scenario,asset,metric",
    [
        ("S1", "HVAC-AHU-02", "supply_air_temp"),
        ("S2", "HVAC-AHU-01", "fan_speed_pct"),
        ("S3", "NET-SW-2", "packet_loss_pct"),
        ("S4", "NET-CORE-01", "cpu_load_pct"),
        ("S5", "NET-SW-3", "bandwidth_mbps"),
    ],
)
def test_fault_scenarios(scenario, asset, metric):
    database = SCENARIOS / f"{scenario}.db"

    incidents = detect(database)

    assert len(incidents) == 1
    assert incidents[0]["asset_code"] == asset
    assert incidents[0]["metric"] == metric
    assert incidents[0]["severity"] == "critical"
    assert incidents[0]["status"] == "resolved"


def test_clean_baseline_has_no_incidents():
    assert detect(BASELINE) == []


# --------------------------------------------------
# Evidence traceability
# --------------------------------------------------

@pytest.mark.parametrize("scenario", ["S1", "S2", "S3", "S4", "S5"])
def test_evidence_citations_match_database(scenario):
    database = SCENARIOS / f"{scenario}.db"
    incidents = detect(database)

    assert len(incidents) == 1

    evidence = build_evidence(database, incidents[0])

    with sqlite3.connect(database) as connection:
        for reading in evidence["key_readings"]:
            row = connection.execute(
                """
                SELECT a.asset_code, m.name, t.value, t.ts
                FROM telemetry_records t
                JOIN assets a ON a.asset_id = t.asset_id
                JOIN metric_types m ON m.metric_id = t.metric_id
                WHERE t.telemetry_id = ?
                """,
                (reading["telemetry_id"],),
            ).fetchone()

            assert row is not None
            assert row[0] == evidence["asset"]["code"]
            assert row[1] == evidence["metric"]
            assert row[2] == reading["value"]
            assert row[3] == reading["ts"]


# --------------------------------------------------
# AI output validation
# --------------------------------------------------

def valid_evidence():
    return {
        "key_readings": [
            {"telemetry_id": 101},
            {"telemetry_id": 102},
        ],
        "candidate_actions": [
            {"id": "CPU-1"},
            {"id": "CPU-2"},
        ],
    }


def valid_response():
    return {
        "summary": "The equipment shows an abnormal operating condition.",
        "cited_readings": [101, 102],
        "possible_causes": [
            "Possible: an unusually demanding process may be affecting the equipment."
        ],
        "recommended_action_ids": ["CPU-1"],
        "evidence_limits": "The available telemetry cannot confirm the underlying cause.",
    }


def test_validator_accepts_valid_response():
    assert validate(valid_response(), valid_evidence()) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("cited_readings", [999]),
        ("cited_readings", [101, 101]),
        ("cited_readings", ["101"]),
        ("recommended_action_ids", ["UNKNOWN"]),
        ("recommended_action_ids", ["CPU-1", "CPU-1"]),
        ("summary", "The fault occurred at 10 percent."),
        ("possible_causes", ["The motor may have failed."]),
    ],
)
def test_validator_rejects_invalid_response(field, value):
    response = valid_response()
    response[field] = value

    assert validate(response, valid_evidence())


# --------------------------------------------------
# AI fallback
# --------------------------------------------------

@pytest.mark.parametrize("failure_type", ["exception", "invalid_response"])
def test_ai_fallback_when_llm_fails(monkeypatch, failure_type):
    database = SCENARIOS / "S1.db"
    incidents = detect(database)

    def fake_ollama(evidence, model):
        if failure_type == "exception":
            raise RuntimeError("Simulated Ollama failure")

        return {"possible_causes": ["Unsupported cause"]}

    monkeypatch.setattr(
        "alerting.ai.explain.call_ollama",
        fake_ollama,
    )

    result = explain_incident(database, incidents[0])

    assert result["source"] == "template"
    assert result["validation_errors"]
    assert result["explanation"]["possible_causes"]
    assert result["explanation"]["cited_readings"]
    assert result["explanation"]["recommended_action_ids"]
