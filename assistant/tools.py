"""Approved assistant tools. Python retrieves; the LLM never writes SQL."""

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


def is_energy_question(question):
    q = question.lower()
    return any(k in q for k in ENERGY_KEYWORDS)


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