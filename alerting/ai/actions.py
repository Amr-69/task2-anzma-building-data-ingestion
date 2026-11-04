"""Candidate corrective actions, chosen by code (never invented by the LLM)."""

ACTIONS = {
    "supply_air_temp": [
        ("SAT-1", "Check the chilled-water valve and cooling coil supply for this air handler."),
        ("SAT-2", "Check the status and alarms of the chiller or cooling plant serving this unit."),
        ("SAT-3", "Inspect air filters and airflow for blockage."),
    ],
    "fan_speed_pct": [
        ("FAN-1", "Inspect the fan motor and its drive (VFD) for faults or trips."),
        ("FAN-2", "Check the fan belt or coupling for slippage or breakage."),
        ("FAN-3", "Check the power supply and breaker for this air handler."),
    ],
    "zone_temp": [
        ("ZT-1", "Check the zone controller setpoint and damper position for this zone."),
        ("ZT-2", "Check the supply air temperature of the serving air handler."),
        ("ZT-3", "Look for heat sources or open doors or windows near the zone."),
    ],
    "zone_humidity_pct": [
        ("ZH-1", "Compare the humidity sensor reading against a handheld reference."),
        ("ZH-2", "Check the dehumidification operation of the serving air handler."),
        ("ZH-3", "Look for moisture sources or ventilation problems in the zone."),
    ],
    "bandwidth_mbps": [
        ("BW-1", "Check the uplink port, cable and transceiver on this switch."),
        ("BW-2", "Check the upstream device and link status for this switch."),
        ("BW-3", "Look for link flapping or a failed neighbour in the device logs."),
    ],
    "packet_loss_pct": [
        ("PL-1", "Inspect the cable and transceiver on the affected port."),
        ("PL-2", "Check interface error counters and duplex settings."),
        ("PL-3", "Check for congestion on the uplink during the incident window."),
    ],
    "cpu_load_pct": [
        ("CPU-1", "Identify the processes or traffic flows driving CPU load."),
        ("CPU-2", "Check for a routing loop, broadcast storm or misbehaving device."),
        ("CPU-3", "Plan to shift load or fail over to a redundant device if load persists."),
    ],
}


def candidate_actions(metric):
    return [{"id": i, "text": t} for i, t in ACTIONS[metric]]


def _extreme_reading(ev):
    """Key reading furthest toward the failure side of the metric."""

    high = ev["thresholds"]["direction"] == "high"
    pick = max if high else min

    return pick(ev["key_readings"], key=lambda reading: reading["value"])


def _crossed_critical(ev, value):
    """True when the value passed the configured critical threshold."""

    thresholds = ev["thresholds"]

    if thresholds["direction"] == "high":
        return value > thresholds["critical"]

    return value < thresholds["critical"]


def select_actions(ev, count=2):
    """Choose corrective actions from the incident evidence (no LLM).

    Each metric has a catalog of candidate actions. A simple rule uses the
    measured readings to decide which catalog entry is checked first; the
    remaining entries follow in catalog order.

    Returns (action_ids, reasons). reasons maps each chosen action ID to a
    sentence that cites the reading or measurement the choice was based on.
    """

    ids = [action["id"] for action in ev["candidate_actions"]]
    metric = ev["metric"]
    unit = ev["unit"]
    critical = ev["thresholds"]["critical"]
    reading = _extreme_reading(ev)
    crossed = _crossed_critical(ev, reading["value"])
    duration = ev["duration_minutes"]
    sustained = ev.get("escalated_by") == "sustained"
    detection = set(ev["detection_reasons"])
    cite = f'reading {reading["telemetry_id"]} = {reading["value"]} {unit}'

    first = ids[0]
    why = "Standard first check for this metric."

    if metric == "fan_speed_pct" and crossed:
        first = "FAN-3"
        why = (
            f"{cite} is below the critical limit {critical} {unit}; "
            "a near-stopped fan points first to a power or breaker problem."
        )
    elif metric == "packet_loss_pct" and duration <= 30:
        first = "PL-3"
        why = (
            f"The incident lasted {duration} minutes ({cite}); "
            "a short burst points first to uplink congestion."
        )
    elif metric == "bandwidth_mbps" and crossed:
        first = "BW-2"
        why = (
            f"{cite} is below the critical limit {critical} {unit}; "
            "a collapse this deep points first to the upstream device or link."
        )
    elif metric == "cpu_load_pct" and sustained:
        first = "CPU-3"
        why = (
            "CPU load stayed at warning level for at least "
            f'{ev["sustained_readings_required"]} readings '
            f"(peak {cite}); persistent load calls for planning "
            "load shifting or failover first."
        )
    elif metric == "supply_air_temp" and not crossed:
        first = "SAT-3"
        why = (
            f"{cite} did not reach the critical limit {critical} {unit}; "
            "a moderate rise points first to airflow or filter restriction."
        )
    elif metric == "zone_humidity_pct" and detection == {"zscore_anomaly"}:
        first = "ZH-1"
        why = (
            "Only the statistical check fired, so confirm the sensor "
            "against a reference before checking the air handler."
        )
    elif crossed:
        why = (
            f"{cite} crossed the critical limit {critical} {unit}, "
            "so the primary check for this metric comes first."
        )

    order = [first] + [action_id for action_id in ids if action_id != first]
    chosen = order[:count]

    reasons = {chosen[0]: why}

    for action_id in chosen[1:]:
        reasons[action_id] = "Next standard check for this metric."

    return chosen, reasons