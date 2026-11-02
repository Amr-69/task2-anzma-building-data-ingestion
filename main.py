
import math
import sqlite3
from datetime import datetime, timedelta
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from db import DB_PATH, get_connection
from reference_data import SYSTEM_CODES, METRICS_BY_ASSET_TYPE


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="Commercial Building Data API",
    description=(
        "REST API for ingesting and retrieving synthetic "
        "commercial building telemetry and events."
    ),
    version="1.0.0",
)


# ============================================================
# COMMON VALIDATION
# ============================================================

def parse_utc_timestamp(value: str) -> datetime:
    """Require a real, canonical UTC timestamp with whole seconds."""

    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(
            "Timestamp must end with Z and use UTC."
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            "Invalid calendar date or timestamp."
        ) from exc

    if parsed.utcoffset() != timedelta(0):
        raise ValueError("Timestamp must use UTC.")

    if parsed.microsecond != 0:
        raise ValueError(
            "Timestamp must have whole-second precision."
        )

    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError(
            "Timestamp must use YYYY-MM-DDTHH:MM:SSZ format."
        )

    return parsed


def open_database():
    """Open a new connection without silently creating a missing database."""

    if not DB_PATH.is_file():
        raise HTTPException(
            status_code=503,
            detail="Database file does not exist. Initialize the database first.",
        )

    try:
        return get_connection()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to connect to the database.",
        ) from exc


def validate_retrieval_filters(
    system_type,
    start_time,
    end_time,
):
    """Validate system codes and timestamp boundaries."""

    if system_type is not None and system_type not in SYSTEM_CODES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unknown system_type.",
                "allowed_values": SYSTEM_CODES,
            },
        )

    parsed_start = None
    parsed_end = None

    try:
        if start_time is not None:
            parsed_start = parse_utc_timestamp(start_time)

        if end_time is not None:
            parsed_end = parse_utc_timestamp(end_time)

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    if (
        parsed_start is not None
        and parsed_end is not None
        and parsed_start >= parsed_end
    ):
        raise HTTPException(
            status_code=422,
            detail="start_time must be earlier than end_time.",
        )


# ============================================================
# PYDANTIC REQUEST MODELS
# ============================================================

class TelemetryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_code: str = Field(
        min_length=1,
        max_length=100,
        description="Unique asset code from the reference data.",
    )

    metric_name: str = Field(
        min_length=1,
        max_length=100,
        description="Existing metric type name.",
    )

    ts: str = Field(
        description="UTC timestamp in YYYY-MM-DDTHH:MM:SSZ format.",
    )

    value: float = Field(
        allow_inf_nan=False,
        description="Finite numeric measurement.",
    )

    @field_validator("ts")
    @classmethod
    def validate_timestamp(cls, value):
        parse_utc_timestamp(value)
        return value

    @field_validator("value", mode="before")
    @classmethod
    def validate_numeric_value(cls, value):

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            raise ValueError(
                "Measurement must be a numeric value."
            )

        if not math.isfinite(value):
            raise ValueError(
                "Measurement must be finite."
            )

        return float(value)


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_code: str = Field(
        min_length=1,
        max_length=100,
        description="Unique asset code from the reference data.",
    )

    event_type: str = Field(
        min_length=1,
        max_length=100,
        description="Existing event type name.",
    )

    ts: str = Field(
        description="UTC timestamp in YYYY-MM-DDTHH:MM:SSZ format.",
    )

    severity: Literal["info", "warning", "critical"]

    details: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator("ts")
    @classmethod
    def validate_timestamp(cls, value):
        parse_utc_timestamp(value)
        return value


class TelemetryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[TelemetryRecord] = Field(
        min_length=1,
        description="Non-empty batch of telemetry records.",
    )


class EventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[EventRecord] = Field(
        min_length=1,
        description="Non-empty batch of event records.",
    )


# ============================================================
# PAGINATION
# ============================================================

def fetch_page(
    sql,
    params,
    limit,
    offset,
):
    """Execute a paginated SELECT and return a consistent response."""

    conn = open_database()

    try:
        rows = conn.execute(
            sql,
            [*params, limit + 1, offset],
        ).fetchall()

        has_more = len(rows) > limit
        items = [dict(row) for row in rows[:limit]]

        return {
            "returned": len(items),
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "next_offset": (
                offset + len(items) if has_more else None
            ),
            "items": items,
        }

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Database retrieval failed.",
        ) from exc

    finally:
        conn.close()


# ============================================================
# TELEMETRY INGESTION
# ============================================================

@app.post(
    "/api/v1/telemetry/batch",
    status_code=201,
    tags=["Ingestion"],
)
def ingest_telemetry(batch: TelemetryBatch):
    """
    Atomically ingest a batch of telemetry records.

    All records must be valid. One invalid or duplicate record
    causes the entire batch to be rolled back.
    """

    conn = open_database()

    try:
        conn.execute("BEGIN IMMEDIATE")

        # Load identifier mappings once per batch.
        asset_rows = conn.execute(
            """
            SELECT asset_id, asset_code, asset_type
            FROM assets
            """
        ).fetchall()

        metric_rows = conn.execute(
            """
            SELECT metric_id, name
            FROM metric_types
            """
        ).fetchall()

        asset_map = {
            row["asset_code"]: (
                row["asset_id"],
                row["asset_type"],
            )
            for row in asset_rows
        }

        metric_map = {
            row["name"]: row["metric_id"]
            for row in metric_rows
        }

        prepared_records = []
        errors = []

        # Resolve stable identifiers into actual SQLite IDs.
        for index, record in enumerate(batch.records):

            asset = asset_map.get(record.asset_code)

            metric_id = metric_map.get(record.metric_name)

            if asset is None:
                errors.append({
                    "index": index,
                    "field": "asset_code",
                    "value": record.asset_code,
                    "message": "Unknown asset.",
                })
                continue

            if metric_id is None:
                errors.append({
                    "index": index,
                    "field": "metric_name",
                    "value": record.metric_name,
                    "message": "Unknown metric type.",
                })
                continue

            asset_id, asset_type = asset

            allowed_metrics = METRICS_BY_ASSET_TYPE.get(
                asset_type,
                [],
            )

            if record.metric_name not in allowed_metrics:
                errors.append({
                    "index": index,
                    "field": "metric_name",
                    "value": record.metric_name,
                    "message": (
                        "This asset type is not assigned "
                        "the submitted metric."
                    ),
                })
                continue

            prepared_records.append((
                asset_id,
                metric_id,
                record.ts,
                record.value,
            ))

        if errors:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Batch rejected. No records were inserted.",
                    "errors": errors,
                },
            )

        # The database uniqueness constraint detects duplicates.
        conn.executemany(
            """
            INSERT INTO telemetry_records
                (asset_id, metric_id, ts, value)
            VALUES (?, ?, ?, ?)
            """,
            prepared_records,
        )

        conn.commit()

        return {
            "status": "accepted",
            "inserted": len(prepared_records),
            "rejected": 0,
            "transaction": "committed",
        }

    except HTTPException:
        conn.rollback()
        raise

    except sqlite3.IntegrityError as exc:
        conn.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "Batch rejected. One or more records conflict with "
                "database integrity constraints, such as duplicate records. "
                "The entire batch was rolled back."
            ),
        ) from exc

    except sqlite3.Error as exc:
        conn.rollback()

        raise HTTPException(
            status_code=500,
            detail="Telemetry ingestion failed. Transaction rolled back.",
        ) from exc

    finally:
        conn.close()


# ============================================================
# EVENT INGESTION
# ============================================================

@app.post(
    "/api/v1/events/batch",
    status_code=201,
    tags=["Ingestion"],
)
def ingest_events(batch: EventBatch):
    """
    Atomically ingest a batch of discrete events.

    All records must be valid. One invalid or duplicate record
    causes the entire batch to be rolled back.
    """

    conn = open_database()

    try:
        conn.execute("BEGIN IMMEDIATE")

        # Resolve asset codes and event names once per batch.
        asset_rows = conn.execute(
            """
            SELECT asset_id, asset_code
            FROM assets
            """
        ).fetchall()

        event_rows = conn.execute(
            """
            SELECT event_type_id, name
            FROM event_types
            """
        ).fetchall()

        asset_map = {
            row["asset_code"]: row["asset_id"]
            for row in asset_rows
        }

        event_map = {
            row["name"]: row["event_type_id"]
            for row in event_rows
        }

        prepared_records = []
        errors = []

        for index, record in enumerate(batch.records):

            asset_id = asset_map.get(record.asset_code)

            event_type_id = event_map.get(record.event_type)

            if asset_id is None:
                errors.append({
                    "index": index,
                    "field": "asset_code",
                    "value": record.asset_code,
                    "message": "Unknown asset.",
                })
                continue

            if event_type_id is None:
                errors.append({
                    "index": index,
                    "field": "event_type",
                    "value": record.event_type,
                    "message": "Unknown event type.",
                })
                continue

            prepared_records.append((
                asset_id,
                event_type_id,
                record.ts,
                record.severity,
                record.details,
            ))

        if errors:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Batch rejected. No records were inserted.",
                    "errors": errors,
                },
            )

        conn.executemany(
            """
            INSERT INTO event_records
                (asset_id, event_type_id, ts, severity, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            prepared_records,
        )

        conn.commit()

        return {
            "status": "accepted",
            "inserted": len(prepared_records),
            "rejected": 0,
            "transaction": "committed",
        }

    except HTTPException:
        conn.rollback()
        raise

    except sqlite3.IntegrityError as exc:
        conn.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "Batch rejected. One or more records conflict with "
                "database integrity constraints, such as duplicate events. "
                "The entire batch was rolled back."
            ),
        ) from exc

    except sqlite3.Error as exc:
        conn.rollback()

        raise HTTPException(
            status_code=500,
            detail="Event ingestion failed. Transaction rolled back.",
        ) from exc

    finally:
        conn.close()


# ============================================================
# TELEMETRY RETRIEVAL
# ============================================================

@app.get(
    "/api/v1/telemetry",
    tags=["Retrieval"],
)
def get_telemetry(
    asset_id: int | None = Query(default=None, gt=0),
    location_id: int | None = Query(default=None, gt=0),
    system_type: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """
    Retrieve telemetry by asset, location, system type and time.

    start_time is inclusive.
    end_time is exclusive.

    All filters are optional and can be combined.
    """

    validate_retrieval_filters(
        system_type,
        start_time,
        end_time,
    )

    conditions = []
    params = []

    if asset_id is not None:
        conditions.append("tr.asset_id = ?")
        params.append(asset_id)

    if location_id is not None:
        conditions.append("a.location_id = ?")
        params.append(location_id)

    if system_type is not None:
        conditions.append("st.code = ?")
        params.append(system_type)

    if start_time is not None:
        conditions.append("tr.ts >= ?")
        params.append(start_time)

    if end_time is not None:
        conditions.append("tr.ts < ?")
        params.append(end_time)

    where_clause = (
        "WHERE " + " AND ".join(conditions)
        if conditions else ""
    )

    sql = f"""
        SELECT
            tr.telemetry_id,
            tr.asset_id,
            a.asset_code,
            a.name AS asset_name,
            tr.metric_id,
            mt.name AS metric_name,
            mt.unit,
            tr.ts,
            tr.value,
            a.location_id,
            l.name AS location_name,
            st.code AS system_type

        FROM telemetry_records AS tr

        JOIN assets AS a
            ON tr.asset_id = a.asset_id

        JOIN locations AS l
            ON a.location_id = l.location_id

        JOIN system_types AS st
            ON a.system_type_id = st.system_type_id

        JOIN metric_types AS mt
            ON tr.metric_id = mt.metric_id

        {where_clause}

        ORDER BY tr.ts ASC, tr.telemetry_id ASC

        LIMIT ? OFFSET ?
    """

    return fetch_page(
        sql,
        params,
        limit,
        offset,
    )


# ============================================================
# EVENT RETRIEVAL
# ============================================================

@app.get(
    "/api/v1/events",
    tags=["Retrieval"],
)
def get_events(
    asset_id: int | None = Query(default=None, gt=0),
    location_id: int | None = Query(default=None, gt=0),
    system_type: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """
    Retrieve events by asset, location, system type and time.

    start_time is inclusive.
    end_time is exclusive.

    All filters are optional and can be combined.
    """

    validate_retrieval_filters(
        system_type,
        start_time,
        end_time,
    )

    conditions = []
    params = []

    if asset_id is not None:
        conditions.append("er.asset_id = ?")
        params.append(asset_id)

    if location_id is not None:
        conditions.append("a.location_id = ?")
        params.append(location_id)

    if system_type is not None:
        conditions.append("st.code = ?")
        params.append(system_type)

    if start_time is not None:
        conditions.append("er.ts >= ?")
        params.append(start_time)

    if end_time is not None:
        conditions.append("er.ts < ?")
        params.append(end_time)

    where_clause = (
        "WHERE " + " AND ".join(conditions)
        if conditions else ""
    )

    sql = f"""
        SELECT
            er.event_id,
            er.asset_id,
            a.asset_code,
            a.name AS asset_name,
            er.event_type_id,
            et.name AS event_type,
            er.ts,
            er.severity,
            er.details,
            a.location_id,
            l.name AS location_name,
            st.code AS system_type

        FROM event_records AS er

        JOIN assets AS a
            ON er.asset_id = a.asset_id

        JOIN locations AS l
            ON a.location_id = l.location_id

        JOIN system_types AS st
            ON a.system_type_id = st.system_type_id

        JOIN event_types AS et
            ON er.event_type_id = et.event_type_id

        {where_clause}

        ORDER BY er.ts ASC, er.event_id ASC

        LIMIT ? OFFSET ?
    """

    return fetch_page(
        sql,
        params,
        limit,
        offset,
    )
