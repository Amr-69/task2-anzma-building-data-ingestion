"""Validate an LLM explanation against the evidence packet."""

import re

REQUIRED = {
    "summary",
    "cited_readings",
    "possible_causes",
    "recommended_action_ids",
    "evidence_limits",
}

DIGIT = re.compile(r"\d")


def validate(resp, ev):
    if not isinstance(resp, dict):
        return ["response is not a JSON object"]

    errors = []

    missing = REQUIRED - resp.keys()
    if missing:
        return ["missing field: " + field for field in sorted(missing)]

    for field in ("summary", "evidence_limits"):
        if not isinstance(resp[field], str) or not resp[field].strip():
            errors.append("invalid or empty field: " + field)

    for field in (
        "cited_readings",
        "possible_causes",
        "recommended_action_ids",
    ):
        if not isinstance(resp[field], list):
            errors.append(field + " must be a list")

    if errors:
        return errors

    # LLM prose must not introduce numerical claims.
    prose_fields = {
        "summary": resp["summary"],
        "evidence_limits": resp["evidence_limits"],
    }

    for field, value in prose_fields.items():
        if DIGIT.search(value):
            errors.append(
                f"{field} must not contain numbers; "
                "use the code-generated evidence instead"
            )

    key_ids = {k["telemetry_id"] for k in ev["key_readings"]}
    cited = resp["cited_readings"]

    if not cited:
        errors.append("no readings cited")

    if any(type(c) is not int for c in cited):
        errors.append("cited_readings must contain integer telemetry IDs")
    else:
        if len(cited) != len(set(cited)):
            errors.append("duplicate telemetry citations")

        for c in cited:
            if c not in key_ids:
                errors.append(f"cited reading {c} is not in the evidence")

    candidates = {a["id"] for a in ev["candidate_actions"]}
    actions = resp["recommended_action_ids"]

    if not actions:
        errors.append("no recommended action")

    if any(not isinstance(a, str) for a in actions):
        errors.append("recommended action IDs must be strings")
    else:
        if len(actions) != len(set(actions)):
            errors.append("duplicate recommended action IDs")

        for action in actions:
            if action not in candidates:
                errors.append(f"action {action} is not a candidate action")

    causes = resp["possible_causes"]

    if not causes:
        errors.append("no possible causes")

    for cause in causes:
        if not isinstance(cause, str) or not cause.strip():
            errors.append("possible causes must be non-empty strings")
        elif not cause.strip().startswith("Possible:"):
            errors.append("possible cause must start with 'Possible:'")
        elif DIGIT.search(cause):
            errors.append("possible causes must not contain numbers")

    return errors