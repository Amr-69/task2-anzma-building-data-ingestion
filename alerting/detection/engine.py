"""Detection engine: fixed thresholds + rolling robust z-score + severity.

Reads telemetry from a SQLite DB (read-only) and returns incidents. Every
incident carries the telemetry_ids and values that caused it.
"""
import sqlite3
import statistics
import sys
from datetime import datetime
from pathlib import Path

from alerting import config

ROOT = Path(__file__).resolve().parents[2]


def parse_ts(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def threshold_level(metric, value):
    t = config.THRESHOLDS[metric]
    if t["direction"] == "high":
        if value > t["critical"]:
            return "critical"
        if value > t["warning"]:
            return "warning"
    else:
        if value < t["critical"]:
            return "critical"
        if value < t["warning"]:
            return "warning"
    return None


def directional_z(metric, value, window):
    """Robust z-score, signed so that positive means 'toward the failure side'."""
    med = statistics.median(window)
    mad = statistics.median([abs(v - med) for v in window])
    scale = max(1.4826 * mad, config.MIN_SCALE[metric])
    z = (value - med) / scale
    return z if config.THRESHOLDS[metric]["direction"] == "high" else -z


def finalize(inc, metric):
    levels = [p["level"] for p in inc["points"]]
    severity = "critical" if "critical" in levels else "warning"
    if severity == "warning" and inc["sustained"]:
        severity = "critical"
        inc["escalated_by"] = "sustained"
    inc["severity"] = severity
    values = [p["value"] for p in inc["points"]]
    high = config.THRESHOLDS[metric]["direction"] == "high"
    inc["peak_value"] = max(values) if high else min(values)
    inc["last_abnormal_ts"] = inc["points"][-1]["ts"]
    return inc


def analyze_series(asset, metric, rows):
    window, prev_dt = [], None
    run, thr_run, normal_run = [], 0, 0
    incident, incidents = None, []
    for tid, ts, value in rows:
        dt = parse_ts(ts)
        if prev_dt is not None and (dt - prev_dt).total_seconds() > config.GAP_RESET_S:
            window = []
        prev_dt = dt

        z = None
        if len(window) >= config.MIN_SAMPLES:
            z = directional_z(metric, value, window)
        level = threshold_level(metric, value)

        reasons, point = [], None
        if level:
            point = level
            reasons.append("threshold_" + level)
        if z is not None and z >= config.Z_ANOMALY:
            reasons.append("zscore_anomaly")
            if point is None:
                point = "warning"
            elif point == "warning" and z >= config.Z_ESCALATE:
                point = "critical"
                reasons.append("zscore_escalation")

        # Only threshold violations are kept out of the baseline window.
        if level is None:
            window.append(value)
            window = window[-config.WINDOW:]

        if point:
            normal_run = 0
            rec = {"telemetry_id": tid, "ts": ts, "value": value,
                   "z": None if z is None else round(z, 2),
                   "level": point, "reasons": reasons}
            run.append(rec)
            thr_run = thr_run + 1 if level else 0
            if incident is None and len(run) >= config.OPEN_AFTER:
                incident = {"asset_code": asset, "metric": metric, "status": "open",
                            "start_ts": run[0]["ts"], "detected_ts": ts,
                            "points": list(run), "sustained": False}
            elif incident is not None:
                incident["points"].append(rec)
            if incident is not None and thr_run >= config.SUSTAINED_READINGS:
                incident["sustained"] = True
        else:
            run, thr_run = [], 0
            if incident is not None:
                normal_run += 1
                if normal_run >= config.CLOSE_AFTER:
                    incident["status"] = "resolved"
                    incident["resolved_ts"] = ts
                    incidents.append(finalize(incident, metric))
                    incident, normal_run = None, 0
    if incident is not None:
        incidents.append(finalize(incident, metric))
    return incidents


def detect(db_path):
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA query_only = ON")
    rows = con.execute(
        """SELECT a.asset_code, m.name, t.telemetry_id, t.ts, t.value
           FROM telemetry_records t
           JOIN assets a ON a.asset_id = t.asset_id
           JOIN metric_types m ON m.metric_id = t.metric_id
           ORDER BY a.asset_code, m.name, t.ts"""
    ).fetchall()
    con.close()
    series = {}
    for asset, metric, tid, ts, value in rows:
        series.setdefault((asset, metric), []).append((tid, ts, value))
    incidents = []
    for (asset, metric), data in series.items():
        incidents.extend(analyze_series(asset, metric, data))
    return incidents


def main(paths):
    for p in paths:
        incs = detect(Path(p))
        print(f"\n== {Path(p).name}: {len(incs)} incident(s) ==")
        for i in incs:
            reasons = sorted({r for pt in i["points"] for r in pt["reasons"]})
            print(f'{i["severity"].upper():8} {i["asset_code"]}/{i["metric"]} '
                  f'start={i["start_ts"]} detected={i["detected_ts"]} '
                  f'status={i["status"]} end={i["last_abnormal_ts"]} '
                  f'points={len(i["points"])} peak={i["peak_value"]} '
                  f'reasons={",".join(reasons)}')


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        gen = ROOT / "alerting" / "scenarios" / "generated"
        args = [ROOT / "data" / "anzma_building.db"] + [gen / f"S{n}.db" for n in range(1, 6)]
    main(args)
