
"""Day 3 dashboard: thin FastAPI layer over dashboard_core.

Routes:
    GET /dashboard                        the dashboard page
    GET /api/v1/dashboard/filters         filter choices and data time extent
    GET /api/v1/dashboard/overview        KPIs, trends, health for the filters

The database is opened read-only, so the dashboard cannot change Day 2 data.
"""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import dashboard_core as core

STATIC_DIR = Path(__file__).resolve().parent / "static"

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])
ui_router = APIRouter()


def open_database():
    """Open a read-only connection without creating a missing database."""

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
    """Run one dashboard query and translate errors into HTTP responses."""

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


@router.get("/filters")
def get_filters():
    """Systems, buildings and the time extent of the stored data."""

    return run_query(core.get_filter_options)


@router.get("/overview")
def get_overview(
    system_type: str | None = Query(default=None),
    building_id: int | None = Query(default=None, gt=0),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
):
    """
    KPIs, hourly trends and equipment health for the selected filters.

    start_time is inclusive and end_time is exclusive (UTC, whole seconds).
    When omitted they default to the full time extent of the stored data.
    All filters are optional and can be combined.
    """

    return run_query(
        core.build_overview,
        system_type,
        building_id,
        start_time,
        end_time,
    )


@ui_router.get("/dashboard", include_in_schema=False)
def dashboard_page():
    return FileResponse(STATIC_DIR / "index.html")


def register(app: FastAPI):
    """Attach the dashboard API, page and static files to the Day 2 app."""

    app.include_router(router)
    app.include_router(ui_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
