"""Day 4 alerting configuration. Every tunable number lives here."""

# Fixed thresholds. Basis: observed baseline envelope of data/anzma_building.db
# plus a margin (not vendor specifications).
# direction "high": alert when value rises above; "low": when it falls below.
THRESHOLDS = {
    "supply_air_temp":   {"direction": "high", "warning": 19.0,  "critical": 22.0},
    "fan_speed_pct":     {"direction": "low",  "warning": 20.0,  "critical": 10.0},
    "zone_temp":         {"direction": "high", "warning": 27.0,  "critical": 29.0},
    "zone_humidity_pct": {"direction": "high", "warning": 65.0,  "critical": 75.0},
    "bandwidth_mbps":    {"direction": "low",  "warning": 150.0, "critical": 50.0},
    "packet_loss_pct":   {"direction": "high", "warning": 3.0,   "critical": 5.0},
    "cpu_load_pct":      {"direction": "high", "warning": 90.0,  "critical": 95.0},
}

# Rolling robust z-score (median / MAD), computed on previous clean readings.
WINDOW = 24            # readings in the rolling window (2 hours at 5 min)
MIN_SAMPLES = 12       # no z-score until this many clean readings exist
# Calibrated on the clean baseline: its highest directional z is 7.2, while
# injected faults reach 13.5 to 24.9 (the CPU fault only 4.1 to 5.5, so it is
# caught by the fixed threshold instead). The initial planned value of 3
# produced 27 false incidents on the control run.
Z_ANOMALY = 8.0        # z in the failure direction at or above this is an anomaly
Z_ESCALATE = 8.0       # a threshold warning plus this z escalates to critical
GAP_RESET_S = 900      # a gap longer than 15 min restarts the window

# Minimum scale per metric, used when the window is almost flat (zero spread).
MIN_SCALE = {
    "supply_air_temp": 0.3,
    "fan_speed_pct": 2.0,
    "zone_temp": 0.2,
    "zone_humidity_pct": 1.0,
    "bandwidth_mbps": 20.0,
    "packet_loss_pct": 0.2,
    "cpu_load_pct": 2.0,
}

# Incident lifecycle.
OPEN_AFTER = 2             # consecutive abnormal readings to open an incident
CLOSE_AFTER = 3            # consecutive normal readings to resolve it
SUSTAINED_READINGS = 6     # consecutive THRESHOLD violations that escalate a warning to critical
