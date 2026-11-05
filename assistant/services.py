"""Read-only helper services for the Day 5 conversational assistant.

These are thin wrappers around the existing Task 2-4 logic. They never write
to the database and never accept an arbitrary database path: scenarios are
resolved through the existing SCENARIOS allowlist.
"""

from datetime import timedelta

from fastapi import HTTPException

from dashboard import dashboard_core as core
from dashboard.dashboard import get_scenario

ALLOWED_HOURS = (1, 6, 12, 24)
DEFAULT_HOURS = 24


class AssistantError(Exception):
    """A request the assistant must reject or report clearly."""

    def __init__(self, message, status_code=422, code="invalid_request"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def resolve_scenario(scenario):
    """Validate a scenario key through the existing allowlist.

    Returns (scenario_key, db_path, label). get_scenario returns the scenario
    dict (name, description, path), so the key is kept from the request.
    Unknown names and missing databases use the dashboard's codes (400 / 503).
    """

    try:
        selected, db_path = get_scenario(scenario)
    except HTTPException as exc:
        raise AssistantError(
            str(exc.detail), exc.status_code, "invalid_scenario"
        ) from exc
    label = selected.get("name", scenario) if isinstance(selected, dict) else str(selected)
    return scenario, db_path, label


def resolve_time_range(scenario="baseline", hours=DEFAULT_HOURS):
    """Return the data window for 'last N hours', anchored to the dataset end.

    The window is anchored to the newest record in the selected database, not
    to the wall clock, because the data is synthetic and ends on 2026-11-02.
    """

    if isinstance(hours, bool) or not isinstance(hours, int):
        raise AssistantError(
            f"hours must be an integer from {list(ALLOWED_HOURS)}.",
            422,
            "invalid_time_range",
        )
    if hours not in ALLOWED_HOURS:
        raise AssistantError(
            f"hours must be one of {list(ALLOWED_HOURS)}; got {hours}.",
            422,
            "invalid_time_range",
        )

    key, db_path, label = resolve_scenario(scenario)

    conn = core.open_readonly(db_path)
    try:
        try:
            first_ts, last_ts = core._data_extent(conn)
        except core.NoDataError as exc:
            raise AssistantError(str(exc), 404, "no_data") from exc
    finally:
        conn.close()

    end_exclusive = last_ts + timedelta(seconds=1)
    start = end_exclusive - timedelta(hours=hours)

    return {
        "scenario": key,
        "scenario_label": label,
        "hours": hours,
        "start": core.format_ts(start),
        "end_exclusive": core.format_ts(end_exclusive),
        "anchored_to": "dataset end",
        "data_start": core.format_ts(first_ts),
        "data_end": core.format_ts(last_ts),
        "coverage": "complete" if start >= first_ts else "partial",
    }