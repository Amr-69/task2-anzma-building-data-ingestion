"""Build five simulated fault scenarios as separate copies of the baseline DB.

The baseline DB (data/anzma_building.db) is never modified. Each scenario is a
copy in alerting/scenarios/generated/ with one asset/metric altered during a
short window. A JSON manifest records every altered row (original and new
value), so alerts can later be traced to a known injected fault.
"""
import hashlib
import json
import random
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root (Task 4)
BASELINE = ROOT / "data" / "anzma_building.db"
OUT_DIR = Path(__file__).resolve().parent / "generated"

# name, asset_code, metric, window start, window end, target value,
# noise, ramp readings, description
SCENARIOS = [
    ("S1", "HVAC-AHU-02", "supply_air_temp", "2026-11-01T10:00:00Z", "2026-11-01T12:00:00Z",
     23.5, 0.2, 6, "AHU-02 cooling failure: supply air temperature rises well above normal"),
    ("S2", "HVAC-AHU-01", "fan_speed_pct", "2026-11-01T14:00:00Z", "2026-11-01T16:00:00Z",
     8.0, 0.5, 1, "AHU-01 fan collapse: fan speed drops to near zero"),
    ("S3", "NET-SW-2", "packet_loss_pct", "2026-11-01T18:00:00Z", "2026-11-01T18:20:00Z",
     4.0, 0.2, 1, "NET-SW-2 short burst of packet loss"),
    ("S4", "NET-CORE-01", "cpu_load_pct", "2026-11-01T08:00:00Z", "2026-11-01T10:00:00Z",
     92.0, 1.0, 4, "NET-CORE-01 sustained CPU overload"),
    ("S5", "NET-SW-3", "bandwidth_mbps", "2026-11-01T12:00:00Z", "2026-11-01T14:00:00Z",
     30.0, 5.0, 1, "NET-SW-3 bandwidth collapse"),
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(scn, rng):
    name, asset, metric, start, end, target, noise, ramp, desc = scn
    dst = OUT_DIR / f"{name}.db"
    shutil.copyfile(BASELINE, dst)
    con = sqlite3.connect(dst)
    rows = con.execute(
        """SELECT telemetry_id, ts, value FROM telemetry_records
           WHERE asset_id = (SELECT asset_id FROM assets WHERE asset_code = ?)
             AND metric_id = (SELECT metric_id FROM metric_types WHERE name = ?)
             AND ts >= ? AND ts <= ? ORDER BY ts""",
        (asset, metric, start, end),
    ).fetchall()
    if not rows:
        raise SystemExit(f"{name}: no rows found for {asset}/{metric} in window")
    changed = []
    for i, (tid, ts, orig) in enumerate(rows):
        factor = min(1.0, (i + 1) / ramp)
        new = round(orig + (target - orig) * factor + rng.uniform(-noise, noise), 2)
        new = max(new, 0.0)
        con.execute("UPDATE telemetry_records SET value = ? WHERE telemetry_id = ?", (new, tid))
        changed.append({"telemetry_id": tid, "ts": ts, "original": orig, "new": new})
    con.commit()
    con.close()
    manifest = {
        "scenario": name, "description": desc, "asset_code": asset, "metric": metric,
        "window_start": start, "window_end": end, "rows_changed": len(changed),
        "changed_rows": changed,
    }
    (OUT_DIR / f"{name}_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"{name}: {asset}/{metric} {len(changed)} rows altered")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    before = sha256(BASELINE)
    rng = random.Random(42)  # fixed seed so results are reproducible
    for scn in SCENARIOS:
        build(scn, rng)
    after = sha256(BASELINE)
    print("Baseline DB unchanged:", before == after)
    if before != after:
        raise SystemExit("ERROR: baseline DB was modified")


if __name__ == "__main__":
    main()
