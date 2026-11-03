# Day 3 — KPI Definitions and Calculation Methods

Operational dashboard for the simulated commercial building (Anzma Tech, Day 3).

Every number on the dashboard is calculated from the Day 2 SQLite database when the page loads. No KPI value is stored in code, in a file, or in the page. Change the data and the numbers change (`test_kpis_follow_the_data` proves this on a copy of the database).

The dashboard opens `data/anzma_building.db` **read-only**. It cannot modify the Day 2 data.

## 1. How the numbers are produced

```text
Browser (static/index.html + app.js)
    -> GET /api/v1/dashboard/overview?system_type=&building_id=&start_time=&end_time=
    -> dashboard.py (FastAPI, validation, HTTP errors)
    -> dashboard_core.py (SQL aggregation, status rules)
    -> data/anzma_building.db (read-only)
```

The existing Day 2 retrieval API returns at most 1,000 rows per page and does no aggregation, so the KPIs are computed with SQL (`COUNT`, `SUM`, `AVG`, `GROUP BY`) directly in the database instead.

## 2. Filters

| Filter | Parameter | Rule |
|---|---|---|
| System | `system_type` | `HVAC`, `NETWORKING`, `ACCESS_CONTROL`, `CCTV`, `FIRE_ALARM`; empty = all |
| Building | `building_id` | Must exist in `buildings`; empty = all. The dataset has one building, so this filter has one choice. |
| Time period | `start_time`, `end_time` | UTC, `YYYY-MM-DDTHH:MM:SSZ`, whole seconds. **Start inclusive, end exclusive**, the same rule and the same timestamp validation as the Day 2 API. Maximum 31 days. |

All filters combine. When no period is given, the period is the full time extent of the stored data: from the earliest to the latest timestamp found in `telemetry_records` and `event_records` (end = latest timestamp + 1 second, exclusive).

**The preset periods ("Last 1 hour" and so on) are measured back from the end of the data, not from the clock.** The data is simulated for 1–2 November 2026, so a clock-based "last hour" would show every asset as silent.

The default period includes four manual test rows from 31 October that sit outside the 25-hour sample window (two telemetry readings and two events, listed in the Day 2 README). That is why the dashboard reports 7,502 telemetry readings and 212 events instead of 7,500 and 210.

## 3. KPI definitions

"Scope" means the assets that match the system and building filters. "Period" means `start <= ts < end`.

| # | KPI | Unit | Calculation | Source tables | Responds to |
|---|---|---|---|---|---|
| 1 | Monitored assets | assets | Number of assets in scope: `COUNT(*)` over `assets` joined to `system_types` and `locations` | assets | system, building |
| 2 | Healthy assets | % | Assets whose status is Normal (section 4) divided by monitored assets, times 100, one decimal | assets, telemetry_records, event_records | all three |
| 3 | Alerts raised | alerts | `COUNT(*)` of events in scope and period with `severity IN ('warning','critical')` | event_records | all three |
| 4 | Critical alerts | alerts | `COUNT(*)` of events in scope and period with `severity = 'critical'` | event_records | all three |
| 5 | Alert rate | alerts/hour | Alerts raised divided by the period length in hours, two decimals | event_records | all three |
| 6 | Average zone temperature | °C | `AVG(value)` of metric `zone_temp` in scope and period, two decimals | telemetry_records, metric_types | all three |
| 7 | Average packet loss | % | `AVG(value)` of metric `packet_loss_pct` in scope and period, two decimals | telemetry_records, metric_types | all three |
| 8 | Heartbeat compliance | % | Heartbeat events received divided by expected heartbeat events, times 100, capped at 100. Expected events = assets that send heartbeats × the number of whole-hour instants within the intersection of the selected period and available dataset coverage. | event_records, event_types | all three |

Core SQL pattern (KPI 3, 4):

```sql
WITH scope AS (
    SELECT a.asset_id FROM assets a
    JOIN system_types st ON st.system_type_id = a.system_type_id
    JOIN locations l ON l.location_id = a.location_id
    WHERE (:system IS NULL OR st.code = :system)
      AND (:building IS NULL OR l.building_id = :building)
)
SELECT SUM(e.severity = 'warning') AS warnings,
       SUM(e.severity = 'critical') AS criticals
FROM event_records e JOIN scope s ON s.asset_id = e.asset_id
WHERE e.ts >= :start AND e.ts < :end;
```

KPI 6 and 7 use the same `scope` joined to `telemetry_records` and `metric_types` with `WHERE mt.name = :metric`.

### Meaningful combinations

A KPI that cannot apply to the selected system shows **N/A**, not 0.

| KPI | N/A when the scope has no asset that… |
|---|---|
| Average zone temperature | reports `zone_temp` (only HVAC zone controllers do) |
| Average packet loss | reports `packet_loss_pct` (only network switches do) |
| Heartbeat compliance | sends heartbeats (only CCTV cameras and the fire panel do) |

Applicability is read from the data (does any asset in scope have such readings at all), not from a fixed list.

Heartbeat compliance also shows no value when there are no whole-hour instants within the intersection of the selected period and available dataset coverage, because there is no expected heartbeat count to compare against.

## 4. Operational status of an asset

Status is evaluated for the selected period, so it responds to the time filter.

| Order | Status | Rule |
|---|---|---|
| 1 | **Critical** | At least one `critical` event in the period |
| 2 | **No data** | The asset has a liveness signal (below) and sent none in the period |
| 3 | **Warning** | At least one `warning` event in the period |
| 4 | **Normal** | None of the above |

**Liveness signal**, derived from the data: an asset that has any telemetry is expected to send telemetry (HVAC and networking). Otherwise an asset that has any `heartbeat` event is expected to send heartbeats (CCTV cameras and the fire panel). Any other asset has no liveness signal.

## 5. Equipment-health summary

For each system in scope: assets, number Normal / Warning / Critical / No data, and a health percentage (Normal ÷ assets × 100). A total row is shown when more than one system is in scope. Below it, every asset is listed with its status, the reason for that status, its warning and critical counts, and when it was last seen.

## 6. Trends

Hourly buckets (UTC) across the selected period, built with `strftime('%Y-%m-%dT%H:00:00Z', ts)` and `GROUP BY`:

- Alerts per hour, stacked by warning and critical
- Average zone temperature per hour
- Average network bandwidth per hour (`bandwidth_mbps`)

The first and last bucket can be partial hours when the period does not start or end on the hour.

## 7. Reference values (full data range, all systems)

Measured on the committed database. They are shown so a reviewer can compare, not stored anywhere.

| KPI | Value |
|---|---|
| Monitored assets | 29 |
| Healthy assets | 65.5 % (19 of 29) |
| Alerts raised | 22 (21 warning, 1 critical) |
| Critical alerts | 1 |
| Alert rate | 0.88 alerts/hour over 25.00 h |
| Average zone temperature | 23.92 °C (1,800 readings) |
| Average packet loss | 0.87 % (1,200 readings) |
| Heartbeat compliance | 100 % (175 received, 175 expected) |

## 8. Verification

```powershell
python test_dashboard.py
```

The tests recompute the numbers from the raw tables with plain `SELECT`s and Python arithmetic, independently of the dashboard's SQL, and compare:

- All KPIs against the raw tables for the default period, for all 5 systems × 2 building filters, and for a custom period
- The exclusive end boundary of the period
- Heartbeat compliance, including a period without a whole hour
- Heartbeat compliance when the selected period extends beyond available dataset coverage
- N/A behaviour for systems the KPI does not apply to
- Status rules, including the No data status in an empty period
- Health-summary counts add up; hourly trends add up to the alert KPIs
- Rejection of invalid systems, buildings, timestamps and periods
- The dashboard's timestamp rules equal the Day 2 API's (`main.parse_utc_timestamp`)
- The database is opened read-only and its file hash is unchanged after the dashboard runs
- On a temporary copy: inserting one critical event and one reading changes the KPIs and the asset's status

## 9. Known limitations

- **Recoveries are not netted out.** A `link_down` followed by a `link_up`, or `camera_offline` followed by `camera_online`, still leaves the asset at Warning for the period, because status uses the most severe event in the period.
- **Access-control readers have no liveness signal.** They send events only when someone uses them, so silence cannot be told apart from a fault. Their status comes from events alone. Every access-control event in this dataset is a warning (`access_denied`, `door_held_open`), so most readers show Warning. That follows the stated rules; it reflects how the data was simulated.
- **Smoke detectors** have no heartbeat either, so they are Normal unless they raise an event.
- **Status uses events only.** Telemetry values are used for the averages and trends, not for status, because the simulated values sit inside fixed ranges and fixed thresholds would flag assets without a real cause.
- **One building and 25 hours of data.** The building filter has one choice and the longest trend has about 26 hourly points.
- **Alerts raised counts events in the period; it is not a live "currently active" count.**
- **Heartbeat coverage limitation:** Available dataset coverage is inferred from the earliest and latest timestamps across telemetry and event records. This approach does not independently detect missing internal hours within that range.
- The simulated data is synthetic. Nothing here is live building data.