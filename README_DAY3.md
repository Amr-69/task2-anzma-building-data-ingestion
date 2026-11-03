# AnzmaTech — Day 3: Operational Dashboard & KPIs

An interactive operational dashboard built on top of the Day 2 building data ingestion service.

The dashboard presents building-system KPIs, historical trends, equipment status indicators, and an equipment-health summary. It reads the existing SQLite database without modifying its contents.

**All building records are synthetic demonstration data. No live building systems are connected.**

## 1. Deliverables

| Requirement | Implementation |
|---|---|
| Interactive operational dashboard | `/dashboard` |
| At least six measurable KPIs | Eight KPIs |
| Historical trends | Three hourly trend charts |
| System filters | HVAC, Networking, Access Control, CCTV, Fire Alarm |
| Building filters | Building selection |
| Time-period filters | Full range, last 1/6/12/24 hours, custom UTC range |
| Operational status indicators | Normal, Warning, Critical, No data |
| Equipment-health summary | Health and status counts by system |
| KPI definitions and calculations | `KPI_DEFINITIONS.md` |
| Automated verification | `test_dashboard.py` |

All dashboard values are calculated from the underlying database. They are not hardcoded.

## 2. Run the Dashboard

The dashboard is registered with the existing FastAPI application. No separate dashboard server is required.

From the project root:

```powershell
# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Start the application
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open the dashboard:

**http://127.0.0.1:8000/dashboard**

Other useful resources:

| Resource | URL |
|---|---|
| Operational Dashboard | [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard) |
| Swagger UI | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |
| OpenAPI specification | [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json) |

Stop the application using `Ctrl+C`.

## 3. Dashboard KPIs

The dashboard provides eight measurable KPIs:

| KPI | Description |
|---|---|
| Monitored Assets | Number of assets included in the selected filters |
| Healthy Assets % | Percentage of assets classified as Normal |
| Alerts Raised | Number of warning and critical events |
| Critical Alerts | Number of critical events |
| Alert Rate per Hour | Alerts divided by the selected period in hours |
| Average Zone Temperature | Average recorded zone temperature |
| Average Packet Loss | Average recorded network packet loss |
| Heartbeat Compliance | Received heartbeat records compared with expected heartbeat slots |

The calculation methods, definitions, units, and limitations are documented in `KPI_DEFINITIONS.md`.

## 4. Historical Trends

Three hourly trend charts are available:

- Alerts per hour, separated by warning and critical severity.
- Average zone temperature over time.
- Average network bandwidth over time.

The displayed trends respond to the selected filters.

## 5. Filters

The dashboard supports the following filters.

**System**

- All systems
- HVAC
- Networking
- Access Control
- CCTV
- Fire Alarm

**Building**

- Building selection based on the available database records.

The current dataset contains one building.

**Time period**

- Full available data range.
- Last 1 hour.
- Last 6 hours.
- Last 12 hours.
- Last 24 hours.
- Custom UTC date and time range.

Filters can be combined. The custom period is limited to 31 days.

The last-N-hours filters are calculated relative to the end of the stored dataset, not the current system clock.

## 6. Operational Status and Equipment Health

Each asset is assigned one of the following operational statuses:

| Status | Meaning |
|---|---|
| Normal | No active condition meeting the warning or critical rules |
| Warning | A warning condition has been detected |
| Critical | A critical condition has been detected |
| No data | No applicable data is available for the selected period |

The equipment-health summary groups assets by system and reports their status counts and health percentage.

An additional filter allows the user to display only assets with issues.

## 7. Dashboard API Endpoints

The dashboard uses two read-only endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/dashboard/filters` | Returns available systems, buildings, and data time range |
| GET | `/api/v1/dashboard/overview` | Returns KPIs, trends, equipment health, and asset statuses |

The overview endpoint supports:

| Parameter | Purpose |
|---|---|
| `system_type` | Filter by system |
| `building_id` | Filter by building |
| `start_time` | Inclusive UTC start timestamp |
| `end_time` | Exclusive UTC end timestamp |

Invalid filters return HTTP 422. A selected period longer than 31 days is rejected.

The dashboard does not provide database write operations.

## 8. Run the Tests

From the project root, activate the virtual environment and run:

```powershell
python -m py_compile main.py dashboard/dashboard.py dashboard/dashboard_core.py
python -m pytest -v
```

The automated test suite verifies:

- KPI calculations and data consistency.
- System and building filter combinations.
- Time-period filtering and timestamp validation.
- Equipment status rules and health-summary consistency.
- Database read-only behavior.
- Heartbeat compliance calculations.
- KPI documentation consistency.
- Invalid request rejection.

**Latest verified test result:**

- 17 tests passed.
- 38 subtests passed.
- Python compilation passed.

The dashboard has also been manually checked in the browser, including filter changes, KPI updates, trend charts, and the asset-health display.

## 9. Project Files

| Path | Responsibility |
|---|---|
| `main.py` | Registers the dashboard with the existing FastAPI application |
| `dashboard/__init__.py` | Dashboard package initialization |
| `dashboard/dashboard.py` | FastAPI dashboard routes and page serving |
| `dashboard/dashboard_core.py` | KPI calculations, SQL aggregation, filtering, and asset status logic |
| `dashboard/static/index.html` | Dashboard page structure |
| `dashboard/static/app.js` | Dashboard data loading, filters, and interactions |
| `dashboard/static/charts.js` | SVG trend chart rendering |
| `test_dashboard.py` | Automated dashboard tests |
| `KPI_DEFINITIONS.md` | KPI definitions, calculation methods, status rules, and limitations |
| `README_DAY3.md` | Day 3 implementation and verification documentation |

## 10. Implementation Scope

**New files:**

- Dashboard package and frontend files under `dashboard/`.
- `test_dashboard.py`
- `KPI_DEFINITIONS.md`
- `README_DAY3.md`

**Changed files:**

- `main.py` — registers the dashboard routes with the existing FastAPI application.

**Reused components:**

- Day 2 SQLite database and schema.
- Existing database modules and connection functionality.
- Existing telemetry and event records.
- Existing ingestion service and API functionality.

The Day 3 dashboard extends the existing service rather than replacing the Day 2 ingestion implementation.

## 11. Known Limitations

- The dataset contains one building, so building comparisons are not possible with the current data.
- The generated dataset is simulated and covers approximately 25 hours.
- Four additional manual test records dated October 31, 2026, are outside the generated sample window. These records are included in the database.
- Heartbeat compliance uses the intersection of the selected period and the available dataset coverage. Coverage is inferred from the earliest and latest available timestamps; internal missing-hour gaps are not independently detected.
- Access-control readers and smoke detectors do not have a dedicated liveness signal. Their status is derived from available events.
- Recovery events such as `link_up` and `camera_online` are not netted against earlier fault events.
- The dashboard is intended for local demonstration and does not include authentication or authorization.

Further KPI calculation details and limitations are available in `KPI_DEFINITIONS.md`.

---

**Day 3 Deliverable: Operational Dashboard & KPIs**

The dashboard extends the existing Day 2 service without replacing its ingestion functionality or modifying the committed database.