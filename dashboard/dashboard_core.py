
"""Day 3 dashboard logic: KPIs, trends and equipment health.

Standard library only. Every number is computed with SQL against the Day 2
SQLite database, opened read-only. Nothing here writes to the database.

The FastAPI layer (dashboard.py) is a thin wrapper around these functions.
"""

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reference_data import SYSTEM_CODES

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "anzma_building.db"

TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
MAX_RANGE_DAYS = 31
HEARTBEAT_EVENT = "heartbeat"
ZONE_TEMP_METRIC = "zone_temp"
PACKET_LOSS_METRIC = "packet_loss_pct"
BANDWIDTH_METRIC = "bandwidth_mbps"

STATUS_ORDER = ["critical", "no_data", "warning", "normal"]


class DashboardError(ValueError):
    """The request is invalid (bad filter, bad period)."""


class NoDataError(DashboardError):
    """The database has no telemetry or events to build a dashboard from."""


# ============================================================
# KPI DEFINITIONS
# ============================================================

KPI_DEFINITIONS = {
    "monitored_assets": {
        "name": "Monitored assets",
        "unit": "assets",
        "source": "assets",
        "definition": (
            "Number of assets that match the system and building filters. "
            "COUNT(*) over assets joined to system_types and locations."
        ),
    },
    "healthy_assets_pct": {
        "name": "Healthy assets",
        "unit": "%",
        "source": "assets, telemetry_records, event_records",
        "definition": (
            "Assets with status Normal divided by monitored assets, times 100. "
            "Status rules: Critical = at least one critical event in the period; "
            "No data = the asset normally sends telemetry or heartbeats but sent "
            "none in the period; Warning = at least one warning event; "
            "otherwise Normal."
        ),
    },
    "alerts_raised": {
        "name": "Alerts raised",
        "unit": "alerts",
        "source": "event_records",
        "definition": (
            "Events with severity warning or critical in the period. "
            "COUNT(*) over event_records where severity IN ('warning','critical') "
            "and start <= ts < end."
        ),
    },
    "critical_alerts": {
        "name": "Critical alerts",
        "unit": "alerts",
        "source": "event_records",
        "definition": (
            "Events with severity critical in the period. "
            "COUNT(*) over event_records where severity = 'critical' "
            "and start <= ts < end."
        ),
    },
    "alert_rate_per_hour": {
        "name": "Alert rate",
        "unit": "alerts/hour",
        "source": "event_records",
        "definition": (
            "Alerts raised divided by the length of the selected period in hours."
        ),
    },
    "avg_zone_temp": {
        "name": "Average zone temperature",
        "unit": "C",
        "source": "telemetry_records, metric_types",
        "definition": (
            "AVG(value) of the zone_temp metric in the period. "
            "Only HVAC zone controllers report it; N/A for other systems."
        ),
    },
    "avg_packet_loss": {
        "name": "Average packet loss",
        "unit": "%",
        "source": "telemetry_records, metric_types",
        "definition": (
            "AVG(value) of the packet_loss_pct metric in the period. "
            "Only network switches report it; N/A for other systems."
        ),
    },
    "heartbeat_compliance": {
        "name": "Heartbeat compliance",
        "unit": "%",
        "source": "event_records, event_types",
        "definition": (
            "Heartbeat events received divided by heartbeat events expected, "
            "times 100 (capped at 100). Expected = assets that send heartbeats "
            "times the number of whole-hour instants within the intersection "
            "of the selected period and available dataset coverage. "
            "CCTV cameras and the fire panel send one heartbeat per hour."
        ),
    },
}


# ============================================================
# TIMESTAMPS
# ============================================================

def parse_utc_timestamp(value):
    """Require a real, canonical UTC timestamp with whole seconds."""

    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Timestamp must end with Z and use UTC.")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid calendar date or timestamp.") from exc

    if parsed.utcoffset() != timedelta(0):
        raise ValueError("Timestamp must use UTC.")

    if parsed.microsecond != 0:
        raise ValueError("Timestamp must have whole-second precision.")

    if parsed.strftime(TS_FORMAT) != value:
        raise ValueError("Timestamp must use YYYY-MM-DDTHH:MM:SSZ format.")

    return parsed


def format_ts(moment):
    return moment.astimezone(timezone.utc).strftime(TS_FORMAT)


# ============================================================
# DATABASE
# ============================================================

def open_readonly(db_path=DB_PATH):
    """Open the database read-only. Writes raise sqlite3.OperationalError."""

    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


SCOPE_CTE = """
WITH scope AS (
    SELECT
        a.asset_id,
        a.asset_code,
        a.name,
        a.asset_type,
        st.code AS system_type,
        l.name  AS location_name,
        l.floor AS floor
    FROM assets AS a
    JOIN system_types AS st ON st.system_type_id = a.system_type_id
    JOIN locations    AS l  ON l.location_id     = a.location_id
    WHERE (:system   IS NULL OR st.code        = :system)
      AND (:building IS NULL OR l.building_id  = :building)
)
"""


# ============================================================
# FILTERS AND PERIOD
# ============================================================

def get_filter_options(conn):
    """Filter choices and the time extent of the data, all read from the database."""

    systems = [
        {"code": row["code"], "assets": row["assets"]}
        for row in conn.execute(
            """
            SELECT st.code AS code, COUNT(a.asset_id) AS assets
            FROM system_types AS st
            LEFT JOIN assets AS a ON a.system_type_id = st.system_type_id
            GROUP BY st.system_type_id
            ORDER BY st.system_type_id
            """
        )
    ]

    buildings = [
        {"building_id": row["building_id"], "name": row["name"]}
        for row in conn.execute(
            "SELECT building_id, name FROM buildings ORDER BY building_id"
        )
    ]

    first, last = _data_extent(conn)

    return {
        "systems": systems,
        "buildings": buildings,
        "data_start": format_ts(first),
        "data_end_exclusive": format_ts(last + timedelta(seconds=1)),
    }


def _data_extent(conn):
    """Return the first and last timestamps present in telemetry or events."""

    row = conn.execute(
        """
        SELECT MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM (
            SELECT ts FROM telemetry_records
            UNION ALL
            SELECT ts FROM event_records
        )
        """
    ).fetchone()

    if row["first_ts"] is None:
        raise NoDataError("The database has no telemetry or events.")

    return (
        parse_utc_timestamp(row["first_ts"]),
        parse_utc_timestamp(row["last_ts"]),
    )


def resolve_filters(conn, system_type, building_id, start_time, end_time):
    """Validate filters. Defaults and coverage boundaries come from the data."""

    if system_type is not None and system_type not in SYSTEM_CODES:
        raise DashboardError(
            f"Unknown system_type. Allowed values: {', '.join(SYSTEM_CODES)}."
        )

    if building_id is not None:
        exists = conn.execute(
            "SELECT 1 FROM buildings WHERE building_id = ?", (building_id,)
        ).fetchone()

        if exists is None:
            raise DashboardError("Unknown building_id.")

    first, last = _data_extent(conn)

    try:
        start = parse_utc_timestamp(start_time) if start_time is not None else first
        end = (
            parse_utc_timestamp(end_time)
            if end_time is not None
            else last + timedelta(seconds=1)
        )
    except ValueError as exc:
        raise DashboardError(str(exc)) from exc

    if start >= end:
        raise DashboardError("start_time must be earlier than end_time.")

    if end - start > timedelta(days=MAX_RANGE_DAYS):
        raise DashboardError(
            f"The period may not be longer than {MAX_RANGE_DAYS} days."
        )

    return {
        "system": system_type,
        "building": building_id,
        "start": start,
        "end": end,
        "data_start": first,
        "data_end_exclusive": last + timedelta(seconds=1),
    }


def _params(f):
    return {
        "system": f["system"],
        "building": f["building"],
        "start": format_ts(f["start"]),
        "end": format_ts(f["end"]),
    }


def hourly_slots(start, end):
    """Number of top-of-the-hour instants t with start <= t < end."""

    first = math.ceil(start.timestamp() / 3600)
    after_last = math.ceil(end.timestamp() / 3600)
    return max(0, after_last - first)


# ============================================================
# EQUIPMENT HEALTH
# ============================================================

HEALTH_SQL = SCOPE_CTE + """
SELECT
    s.asset_id, s.asset_code, s.name, s.asset_type,
    s.system_type, s.location_name, s.floor,

    (SELECT COUNT(*) FROM telemetry_records t
      WHERE t.asset_id = s.asset_id) AS telemetry_total,

    (SELECT COUNT(*) FROM telemetry_records t
      WHERE t.asset_id = s.asset_id
        AND t.ts >= :start AND t.ts < :end) AS telemetry_in_period,

    (SELECT COUNT(*) FROM event_records e
       JOIN event_types et ON et.event_type_id = e.event_type_id
      WHERE e.asset_id = s.asset_id
        AND et.name = :heartbeat) AS heartbeat_total,

    (SELECT COUNT(*) FROM event_records e
       JOIN event_types et ON et.event_type_id = e.event_type_id
      WHERE e.asset_id = s.asset_id
        AND et.name = :heartbeat
        AND e.ts >= :start AND e.ts < :end) AS heartbeat_in_period,

    (SELECT COUNT(*) FROM event_records e
      WHERE e.asset_id = s.asset_id AND e.severity = 'warning'
        AND e.ts >= :start AND e.ts < :end) AS warnings,

    (SELECT COUNT(*) FROM event_records e
      WHERE e.asset_id = s.asset_id AND e.severity = 'critical'
        AND e.ts >= :start AND e.ts < :end) AS criticals,

    (SELECT MAX(ts) FROM (
        SELECT t.ts AS ts FROM telemetry_records t
         WHERE t.asset_id = s.asset_id AND t.ts >= :start AND t.ts < :end
        UNION ALL
        SELECT e.ts AS ts FROM event_records e
         WHERE e.asset_id = s.asset_id AND e.ts >= :start AND e.ts < :end
    )) AS last_seen

FROM scope AS s
ORDER BY s.asset_id
"""


def classify_asset(row):
    """Derive the liveness source and status of one asset."""

    if row["telemetry_total"] > 0:
        liveness, signals = "telemetry", row["telemetry_in_period"]
    elif row["heartbeat_total"] > 0:
        liveness, signals = "heartbeat", row["heartbeat_in_period"]
    else:
        liveness, signals = "none", None

    if row["criticals"] > 0:
        status = "critical"
        reason = f"{row['criticals']} critical event(s) in the period"
    elif signals is not None and signals == 0:
        status = "no_data"
        reason = f"No {liveness} received in the period"
    elif row["warnings"] > 0:
        status = "warning"
        reason = f"{row['warnings']} warning event(s) in the period"
    else:
        status = "normal"
        reason = "No warning or critical events in the period"

    if liveness == "none" and status == "normal":
        reason += " (no liveness signal exists for this asset type)"

    return liveness, status, reason


def compute_health(conn, f):
    params = _params(f)
    params["heartbeat"] = HEARTBEAT_EVENT

    assets = []

    for row in conn.execute(HEALTH_SQL, params):
        liveness, status, reason = classify_asset(row)

        assets.append({
            "asset_id": row["asset_id"],
            "asset_code": row["asset_code"],
            "name": row["name"],
            "asset_type": row["asset_type"],
            "system_type": row["system_type"],
            "location_name": row["location_name"],
            "floor": row["floor"],
            "liveness": liveness,
            "status": status,
            "status_reason": reason,
            "warnings": row["warnings"],
            "criticals": row["criticals"],
            "telemetry_in_period": row["telemetry_in_period"],
            "heartbeat_in_period": row["heartbeat_in_period"],
            "heartbeat_total": row["heartbeat_total"],
            "last_seen": row["last_seen"],
        })

    return assets


def summarize_health(assets):
    """Counts by system and overall, derived from per-asset statuses."""

    def blank():
        return {
            "assets": 0,
            "critical": 0,
            "no_data": 0,
            "warning": 0,
            "normal": 0,
        }

    by_system = {}
    overall = blank()

    for asset in assets:
        for bucket in (
            by_system.setdefault(asset["system_type"], blank()),
            overall,
        ):
            bucket["assets"] += 1
            bucket[asset["status"]] += 1

    def finish(code, bucket):
        pct = round(bucket["normal"] * 100 / bucket["assets"], 1)
        return {"system_type": code, **bucket, "healthy_pct": pct}

    systems = [
        finish(code, by_system[code])
        for code in SYSTEM_CODES
        if code in by_system
    ]

    return {
        "by_system": systems,
        "overall": finish("ALL", overall) if overall["assets"] else None,
    }


# ============================================================
# KPIs
# ============================================================

def _kpi(key, value, applicable=True, detail=""):
    meta = KPI_DEFINITIONS[key]

    return {
        "key": key,
        "name": meta["name"],
        "unit": meta["unit"],
        "value": value,
        "applicable": applicable,
        "detail": detail,
        "definition": meta["definition"],
        "source": meta["source"],
    }


def _alert_counts(conn, f):
    row = conn.execute(
        SCOPE_CTE + """
        SELECT
            COALESCE(SUM(e.severity = 'warning'),  0) AS warnings,
            COALESCE(SUM(e.severity = 'critical'), 0) AS criticals
        FROM event_records AS e
        JOIN scope AS s ON s.asset_id = e.asset_id
        WHERE e.ts >= :start AND e.ts < :end
        """,
        _params(f),
    ).fetchone()

    return row["warnings"], row["criticals"]


def _metric_average(conn, f, metric):
    """Return (applicable, average, samples) for one metric over the scope."""

    params = _params(f)
    params["metric"] = metric

    applicable = conn.execute(
        SCOPE_CTE + """
        SELECT COUNT(*) AS n
        FROM telemetry_records AS t
        JOIN scope AS s ON s.asset_id = t.asset_id
        JOIN metric_types AS mt ON mt.metric_id = t.metric_id
        WHERE mt.name = :metric
        """,
        params,
    ).fetchone()["n"] > 0

    row = conn.execute(
        SCOPE_CTE + """
        SELECT COUNT(*) AS n, AVG(t.value) AS avg_value
        FROM telemetry_records AS t
        JOIN scope AS s ON s.asset_id = t.asset_id
        JOIN metric_types AS mt ON mt.metric_id = t.metric_id
        WHERE mt.name = :metric
          AND t.ts >= :start AND t.ts < :end
        """,
        params,
    ).fetchone()

    average = (
        round(row["avg_value"], 2)
        if row["avg_value"] is not None
        else None
    )

    return applicable, average, row["n"]


def compute_kpis(conn, f, assets):
    kpis = []
    total = len(assets)

    # 1. Monitored assets
    kpis.append(_kpi("monitored_assets", total))

    # 2. Healthy assets %
    normal = sum(1 for a in assets if a["status"] == "normal")

    kpis.append(_kpi(
        "healthy_assets_pct",
        round(normal * 100 / total, 1) if total else None,
        applicable=total > 0,
        detail=f"{normal} of {total} assets Normal",
    ))

    # 3-5. Alerts
    warnings, criticals = _alert_counts(conn, f)
    alerts = warnings + criticals
    hours = (f["end"] - f["start"]).total_seconds() / 3600

    kpis.append(_kpi(
        "alerts_raised",
        alerts,
        detail=f"{warnings} warning, {criticals} critical",
    ))

    kpis.append(_kpi("critical_alerts", criticals))

    kpis.append(_kpi(
        "alert_rate_per_hour",
        round(alerts / hours, 2),
        detail=f"{alerts} alerts over {hours:.2f} h",
    ))

    # 6-7. Telemetry averages
    for key, metric in (
        ("avg_zone_temp", ZONE_TEMP_METRIC),
        ("avg_packet_loss", PACKET_LOSS_METRIC),
    ):
        applicable, average, samples = _metric_average(conn, f, metric)

        if not applicable:
            detail = "Not applicable to the selected system"
        elif samples == 0:
            detail = "No readings in the period"
        else:
            detail = f"{samples} readings"

        kpis.append(_kpi(
            key,
            average,
            applicable=applicable,
            detail=detail,
        ))

    # 8. Heartbeat compliance
    hb_assets = [
        a for a in assets
        if a["heartbeat_total"] > 0
        and a["liveness"] == "heartbeat"
    ]

    # Only expect heartbeats during the part of the selected period
    # for which the dataset actually contains records.
    effective_start = max(f["start"], f["data_start"])
    effective_end = min(f["end"], f["data_end_exclusive"])

    slots = hourly_slots(effective_start, effective_end)
    expected = len(hb_assets) * slots
    received = sum(a["heartbeat_in_period"] for a in hb_assets)

    if not hb_assets:
        kpis.append(_kpi(
            "heartbeat_compliance",
            None,
            applicable=False,
            detail="Not applicable to the selected system",
        ))
    elif expected == 0:
        kpis.append(_kpi(
            "heartbeat_compliance",
            None,
            detail="No complete hourly slots within available data coverage",
        ))
    else:
        kpis.append(_kpi(
            "heartbeat_compliance",
            round(min(received, expected) * 100 / expected, 1),
            detail=f"{received} received, {expected} expected",
        ))

    return kpis


# ============================================================
# TRENDS (hourly)
# ============================================================

HOUR_FORMAT = "%Y-%m-%dT%H:00:00Z"


def _hour_buckets(start, end):
    bucket = start.replace(minute=0, second=0, microsecond=0)
    labels = []

    while bucket < end:
        labels.append(bucket.strftime(HOUR_FORMAT))
        bucket += timedelta(hours=1)

    return labels


def _hourly_metric(conn, f, metric, labels):
    params = _params(f)
    params["metric"] = metric

    found = {
        row["hour"]: round(row["avg_value"], 2)
        for row in conn.execute(
            SCOPE_CTE + """
            SELECT strftime('%Y-%m-%dT%H:00:00Z', t.ts) AS hour,
                   AVG(t.value) AS avg_value
            FROM telemetry_records AS t
            JOIN scope AS s ON s.asset_id = t.asset_id
            JOIN metric_types AS mt ON mt.metric_id = t.metric_id
            WHERE mt.name = :metric AND t.ts >= :start AND t.ts < :end
            GROUP BY hour
            """,
            params,
        )
    }

    return [found.get(label) for label in labels]


def compute_trends(conn, f):
    labels = _hour_buckets(f["start"], f["end"])

    alerts = {
        row["hour"]: (row["warnings"], row["criticals"])
        for row in conn.execute(
            SCOPE_CTE + """
            SELECT strftime('%Y-%m-%dT%H:00:00Z', e.ts) AS hour,
                   SUM(e.severity = 'warning')  AS warnings,
                   SUM(e.severity = 'critical') AS criticals
            FROM event_records AS e
            JOIN scope AS s ON s.asset_id = e.asset_id
            WHERE e.ts >= :start AND e.ts < :end
            GROUP BY hour
            """,
            _params(f),
        )
    }

    zone_applicable, _, _ = _metric_average(conn, f, ZONE_TEMP_METRIC)
    bw_applicable, _, _ = _metric_average(conn, f, BANDWIDTH_METRIC)

    return {
        "hours": labels,
        "warnings": [alerts.get(h, (0, 0))[0] for h in labels],
        "criticals": [alerts.get(h, (0, 0))[1] for h in labels],
        "zone_temp": {
            "applicable": zone_applicable,
            "unit": "C",
            "values": _hourly_metric(conn, f, ZONE_TEMP_METRIC, labels),
        },
        "bandwidth": {
            "applicable": bw_applicable,
            "unit": "Mbps",
            "values": _hourly_metric(conn, f, BANDWIDTH_METRIC, labels),
        },
    }


# ============================================================
# OVERVIEW
# ============================================================

def build_overview(
    conn,
    system_type=None,
    building_id=None,
    start_time=None,
    end_time=None,
):
    f = resolve_filters(
        conn,
        system_type,
        building_id,
        start_time,
        end_time,
    )

    assets = compute_health(conn, f)

    counts = conn.execute(
        SCOPE_CTE + """
        SELECT
          (SELECT COUNT(*) FROM telemetry_records t
             JOIN scope s ON s.asset_id = t.asset_id
            WHERE t.ts >= :start AND t.ts < :end) AS telemetry,
          (SELECT COUNT(*) FROM event_records e
             JOIN scope s ON s.asset_id = e.asset_id
            WHERE e.ts >= :start AND e.ts < :end) AS events
        """,
        _params(f),
    ).fetchone()

    return {
        "filters": {
            "system_type": f["system"],
            "building_id": f["building"],
        },
        "period": {
            "start": format_ts(f["start"]),
            "end_exclusive": format_ts(f["end"]),
            "hours": round(
                (f["end"] - f["start"]).total_seconds() / 3600,
                2,
            ),
            "telemetry_records": counts["telemetry"],
            "event_records": counts["events"],
        },
        "kpis": compute_kpis(conn, f, assets),
        "health": summarize_health(assets),
        "trends": compute_trends(conn, f),
        "assets": assets,
    }
