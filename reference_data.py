import sys
from collections import Counter

SYSTEM_CODES = ["HVAC", "NETWORKING", "ACCESS_CONTROL", "CCTV", "FIRE_ALARM"]

# Dataset window: start inclusive, end exclusive (25 hours), fixed so it is reproducible
DATASET_START = "2026-11-01T00:00:00Z"
DATASET_END_EXCLUSIVE = "2026-11-02T01:00:00Z"
WINDOW_HOURS = 25
SAMPLE_INTERVAL_SECONDS = 300
SEED = 42

BUILDING = {"building_id": 1, "name": "Commercial Building A"}

# (location_id, floor, name)
LOCATIONS = [
    (1, 0, "Ground Lobby"),
    (2, 0, "Parking Entrance"),
    (3, 0, "IT Room"),
    (4, 1, "Floor 1 East"),
    (5, 1, "Floor 1 West"),
    (6, 2, "Floor 2 East"),
    (7, 2, "Floor 2 West"),
    (8, 3, "Floor 3 East"),
    (9, 3, "Floor 3 West"),
    (10, 4, "Roof Plant Room"),
]

# (name, unit)
METRIC_TYPES = [
    ("supply_air_temp", "C"),
    ("fan_speed_pct", "%"),
    ("zone_temp", "C"),
    ("zone_humidity_pct", "%"),
    ("bandwidth_mbps", "Mbps"),
    ("packet_loss_pct", "%"),
    ("cpu_load_pct", "%"),
]

EVENT_TYPES = [
    "filter_alarm", "high_temperature",
    "link_down", "link_up", "high_latency",
    "access_granted", "access_denied", "door_held_open", "forced_entry",
    "motion_detected", "camera_offline", "camera_online",
    "heartbeat",
    "detector_trouble", "alarm_test",
]

# asset_type -> metrics sampled every SAMPLE_INTERVAL_SECONDS
METRICS_BY_ASSET_TYPE = {
    "air_handler": ["supply_air_temp", "fan_speed_pct"],
    "zone_controller": ["zone_temp", "zone_humidity_pct"],
    "core_switch": ["bandwidth_mbps", "packet_loss_pct", "cpu_load_pct"],
    "floor_switch": ["bandwidth_mbps", "packet_loss_pct"],
}

# (asset_code, name, asset_type, system_code, location_id)
ASSETS = [
    # HVAC
    ("HVAC-AHU-01", "Air Handler 1", "air_handler", "HVAC", 10),
    ("HVAC-AHU-02", "Air Handler 2", "air_handler", "HVAC", 10),
    ("HVAC-ZN-1E", "Zone Controller Floor 1 East", "zone_controller", "HVAC", 4),
    ("HVAC-ZN-1W", "Zone Controller Floor 1 West", "zone_controller", "HVAC", 5),
    ("HVAC-ZN-2E", "Zone Controller Floor 2 East", "zone_controller", "HVAC", 6),
    ("HVAC-ZN-2W", "Zone Controller Floor 2 West", "zone_controller", "HVAC", 7),
    ("HVAC-ZN-3E", "Zone Controller Floor 3 East", "zone_controller", "HVAC", 8),
    ("HVAC-ZN-3W", "Zone Controller Floor 3 West", "zone_controller", "HVAC", 9),
    # Networking
    ("NET-CORE-01", "Core Switch", "core_switch", "NETWORKING", 3),
    ("NET-SW-1", "Floor 1 Switch", "floor_switch", "NETWORKING", 4),
    ("NET-SW-2", "Floor 2 Switch", "floor_switch", "NETWORKING", 6),
    ("NET-SW-3", "Floor 3 Switch", "floor_switch", "NETWORKING", 8),
    # Access control
    ("AC-RDR-LOBBY", "Lobby Door Reader", "card_reader", "ACCESS_CONTROL", 1),
    ("AC-RDR-PARK", "Parking Barrier Reader", "barrier_reader", "ACCESS_CONTROL", 2),
    ("AC-RDR-IT", "IT Room Door Reader", "card_reader", "ACCESS_CONTROL", 3),
    ("AC-RDR-1E", "Floor 1 East Door Reader", "card_reader", "ACCESS_CONTROL", 4),
    ("AC-RDR-2E", "Floor 2 East Door Reader", "card_reader", "ACCESS_CONTROL", 6),
    ("AC-RDR-3E", "Floor 3 East Door Reader", "card_reader", "ACCESS_CONTROL", 8),
    # CCTV
    ("CCTV-LOBBY", "Lobby Camera", "camera", "CCTV", 1),
    ("CCTV-PARK", "Parking Entrance Camera", "camera", "CCTV", 2),
    ("CCTV-IT", "IT Room Camera", "camera", "CCTV", 3),
    ("CCTV-1E", "Floor 1 East Camera", "camera", "CCTV", 4),
    ("CCTV-2E", "Floor 2 East Camera", "camera", "CCTV", 6),
    ("CCTV-3E", "Floor 3 East Camera", "camera", "CCTV", 8),
    # Fire alarm
    ("FA-PANEL-01", "Fire Alarm Panel", "fire_panel", "FIRE_ALARM", 1),
    ("FA-DET-1E", "Smoke Detector Floor 1 East", "smoke_detector", "FIRE_ALARM", 4),
    ("FA-DET-2E", "Smoke Detector Floor 2 East", "smoke_detector", "FIRE_ALARM", 6),
    ("FA-DET-3E", "Smoke Detector Floor 3 East", "smoke_detector", "FIRE_ALARM", 8),
    ("FA-DET-IT", "Smoke Detector IT Room", "smoke_detector", "FIRE_ALARM", 3),
]


def validate():
    errors = []
    loc_ids = [l[0] for l in LOCATIONS]
    if len(set(loc_ids)) != len(loc_ids):
        errors.append("duplicate location_id")
    if len({l[2] for l in LOCATIONS}) != len(LOCATIONS):
        errors.append("duplicate location name")
    codes = [a[0] for a in ASSETS]
    if len(set(codes)) != len(codes):
        errors.append("duplicate asset_code")
    metric_names = [m[0] for m in METRIC_TYPES]
    if len(set(metric_names)) != len(metric_names):
        errors.append("duplicate metric name")
    if len(set(EVENT_TYPES)) != len(EVENT_TYPES):
        errors.append("duplicate event type")
    for code, _name, atype, system, loc in ASSETS:
        if system not in SYSTEM_CODES:
            errors.append(f"{code}: unknown system {system}")
        if loc not in loc_ids:
            errors.append(f"{code}: unknown location {loc}")
        for m in METRICS_BY_ASSET_TYPE.get(atype, []):
            if m not in metric_names:
                errors.append(f"{code}: unknown metric {m}")
    present = {a[3] for a in ASSETS}
    for s in SYSTEM_CODES:
        if s not in present:
            errors.append(f"no assets for system {s}")
    return errors


if __name__ == "__main__":
    errs = validate()
    if errs:
        for e in errs:
            print("ERROR:", e)
        sys.exit(1)
    print("reference data OK")
    print("building:", BUILDING["name"])
    print("locations:", len(LOCATIONS))
    print("assets:", len(ASSETS))
    print("metric types:", len(METRIC_TYPES))
    print("event types:", len(EVENT_TYPES))
    for system, n in sorted(Counter(a[3] for a in ASSETS).items()):
        print(f"  {system}: {n} assets")
    series = sum(len(METRICS_BY_ASSET_TYPE.get(a[2], [])) for a in ASSETS)
    per_series = WINDOW_HOURS * 3600 // SAMPLE_INTERVAL_SECONDS
    print("telemetry series:", series)
    print("expected telemetry records:", series * per_series)