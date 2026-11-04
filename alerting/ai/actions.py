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
