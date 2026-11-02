
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from random import Random

from reference_data import (
    ASSETS,
    DATASET_START,
    DATASET_END_EXCLUSIVE,
    WINDOW_HOURS,
    SAMPLE_INTERVAL_SECONDS,
    SEED,
    SYSTEM_CODES,
    METRICS_BY_ASSET_TYPE,
    METRIC_TYPES,
    EVENT_TYPES,
    validate,
)


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "data" / "generated"

EVENT_ONLY_ASSET_TYPES = {
    "card_reader",
    "barrier_reader",
    "camera",
    "fire_panel",
    "smoke_detector",
}

KNOWN_ASSET_TYPES = (
    set(METRICS_BY_ASSET_TYPE)
    | EVENT_ONLY_ASSET_TYPES
)

# Metric name: (minimum, maximum, maximum step per sample)
METRIC_RANGES = {
    "supply_air_temp": (13.0, 18.0, 0.35),
    "fan_speed_pct": (25.0, 90.0, 4.0),
    "zone_temp": (20.0, 26.0, 0.25),
    "zone_humidity_pct": (35.0, 60.0, 0.8),
    "bandwidth_mbps": (10.0, 850.0, 45.0),
    "packet_loss_pct": (0.0, 2.0, 0.15),
    "cpu_load_pct": (10.0, 85.0, 3.0),
}

# All 15 approved event types must have a valid severity.
SEVERITY_BY_EVENT = {
    "heartbeat": "info",
    "access_granted": "info",
    "access_denied": "warning",
    "door_held_open": "warning",
    "forced_entry": "critical",
    "filter_alarm": "warning",
    "high_temperature": "critical",
    "link_down": "warning",
    "link_up": "info",
    "high_latency": "warning",
    "motion_detected": "info",
    "camera_offline": "warning",
    "camera_online": "info",
    "detector_trouble": "warning",
    "alarm_test": "info",
}

ALLOWED_SEVERITIES = {"info", "warning", "critical"}


def format_utc(value):
    """Format a timezone-aware UTC datetime with whole-second precision."""
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value, label):
    """Parse a canonical UTC timestamp and require whole-second precision."""

    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(
            f"{label} must be a UTC timestamp ending in Z."
        )

    try:
        result = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            f"Invalid {label}: {value}"
        ) from exc

    if result.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC.")

    if result.microsecond != 0:
        raise ValueError(
            f"{label} must have whole-second precision."
        )

    if format_utc(result) != value:
        raise ValueError(
            f"{label} must use canonical YYYY-MM-DDTHH:MM:SSZ format."
        )

    return result


def validate_configuration():
    """Validate reference data, metrics, event severities and time boundaries."""

    errors = validate()

    for asset_code, _name, asset_type, _system, _location in ASSETS:

        if asset_type not in KNOWN_ASSET_TYPES:
            errors.append(
                f"{asset_code}: unrecognized asset type '{asset_type}'"
            )

        for metric in METRICS_BY_ASSET_TYPE.get(asset_type, []):
            if metric not in METRIC_RANGES:
                errors.append(
                    f"{asset_code}: metric '{metric}' has no value range"
                )

    defined_metrics = {
        name for name, _unit in METRIC_TYPES
    }

    if set(METRIC_RANGES) != defined_metrics:
        errors.append(
            "Metric value ranges do not match the seven metric definitions."
        )

    if set(SEVERITY_BY_EVENT) != set(EVENT_TYPES):
        errors.append(
            "Event severity definitions do not match the approved event types."
        )

    invalid_severities = (
        set(SEVERITY_BY_EVENT.values()) - ALLOWED_SEVERITIES
    )

    if invalid_severities:
        errors.append(
            f"Invalid event severities: {sorted(invalid_severities)}"
        )

    if errors:
        raise ValueError(
            "Reference/configuration validation failed: "
            + "; ".join(errors)
        )

    start = parse_utc(
        DATASET_START,
        "DATASET_START"
    )

    end = parse_utc(
        DATASET_END_EXCLUSIVE,
        "DATASET_END_EXCLUSIVE"
    )

    if end <= start:
        raise ValueError(
            "Dataset end must be after its start."
        )

    if WINDOW_HOURS <= 0:
        raise ValueError(
            "WINDOW_HOURS must be positive."
        )

    duration = end - start

    if duration != timedelta(hours=WINDOW_HOURS):
        raise ValueError(
            "Dataset boundaries do not match WINDOW_HOURS."
        )

    if SAMPLE_INTERVAL_SECONDS <= 0:
        raise ValueError(
            "Sampling interval must be positive."
        )

    if duration.total_seconds() % SAMPLE_INTERVAL_SECONDS != 0:
        raise ValueError(
            "Dataset duration must be divisible by the sampling interval."
        )

    if duration.total_seconds() % 3600 != 0:
        raise ValueError(
            "Dataset duration must contain complete hourly buckets."
        )

    return start, end


def build_asset_lookup():
    """Build stable asset-code mappings from approved reference data."""

    return {
        asset[0]: {
            "asset_type": asset[2],
            "system_code": asset[3],
        }
        for asset in ASSETS
    }


def deduplicate(records, key_fields):
    """Remove duplicates using the agreed natural business keys."""

    seen = set()
    unique = []

    for record in records:
        key = tuple(
            record[field] for field in key_fields
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(record)

    return unique, len(records) - len(unique)


def generate_telemetry(start, end):
    """Generate reproducible, bounded telemetry time series."""

    rng = Random(SEED)

    interval = timedelta(
        seconds=SAMPLE_INTERVAL_SECONDS
    )

    sample_count = int(
        (end - start).total_seconds()
        // SAMPLE_INTERVAL_SECONDS
    )

    records = []

    for asset_code, _name, asset_type, _system, _location in ASSETS:

        metrics = METRICS_BY_ASSET_TYPE.get(
            asset_type, []
        )

        for metric_name in metrics:

            minimum, maximum, max_step = METRIC_RANGES[metric_name]

            current_value = rng.uniform(
                minimum,
                maximum
            )

            for sample_index in range(sample_count):

                if sample_index > 0:
                    change = rng.uniform(
                        -max_step,
                        max_step
                    )

                    current_value = max(
                        minimum,
                        min(
                            maximum,
                            current_value + change
                        ),
                    )

                timestamp = start + interval * sample_index

                records.append({
                    "asset_code": asset_code,
                    "metric_name": metric_name,
                    "ts": format_utc(timestamp),
                    "value": round(current_value, 2),
                })

    if start + interval * sample_count != end:
        raise RuntimeError(
            "Telemetry generation did not end at the exclusive boundary."
        )

    records.sort(
        key=lambda r: (
            r["ts"],
            r["asset_code"],
            r["metric_name"],
        )
    )

    return records, sample_count


def generate_events(start):
    """Generate operational events and approved hourly heartbeats."""

    records = []

    assets_by_code = {
        asset[0]: asset
        for asset in ASSETS
    }

    cctv_cameras = [
        asset[0]
        for asset in ASSETS
        if asset[3] == "CCTV" and asset[2] == "camera"
    ]

    fire_panels = [
        asset[0]
        for asset in ASSETS
        if asset[3] == "FIRE_ALARM"
        and asset[2] == "fire_panel"
    ]

    access_readers = [
        asset[0]
        for asset in ASSETS
        if asset[3] == "ACCESS_CONTROL"
        and asset[2] in {"card_reader", "barrier_reader"}
    ]

    if not cctv_cameras or not fire_panels or not access_readers:
        raise RuntimeError(
            "Required CCTV, fire panel, or access reader assets are missing."
        )

    def add_event(asset_code, event_type, timestamp, details):

        if asset_code not in assets_by_code:
            raise ValueError(
                f"Unknown event asset: {asset_code}"
            )

        if event_type not in EVENT_TYPES:
            raise ValueError(
                f"Unknown event type: {event_type}"
            )

        records.append({
            "asset_code": asset_code,
            "event_type": event_type,
            "ts": format_utc(timestamp),
            "severity": SEVERITY_BY_EVENT[event_type],
            "details": details,
        })

    access_event_cycle = [
        "access_granted",
        "access_denied",
        "door_held_open",
    ]

    # Every UTC hour:
    # - One Access Control event.
    # - One heartbeat per CCTV camera.
    # - One heartbeat from the fire panel.

    for hour_index in range(WINDOW_HOURS):

        hour_start = start + timedelta(
            hours=hour_index
        )

        access_asset = access_readers[
            hour_index % len(access_readers)
        ]

        access_event = access_event_cycle[
            hour_index % len(access_event_cycle)
        ]

        add_event(
            access_asset,
            access_event,
            hour_start + timedelta(minutes=5),
            "Synthetic access-control activity.",
        )

        for camera_code in cctv_cameras:

            add_event(
                camera_code,
                "heartbeat",
                hour_start,
                "Synthetic CCTV camera heartbeat.",
            )

        for panel_code in fire_panels:

            add_event(
                panel_code,
                "heartbeat",
                hour_start,
                "Synthetic fire-panel heartbeat.",
            )

    # Additional representative operational events.
    # All timestamps are inside the approved dataset window.

    scheduled_events = [
        (
            "HVAC-AHU-01",
            "filter_alarm",
            6, 10,
            "Synthetic HVAC filter maintenance alert.",
        ),
        (
            "HVAC-AHU-02",
            "high_temperature",
            17, 20,
            "Synthetic HVAC high-temperature event.",
        ),
        (
            "NET-SW-1",
            "link_down",
            8, 10,
            "Synthetic network link-down event.",
        ),
        (
            "NET-SW-1",
            "link_up",
            8, 25,
            "Synthetic network link-restored event.",
        ),
        (
            "NET-CORE-01",
            "high_latency",
            14, 40,
            "Synthetic network latency event.",
        ),
        (
            "CCTV-LOBBY",
            "motion_detected",
            3, 15,
            "Synthetic CCTV motion detection.",
        ),
        (
            "CCTV-IT",
            "camera_offline",
            10, 10,
            "Synthetic CCTV camera-offline event.",
        ),
        (
            "CCTV-IT",
            "camera_online",
            11, 10,
            "Synthetic CCTV camera-online event.",
        ),
        (
            "FA-DET-2E",
            "detector_trouble",
            12, 30,
            "Synthetic detector troubleshooting event.",
        ),
        (
            "FA-PANEL-01",
            "alarm_test",
            20, 0,
            "Synthetic scheduled fire alarm test.",
        ),
    ]

    for asset_code, event_type, hour, minute, details in scheduled_events:

        add_event(
            asset_code,
            event_type,
            start + timedelta(
                hours=hour,
                minutes=minute
            ),
            details,
        )

    records.sort(
        key=lambda r: (
            r["ts"],
            r["asset_code"],
            r["event_type"],
        )
    )

    return records


def verify_generated_data(
    telemetry,
    events,
    start,
    end,
    sample_count,
):
    """Verify records, values, timestamps, references and hourly coverage."""

    asset_lookup = build_asset_lookup()

    metric_names = {
        name for name, _unit in METRIC_TYPES
    }

    event_types = set(EVENT_TYPES)

    all_timestamps = []

    hourly_coverage = {
        system: set()
        for system in SYSTEM_CODES
    }

    system_counts = Counter()
    telemetry_series_counts = Counter()
    telemetry_timestamps = defaultdict(set)

    expected_interval = timedelta(
        seconds=SAMPLE_INTERVAL_SECONDS
    )

    expected_sample_timestamps = {
        format_utc(start + expected_interval * index)
        for index in range(sample_count)
    }

    # ---------------- TELEMETRY VERIFICATION ----------------

    telemetry_keys = set()

    for record in telemetry:

        asset_code = record["asset_code"]
        metric_name = record["metric_name"]

        if asset_code not in asset_lookup:
            raise RuntimeError(
                f"Telemetry references unknown asset: {asset_code}"
            )

        if metric_name not in metric_names:
            raise RuntimeError(
                f"Unknown telemetry metric: {metric_name}"
            )

        asset_type = asset_lookup[asset_code]["asset_type"]

        if metric_name not in METRICS_BY_ASSET_TYPE.get(asset_type, []):
            raise RuntimeError(
                f"{asset_code} is not assigned metric {metric_name}."
            )

        timestamp = parse_utc(
            record["ts"],
            "telemetry timestamp",
        )

        if not start <= timestamp < end:
            raise RuntimeError(
                f"Telemetry timestamp outside dataset window: {record['ts']}"
            )

        value = record["value"]

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise RuntimeError(
                f"Invalid numeric telemetry value: {value}"
            )

        minimum, maximum, _step = METRIC_RANGES[metric_name]

        if not minimum <= value <= maximum:
            raise RuntimeError(
                f"{metric_name} value {value} outside approved range."
            )

        key = (
            asset_code,
            metric_name,
            record["ts"],
        )

        if key in telemetry_keys:
            raise RuntimeError(
                f"Duplicate telemetry record remains: {key}"
            )

        telemetry_keys.add(key)

        series = (asset_code, metric_name)

        telemetry_series_counts[series] += 1
        telemetry_timestamps[series].add(record["ts"])

        system = asset_lookup[asset_code]["system_code"]

        hourly_coverage[system].add(
            timestamp.strftime("%Y-%m-%dT%H")
        )

        system_counts[system] += 1
        all_timestamps.append(timestamp)

    # Check all approved telemetry series exist.
    expected_series = {
        (asset[0], metric)
        for asset in ASSETS
        for metric in METRICS_BY_ASSET_TYPE.get(asset[2], [])
    }

    if set(telemetry_series_counts) != expected_series:
        raise RuntimeError(
            "Generated telemetry series do not match approved definitions."
        )

    # Every series must contain exactly 300 records.
    incorrect_series = {
        series: count
        for series, count in telemetry_series_counts.items()
        if count != sample_count
    }

    if incorrect_series:
        raise RuntimeError(
            f"Incorrect telemetry sample counts: {incorrect_series}"
        )

    # Every series must follow the exact five-minute schedule.
    for series, timestamps in telemetry_timestamps.items():

        if timestamps != expected_sample_timestamps:
            raise RuntimeError(
                f"Incorrect timestamp schedule for telemetry series {series}."
            )

    expected_telemetry = (
        len(expected_series) * sample_count
    )

    if len(telemetry) != expected_telemetry:
        raise RuntimeError(
            f"Expected {expected_telemetry} telemetry records, "
            f"found {len(telemetry)}."
        )

    # ---------------- EVENT VERIFICATION ----------------

    event_keys = set()

    for record in events:

        asset_code = record["asset_code"]
        event_type = record["event_type"]

        if asset_code not in asset_lookup:
            raise RuntimeError(
                f"Event references unknown asset: {asset_code}"
            )

        if event_type not in event_types:
            raise RuntimeError(
                f"Event references unknown type: {event_type}"
            )

        timestamp = parse_utc(
            record["ts"],
            "event timestamp",
        )

        if not start <= timestamp < end:
            raise RuntimeError(
                f"Event timestamp outside dataset window: {record['ts']}"
            )

        if record["severity"] != SEVERITY_BY_EVENT[event_type]:
            raise RuntimeError(
                f"Incorrect severity for event {event_type}."
            )

        if record["severity"] not in ALLOWED_SEVERITIES:
            raise RuntimeError(
                f"Invalid event severity: {record['severity']}"
            )

        if (
            not isinstance(record["details"], str)
            or not record["details"]
        ):
            raise RuntimeError(
                "Event details cannot be empty."
            )

        key = (
            asset_code,
            event_type,
            record["ts"],
        )

        if key in event_keys:
            raise RuntimeError(
                f"Duplicate event record remains: {key}"
            )

        event_keys.add(key)

        system = asset_lookup[asset_code]["system_code"]

        hourly_coverage[system].add(
            timestamp.strftime("%Y-%m-%dT%H")
        )

        system_counts[system] += 1
        all_timestamps.append(timestamp)

    # ---------------- HOURLY COVERAGE ----------------

    expected_hours = {
        format_utc(
            start + timedelta(hours=i)
        )[:13]
        for i in range(WINDOW_HOURS)
    }

    for system in SYSTEM_CODES:

        missing = (
            expected_hours - hourly_coverage[system]
        )

        if missing:
            raise RuntimeError(
                f"{system} has missing hourly coverage: "
                f"{sorted(missing)}"
            )

    # Access Control must have discrete events every hour.
    access_event_hours = {
        record["ts"][:13]
        for record in events
        if asset_lookup[record["asset_code"]]["system_code"]
        == "ACCESS_CONTROL"
    }

    if access_event_hours != expected_hours:
        raise RuntimeError(
            "Access Control does not have event coverage in every hour."
        )

    # Verify every CCTV camera has an hourly heartbeat.
    for asset in ASSETS:

        asset_code, _name, asset_type, system, _location = asset

        if system == "CCTV" and asset_type == "camera":

            for hour_index in range(WINDOW_HOURS):

                timestamp = format_utc(
                    start + timedelta(hours=hour_index)
                )

                key = (
                    asset_code,
                    "heartbeat",
                    timestamp,
                )

                if key not in event_keys:
                    raise RuntimeError(
                        f"Missing CCTV heartbeat: {asset_code}, {timestamp}"
                    )

    # Verify the fire panel has an hourly heartbeat.
    for asset in ASSETS:

        asset_code, _name, asset_type, system, _location = asset

        if system == "FIRE_ALARM" and asset_type == "fire_panel":

            for hour_index in range(WINDOW_HOURS):

                timestamp = format_utc(
                    start + timedelta(hours=hour_index)
                )

                key = (
                    asset_code,
                    "heartbeat",
                    timestamp,
                )

                if key not in event_keys:
                    raise RuntimeError(
                        f"Missing fire-panel heartbeat: {asset_code}, "
                        f"{timestamp}"
                    )

    # ---------------- TIMESTAMP SPAN ----------------

    if not all_timestamps:
        raise RuntimeError(
            "No generated records were found."
        )

    earliest = min(all_timestamps)
    latest = max(all_timestamps)

    actual_span = latest - earliest

    if actual_span < timedelta(hours=24):
        raise RuntimeError(
            f"Generated timestamp span is insufficient: {actual_span}"
        )

    if earliest != start:
        raise RuntimeError(
            f"Unexpected earliest timestamp: {format_utc(earliest)}"
        )

    if latest != start + expected_interval * (sample_count - 1):
        raise RuntimeError(
            "Latest record does not match the final telemetry sample."
        )

    if latest >= end:
        raise RuntimeError(
            "Latest timestamp violates the exclusive end boundary."
        )

    return (
        earliest,
        latest,
        actual_span,
        system_counts,
        len(expected_hours),
    )


def write_jsonl(path, records):
    """Write UTF-8 JSON Lines, one JSON object per line."""

    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:

        for record in records:

            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            )


def read_jsonl(path):
    """Read JSONL from disk and verify each line is a JSON object."""

    records = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        for line_number, line in enumerate(file, start=1):

            if not line.strip():
                raise RuntimeError(
                    f"Empty line found in {path.name}, line {line_number}."
                )

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid JSON in {path.name}, "
                    f"line {line_number}: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise RuntimeError(
                    f"JSON record must be an object: "
                    f"{path.name}, line {line_number}."
                )

            records.append(record)

    return records


def main():

    print("Validating reference data and generation configuration...")

    start, end = validate_configuration()

    print("Generating telemetry...")

    telemetry, sample_count = generate_telemetry(
        start,
        end,
    )

    print("Generating discrete events...")

    events = generate_events(start)

    # Deduplicate using the same natural keys as the database constraints.
    telemetry, telemetry_duplicates = deduplicate(
        telemetry,
        ("asset_code", "metric_name", "ts"),
    )

    events, event_duplicates = deduplicate(
        events,
        ("asset_code", "event_type", "ts"),
    )

    print("Verifying generated records in memory...")

    verify_generated_data(
        telemetry,
        events,
        start,
        end,
        sample_count,
    )

    # Only write files after in-memory validation succeeds.
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    telemetry_path = OUTPUT_DIR / "telemetry.jsonl"
    events_path = OUTPUT_DIR / "events.jsonl"

    print("Writing telemetry.jsonl...")
    write_jsonl(
        telemetry_path,
        telemetry,
    )

    print("Writing events.jsonl...")
    write_jsonl(
        events_path,
        events,
    )

    # Read back the actual saved files.
    print("Reading generated files back from disk...")

    saved_telemetry = read_jsonl(telemetry_path)
    saved_events = read_jsonl(events_path)

    # Confirm the saved objects exactly match the generated objects.
    if saved_telemetry != telemetry:
        raise RuntimeError(
            "Saved telemetry records do not match generated telemetry."
        )

    if saved_events != events:
        raise RuntimeError(
            "Saved event records do not match generated events."
        )

    # Verify the persisted records independently.
    print("Verifying persisted records...")

    (
        earliest,
        latest,
        actual_span,
        system_counts,
        covered_hours,
    ) = verify_generated_data(
        saved_telemetry,
        saved_events,
        start,
        end,
        sample_count,
    )

    # ---------------- FINAL REPORT ----------------

    print()
    print("DATASET GENERATED AND VERIFIED")
    print("--------------------------------")

    print("Start (inclusive):", format_utc(start))
    print("End (exclusive):", format_utc(end))

    print("Earliest record:", format_utc(earliest))
    print("Latest record:", format_utc(latest))

    print("Actual timestamp span:", actual_span)

    print()
    print("Telemetry records:", len(saved_telemetry))

    print(
        "Telemetry series:",
        len({
            (r["asset_code"], r["metric_name"])
            for r in saved_telemetry
        })
    )

    print("Samples per series:", sample_count)

    print("Event records:", len(saved_events))

    print(
        "Duplicate telemetry removed:",
        telemetry_duplicates,
    )

    print(
        "Duplicate events removed:",
        event_duplicates,
    )

    print()
    print("Records by system (telemetry + events):")

    for system in sorted(SYSTEM_CODES):
        print(
            f"  {system}: {system_counts[system]}"
        )

    print()
    print(
        f"Hourly coverage: PASSED "
        f"({covered_hours}/{WINDOW_HOURS} hours per system)"
    )

    print("Access Control discrete-event coverage: PASSED")
    print("CCTV hourly camera heartbeats: PASSED")
    print("Fire-panel hourly heartbeats: PASSED")
    print("Telemetry five-minute intervals: PASSED")
    print("Timestamp boundaries: PASSED")
    print("Metric value ranges: PASSED")
    print("Record references: PASSED")
    print("Duplicate checks: PASSED")
    print("JSONL file read-back verification: PASSED")

    print()
    print("Output files:")

    print(" ", telemetry_path)
    print(" ", events_path)

    print()
    print("SQLite database was not modified.")
    print("Generation and file verification: SUCCESS")


if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        print()
        print("DATASET GENERATION FAILED")
        print("ERROR:", exc)

        sys.exit(1)
