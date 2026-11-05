"""Day 3 dashboard and Day 4 alert API.

Day 3 routes continue to use the original baseline database.
Day 4 alert routes use a fixed allowlist of read-only scenario databases.
"""

import re
import sqlite3
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import dashboard_core as core
from alerting.detection.engine import detect
from alerting.ai.explain import explain_incident


STATIC_DIR = Path(__file__).resolve().parent / "static"

ROOT_DIR = Path(__file__).resolve().parents[1]
SCENARIO_DIR = ROOT_DIR / "alerting" / "scenarios" / "generated"

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])
ui_router = APIRouter()


# Fixed scenario allowlist. Custom scenarios are resolved safely from the
# generated scenario directory only when their database already exists.
SCENARIOS = {
    "baseline": {
        "name": "Baseline",
        "description": "Original building telemetry without injected faults.",
        "path": ROOT_DIR / "data" / "anzma_building.db",
    },
    "S1": {
        "name": "S1 - Cooling failure",
        "description": "HVAC-AHU-02 supply air temperature rises.",
        "path": SCENARIO_DIR / "S1.db",
    },
    "S2": {
        "name": "S2 - Fan collapse",
        "description": "HVAC-AHU-01 fan speed drops.",
        "path": SCENARIO_DIR / "S2.db",
    },
    "S3": {
        "name": "S3 - Packet loss",
        "description": "NET-SW-2 experiences a packet loss burst.",
        "path": SCENARIO_DIR / "S3.db",
    },
    "S4": {
        "name": "S4 - CPU overload",
        "description": "NET-CORE-01 experiences sustained CPU load.",
        "path": SCENARIO_DIR / "S4.db",
    },
    "S5": {
        "name": "S5 - Bandwidth collapse",
        "description": "NET-SW-3 bandwidth drops.",
        "path": SCENARIO_DIR / "S5.db",
    },
}


SAFE_SCENARIO_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def open_database():
    """Open the original Day 3 database read-only."""

    if not core.DB_PATH.is_file():
        raise HTTPException(
            status_code=503,
            detail="Database file does not exist. Initialize the database first.",
        )

    try:
        return core.open_readonly()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to connect to the database.",
        ) from exc


def run_query(function, *args):
    """Run one Day 3 dashboard query and translate errors."""

    conn = open_database()

    try:
        return function(conn, *args)

    except core.NoDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except core.DashboardError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Dashboard query failed.",
        ) from exc

    finally:
        conn.close()


def get_scenario(scenario):
    """Resolve a fixed or validated custom scenario to a read-only database."""

    if not isinstance(scenario, str) or not scenario.strip():
        raise HTTPException(
            status_code=400,
            detail="A scenario must be selected.",
        )

    scenario = scenario.strip()
    selected = SCENARIOS.get(scenario)

    if selected is not None:
        database = selected["path"]
    else:
        # Custom scenarios must use a safe ID and must already exist in the
        # generated scenario directory. This prevents arbitrary file access.
        if not SAFE_SCENARIO_ID.fullmatch(scenario):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid scenario ID. Use baseline, S1 through S5, or a "
                    "custom scenario ID containing only letters, numbers, "
                    "hyphens and underscores."
                ),
            )

        database = SCENARIO_DIR / f"{scenario}.db"

        if not database.is_file():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Unknown scenario. Select baseline, S1 through S5, or an "
                    "existing custom scenario."
                ),
            )

        selected = {
            "name": f"Custom scenario - {scenario}",
            "description": "User-generated validated scenario.",
            "path": database,
        }

    if not database.is_file():
        raise HTTPException(
            status_code=503,
            detail=f"The database for {scenario} is unavailable.",
        )

    return selected, database


@router.get("/filters")
def get_filters():
    """Systems, buildings and the time extent of stored data."""

    return run_query(core.get_filter_options)


@router.get("/overview")
def get_overview(
    system_type: str | None = Query(default=None),
    building_id: int | None = Query(default=None, gt=0),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
):
    """KPIs, hourly trends and equipment health for selected filters."""

    return run_query(
        core.build_overview,
        system_type,
        building_id,
        start_time,
        end_time,
    )


# ---------- Day 4 alert API ----------

@router.get("/alerts/scenarios")
def get_alert_scenarios():
    """Return the available baseline and simulated fault scenarios."""

    return {
        "scenarios": [
            {
                "id": scenario_id,
                "name": details["name"],
                "description": details["description"],
            }
            for scenario_id, details in SCENARIOS.items()
        ]
    }


@router.get("/alerts")
def get_alerts(
    scenario: str = Query(default="baseline"),
):
    """Run the existing detection engine on one approved database."""

    selected, database = get_scenario(scenario)

    try:
        incidents = detect(database)

    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to analyze the selected scenario.",
        ) from exc

    results = []

    for index, incident in enumerate(incidents):
        results.append({
            "incident_index": index,
            "asset_code": incident["asset_code"],
            "metric": incident["metric"],
            "severity": incident["severity"],
            "status": incident["status"],
            "start_ts": incident["start_ts"],
            "detected_ts": incident["detected_ts"],
            "last_abnormal_ts": incident["last_abnormal_ts"],
            "resolved_ts": incident.get("resolved_ts"),
            "peak_value": incident["peak_value"],
            "readings_count": len(incident["points"]),
            "detection_reasons": sorted({
                reason
                for point in incident["points"]
                for reason in point["reasons"]
            }),
        })

    return {
        "scenario": scenario,
        "scenario_name": selected["name"],
        "incident_count": len(results),
        "incidents": results,
    }


@router.get("/alerts/{incident_index}")
def get_alert_detail(
    incident_index: int,
    scenario: str = Query(default="baseline"),
):
    """Return evidence and an explanation for one detected incident."""

    if incident_index < 0:
        raise HTTPException(
            status_code=400,
            detail="Incident index must be zero or greater.",
        )

    _, database = get_scenario(scenario)

    try:
        incidents = detect(database)

        if incident_index >= len(incidents):
            raise HTTPException(
                status_code=404,
                detail="Incident not found in the selected scenario.",
            )

        result = explain_incident(
            database,
            incidents[incident_index],
        )

        return {
            "scenario": scenario,
            "incident_index": incident_index,
            **result,
        }

    except HTTPException:
        raise

    except (sqlite3.Error, OSError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to build the incident explanation.",
        ) from exc


# ---------- Dashboard page ----------

@ui_router.get("/dashboard", include_in_schema=False)
def dashboard_page():
    return FileResponse(STATIC_DIR / "index.html")


def register(app: FastAPI):
    """Attach the dashboard API, page and static files to the Day 2 app."""

    app.include_router(router)
    app.include_router(ui_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")