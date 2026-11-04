"""AI explanation layer: Ollama suggests causes; Python supplies facts."""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from alerting.ai.actions import select_actions
from alerting.ai.evidence import build_evidence
from alerting.detection.engine import detect


MODEL = "qwen2.5:3b"
OLLAMA_URL = "http://localhost:11434/api/chat"
ROOT = Path(__file__).resolve().parents[2]

REQUEST_TIMEOUT = 90
MAX_CAUSES = 2


SYSTEM = """You assist an operations engineer investigating building-system
incidents.

Your ONLY task is to suggest possible causes.

Use ONLY the evidence JSON provided.

Rules:
1. Return one or two possible causes.
2. Every cause MUST begin with the exact prefix 'Possible:'.
3. Causes are hypotheses, not confirmed facts.
4. Base hypotheses on the supplied metric, incident evidence,
   and candidate corrective actions.
5. Do not invent equipment, components, events, or measurements.
6. You may reference only numbers that appear in the supplied evidence.
   Do not invent numbers, dates, percentages, timestamps, asset codes,
   or telemetry IDs.
7. Do not recommend actions. Python supplies corrective actions.
8. Do not repeat the incident summary.
9. If evidence is insufficient, state that as a hypothesis limitation.

Return JSON only."""


SCHEMA = {
    "type": "object",
    "properties": {
        "possible_causes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["possible_causes"],
}


def call_ollama(ev, model=MODEL):
    """Ask Ollama only for possible causes."""

    packet = {
        "asset": ev["asset"],
        "metric": ev["metric"],
        "severity": ev["severity"],
        "detection_reasons": ev["detection_reasons"],
        "thresholds": ev["thresholds"],
        "normal_before": ev["normal_before"],
        "key_readings": ev["key_readings"],
        "related_events": ev["related_events"],
        "candidate_actions": ev["candidate_actions"],
    }

    user = (
        "Suggest possible causes for this incident. "
        "Return only the requested JSON structure.\n\n"
        + json.dumps(packet)
    )

    body = {
        "model": model,
        "stream": False,
        "format": SCHEMA,
        "options": {
            "temperature": 0,
            "num_ctx": 4096,
            "num_predict": 180,
        },
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(
        request,
        timeout=REQUEST_TIMEOUT,
    ) as response:
        result = json.loads(response.read())

    return json.loads(result["message"]["content"])


def _number_variants(value):
    """Return common textual representations of an evidence-backed number."""

    if value is None:
        return set()

    variants = set()

    try:
        variants.add(str(value))
        variants.add(f"{float(value):g}")
    except (TypeError, ValueError):
        pass

    return variants


def _allowed_numbers(ev):
    """Collect numeric strings that already exist in the evidence packet."""

    allowed = set()

    thresholds = ev.get("thresholds") or {}
    allowed.update(_number_variants(thresholds.get("warning")))
    allowed.update(_number_variants(thresholds.get("critical")))

    for reading in ev.get("key_readings") or []:
        allowed.update(_number_variants(reading.get("value")))
        allowed.update(_number_variants(reading.get("z")))
        allowed.update(_number_variants(reading.get("telemetry_id")))

    normal = ev.get("normal_before") or {}
    for key in ("median", "min", "max", "count"):
        allowed.update(_number_variants(normal.get(key)))

    allowed.update(_number_variants(ev.get("duration_minutes")))
    allowed.update(_number_variants(ev.get("readings_in_incident")))
    allowed.update(_number_variants(ev.get("sustained_readings_required")))

    return allowed


def validate_causes(response, ev):
    """Validate LLM-generated hypotheses against evidence-backed numbers."""

    if not isinstance(response, dict):
        return ["response must be a JSON object"]

    causes = response.get("possible_causes")

    if not isinstance(causes, list):
        return ["possible_causes must be a list"]

    errors = []

    if not causes:
        errors.append("no possible causes returned")

    if len(causes) > MAX_CAUSES:
        errors.append(
            f"no more than {MAX_CAUSES} possible causes are allowed"
        )

    allowed = _allowed_numbers(ev)

    for cause in causes:
        if not isinstance(cause, str) or not cause.strip():
            errors.append("possible causes must be non-empty strings")
            continue

        cause = cause.strip()

        if not cause.startswith("Possible:"):
            errors.append(
                "every possible cause must start with 'Possible:'"
            )

        for number in re.findall(r"\d+(?:\.\d+)?", cause):
            if number not in allowed:
                errors.append(
                    "possible causes contain unsupported numerical value: "
                    + number
                )

    return errors


def template_causes():
    """Provide a safe fallback when AI output is unavailable."""

    return [
        "Possible: a fault in the equipment serving this metric "
        "(not confirmed by the available data)."
    ]


def _extreme_reading(ev):
    """Key reading furthest toward the failure side of the metric."""

    high = ev["thresholds"]["direction"] == "high"
    pick = max if high else min

    return pick(ev["key_readings"], key=lambda reading: reading["value"])


def _crossed_critical(ev, value):
    """True when the value passed the configured critical threshold."""

    thresholds = ev["thresholds"]

    if thresholds["direction"] == "high":
        return value > thresholds["critical"]

    return value < thresholds["critical"]


def build_summary(ev):
    """Factual summary built only from the evidence packet.

    This text is generated by Python from database readings. It is not
    model prose, so it is allowed to contain numbers.
    """

    reading = _extreme_reading(ev)
    unit = ev["unit"]
    thresholds = ev["thresholds"]
    z_score = "not available" if reading["z"] is None else reading["z"]

    if _crossed_critical(ev, reading["value"]):
        threshold_sentence = (
            "That reading crossed the configured critical threshold."
        )
    else:
        threshold_sentence = (
            "That reading did not cross the configured critical threshold."
        )

    sustained_sentence = ""

    if ev.get("escalated_by") == "sustained":
        sustained_sentence = (
            " Severity was escalated because warning-level readings "
            f'persisted for at least {ev["sustained_readings_required"]} '
            "readings."
        )

    return (
        f'{ev["asset"]["code"]} has a {ev["severity"]} incident '
        f'on {ev["metric"]}. '
        f'The most extreme reading was {reading["value"]} {unit} '
        f'at {reading["ts"]} '
        f'(telemetry_id {reading["telemetry_id"]}, z-score {z_score}). '
        f'Configured thresholds: warning {thresholds["warning"]} {unit}, '
        f'critical {thresholds["critical"]} {unit}. '
        f"{threshold_sentence} "
        f'Detection reasons: {", ".join(ev["detection_reasons"])}.'
        f"{sustained_sentence}"
    )


def build_python_explanation(ev):
    """Generate factual explanation fields deterministically."""

    action_ids, action_reasons = select_actions(ev)

    return {
        "summary": build_summary(ev),
        "cited_readings": [
            reading["telemetry_id"]
            for reading in ev["key_readings"]
        ],
        "recommended_action_ids": action_ids,
        "action_reasons": action_reasons,
        "evidence_limits": (
            "The available telemetry establishes an abnormal condition "
            "but cannot independently establish its underlying root cause."
        ),
    }


def explain_incident(db_path, incident, model=MODEL):
    """Generate factual fields in Python and request causes once."""

    start = time.time()

    evidence = build_evidence(db_path, incident)
    explanation = build_python_explanation(evidence)

    errors = []
    attempts = 0
    source = "template"

    try:
        attempts = 1

        response = call_ollama(evidence, model)
        errors = validate_causes(response, evidence)

        if not errors:
            explanation["possible_causes"] = response["possible_causes"]
            source = "llm"
        else:
            explanation["possible_causes"] = template_causes()

    except Exception as exc:
        errors = ["ollama error: " + str(exc)]
        explanation["possible_causes"] = template_causes()

    return {
        "evidence": evidence,
        "explanation": explanation,
        "source": source,
        "model": model,
        "attempts": attempts,
        "validation_errors": errors,
        "seconds": round(time.time() - start, 1),
    }


def render(result):
    """Render hypotheses and code-generated incident evidence."""

    evidence = result["evidence"]
    explanation = result["explanation"]

    readings = {
        reading["telemetry_id"]: reading
        for reading in evidence["key_readings"]
    }

    actions = {
        action["id"]: action["text"]
        for action in evidence["candidate_actions"]
    }

    thresholds = evidence["thresholds"]
    normal = evidence.get("normal_before") or {}
    asset = evidence["asset"]

    source_label = (
        "LLM CAUSES + PYTHON FACTS"
        if result["source"] == "llm"
        else "TEMPLATE CAUSES + PYTHON FACTS"
    )

    print("\n" + "=" * 65)

    print(
        f'[{source_label}] '
        f'{asset["code"]} / {evidence["metric"]} / '
        f'{evidence["severity"].upper()}'
    )

    print(
        f'Generation time: {result["seconds"]}s | '
        f'LLM attempts: {result["attempts"]}'
    )

    print("\nEXPLANATION")
    print(explanation["summary"])

    print("\nSEVERITY JUSTIFICATION")
    print(evidence["severity_explanation"])

    print("\nINCIDENT DETAILS")
    print(f'Asset: {asset["name"]}')
    print(f'Asset code: {asset["code"]}')
    print(f'Location: {asset["location"]}')
    print(f'Floor: {asset["floor"]}')
    print(f'System: {asset["system"]}')
    print(f'Metric: {evidence["metric"]}')
    print(f'Status: {evidence["status"]}')
    print(f'Severity: {evidence["severity"]}')
    print(f'Readings in incident: {evidence["readings_in_incident"]}')
    print(f'Duration: {evidence["duration_minutes"]} minutes')
    print(f'Detection reasons: {evidence["detection_reasons"]}')
    print(f'Escalated by: {evidence["escalated_by"]}')
    print(f'Sustained: {evidence["sustained"]}')

    print("\nTHRESHOLDS")
    print(f'Direction: {thresholds["direction"]}')
    print(f'Warning: {thresholds["warning"]} {evidence["unit"]}')
    print(f'Critical: {thresholds["critical"]} {evidence["unit"]}')

    print("\nNORMAL BASELINE")

    if normal:
        print(f'Median: {normal["median"]} {evidence["unit"]}')
        print(f'Minimum: {normal["min"]} {evidence["unit"]}')
        print(f'Maximum: {normal["max"]} {evidence["unit"]}')
        print(f'Sample count: {normal["count"]}')
    else:
        print("No baseline statistics available.")

    print("\nEVIDENCE READINGS")

    for citation in explanation["cited_readings"]:
        reading = readings[citation]

        print(
            f'  telemetry_id {citation}: '
            f'{reading["value"]} {evidence["unit"]} '
            f'at {reading["ts"]} '
            f'(z-score: {reading["z"]})'
        )

    print("\nPOSSIBLE CAUSES")

    for cause in explanation["possible_causes"]:
        print("  -", cause)

    print("\nRECOMMENDED ACTIONS")

    for action_id in explanation["recommended_action_ids"]:
        print(f'  {action_id}: {actions[action_id]}')

        reason = explanation.get("action_reasons", {}).get(action_id)

        if reason:
            print(f'      Why: {reason}')

    print("\nEVIDENCE LIMITATIONS")
    print(explanation["evidence_limits"])

    print("\nRELATED EVENTS")

    related_events = evidence.get("related_events") or []

    if related_events:
        for event in related_events:
            print(
                f'  Event ID: {event["event_id"]} | '
                f'Type: {event["type"]} | '
                f'Severity: {event["severity"]} | '
                f'Timestamp: {event["ts"]}'
            )

            if event.get("details"):
                print(f'  Details: {event["details"]}')
    else:
        print("  No related events were recorded.")

    if result.get("validation_errors"):
        print("\nLLM VALIDATION / GENERATION ISSUES")

        for error in result["validation_errors"]:
            print("  -", error)

    print("=" * 65)


if __name__ == "__main__":
    scenario_name = (
        sys.argv[1] if len(sys.argv) > 1 else "S2"
    )

    database = (
        ROOT
        / "alerting"
        / "scenarios"
        / "generated"
        / (scenario_name + ".db")
    )

    if not database.exists():
        print(f"Scenario database not found: {database}")
        sys.exit(1)

    incidents = detect(database)

    if not incidents:
        print(f"No incidents detected in {scenario_name}.")
        sys.exit(0)

    for incident in incidents:
        result = explain_incident(database, incident)
        render(result)