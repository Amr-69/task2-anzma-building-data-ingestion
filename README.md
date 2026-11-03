# Day 3 — Operational Dashboard (this branch)

Branch: `day3-dashboard`. Full Day 3 documentation: **[README_DAY3.md](README_DAY3.md)**.

| Item | Detail |
|---|---|
| Dashboard | [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard) |
| KPI definitions | [KPI_DEFINITIONS.md](KPI_DEFINITIONS.md) |
| Tests | `python test_dashboard.py` |

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# Anzma Tech — Building Data Ingestion Service

Simulated commercial-building telemetry and events, stored in SQLite and exposed through a local REST API.

The sample covers HVAC, networking, access control, CCTV, and fire alarm. Records are synthetic. Nothing in this repository is live building data.

## Deliverables

| Request | Where it is |
|---|---|
| Ingestion service | `POST /api/v1/telemetry/batch`, `POST /api/v1/events/batch` |
| Database and documented API | `data/anzma_building.db`, this file, Swagger at `/docs` |
| At least 24 hours of records | 25-hour window, 1 Nov 2026 00:00:00Z through 2 Nov 2026 01:00:00Z exclusive |
| Data-flow diagram | [DATA_FLOW.md](DATA_FLOW.md) |
| Retrieval by asset, location, timestamp, and system type | `GET /api/v1/telemetry`, `GET /api/v1/events` |

Generation and ingestion are separate. `generate_data.py` writes JSONL only. It does not insert into SQLite and it does not call the API.

## Review the committed database

Start here for a live review. This procedure only reads the committed database. It does not load the sample again.

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

| Resource | URL |
|---|---|
| Swagger UI | http://127.0.0.1:8000/docs |
| OpenAPI | http://127.0.0.1:8000/openapi.json |

Stop the server with `Ctrl+C`.

The service always opens `data/anzma_building.db`. Do not run `python init_db.py --reset` against that file. `--reset` deletes it.

### What the first rows are

Unfiltered telemetry is ordered by timestamp, so the first row is not the start of the sample. It is a manual test insert:

| Table | IDs | Asset | What | Timestamp |
|---|---|---|---|---|
| `telemetry_records` | 1, 2 | `HVAC-AHU-01` | `supply_air_temp` 15.2 and 15.3 | `2026-10-31T23:55:00Z`, `2026-10-31T23:57:00Z` |
| `event_records` | 1, 2 | `CCTV-LOBBY` | `motion_detected`, details contain the word "test" | `2026-10-31T23:56:00Z`, `2026-10-31T23:57:00Z` |

Those four rows are why the database counts are higher than the generator counts. They sit outside the sample window. Pass `start_time=2026-11-01T00:00:00Z` when the review should show only the generated sample.

### Counts

| | Generated JSONL | Committed database |
|---|---:|---:|
| Telemetry | 7,500 | 7,502 |
| Events | 210 | 212 |

Inside the sample window the database matches the JSONL exactly. `PRAGMA integrity_check` is `ok`. `PRAGMA foreign_key_check` returns no rows.

### Retrieval checks

Filters combine with AND. `start_time` is inclusive. `end_time` is exclusive. `limit` defaults to 100 and cannot exceed 1,000. Follow `next_offset` while `has_more` is true.

IDs used below are the ids in the committed database:

| asset_id | asset_code | location_id | location | system |
|---:|---|---:|---|---|
| 1 | HVAC-AHU-01 | 10 | Roof Plant Room | HVAC |
| 9 | NET-CORE-01 | 3 | IT Room | NETWORKING |
| 13 | AC-RDR-LOBBY | 1 | Ground Lobby | ACCESS_CONTROL |

```powershell
# Combined filter. Expect returned = 600, all HVAC-AHU-01, all inside the window.
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/telemetry?asset_id=1&location_id=10&system_type=HVAC&start_time=2026-11-01T00:00:00Z&end_time=2026-11-02T01:00:00Z&limit=1000"

# One asset. Expect 900 rows for NET-CORE-01 (page with limit=1000).
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/telemetry?asset_id=9&limit=1000"

# Last five minutes of the window. Expect 25 rows, timestamp 2026-11-02T00:55:00Z.
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/telemetry?start_time=2026-11-02T00:55:00Z&end_time=2026-11-02T01:00:00Z&limit=1000"

# Exclusive end. Expect 25 rows, none at 00:55:00Z.
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/telemetry?start_time=2026-11-02T00:50:00Z&end_time=2026-11-02T00:55:00Z&limit=1000"

# Access control has events and no telemetry. Expect 25 events.
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/events?system_type=ACCESS_CONTROL&limit=100"

# CCTV, fire alarm: events only. HVAC and networking: both.
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/telemetry?system_type=CCTV&limit=10"
```

`asset_id=1` together with `location_id=1` returns zero rows. The asset is not in that location. An unknown `system_type`, a `limit` above 1000, or a `start_time` that is not earlier than `end_time` returns HTTP 422.

There is no `asset_code` query parameter. Ingestion uses codes. Retrieval uses numeric ids. The response body includes `asset_code`, `location_name`, and `system_type`.

### Do not ingest the sample into this database

The generated rows are already stored. Posting them again hits the unique key and returns HTTP 409. The batch is rolled back. The counts stay 7,502 and 212. That 409 means the rows are already there. It does not mean the service failed.

## Sample data

| Property | Value |
|---|---|
| Start, inclusive | `2026-11-01T00:00:00Z` |
| End, exclusive | `2026-11-02T01:00:00Z` |
| Telemetry interval | 5 minutes |
| Series | 25 |
| Samples per series | 300 |
| Telemetry rows | 7,500 |
| Event rows | 210 |
| Random seed | 42 |

Hourly coverage is 25/25 hours for each system. HVAC and networking get that coverage from telemetry. Access control gets one event per hour. CCTV gets one heartbeat per camera per hour. Fire alarm gets one panel heartbeat per hour. This is enough to satisfy a 24-hour retrieval test. It is not a realistic occupant or alarm rate.

`forced_entry` is a defined event type. The sample never emits it. Fourteen of the fifteen event types appear at least once.

Regenerate the files with:

```powershell
python generate_data.py
```

That overwrites `data/generated/telemetry.jsonl` and `data/generated/events.jsonl`. It prints `SQLite database was not modified` when it succeeds.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/telemetry/batch` | Insert a telemetry batch |
| `POST` | `/api/v1/events/batch` | Insert an event batch |
| `GET` | `/api/v1/telemetry` | Read telemetry |
| `GET` | `/api/v1/events` | Read events |

### Ingestion

Telemetry fields: `asset_code`, `metric_name`, `ts`, `value`.

Event fields: `asset_code`, `event_type`, `ts`, `severity` (`info`, `warning`, or `critical`), optional `details`.

`ts` must be `YYYY-MM-DDTHH:MM:SSZ`, real UTC, whole seconds. `value` must be a finite number. Booleans are rejected. Unknown JSON fields are rejected. `records` must be a non-empty array.

Both posts run in one SQLite transaction. One bad row rolls back the batch.

| Failure | HTTP | Database |
|---|---|---|
| Malformed JSON or a field the schema rejects | 422 | unchanged |
| Unknown asset, metric, or event type | 422 | unchanged |
| Metric not allowed for that asset type | 422 | unchanged |
| Duplicate natural key, including a duplicate inside the same batch | 409 | unchanged |

A successful batch returns HTTP 201 and `inserted` equal to the number of rows submitted. Telemetry and events are separate transactions.

What is enforced:

- The asset code exists.
- The metric or event type exists.
- For telemetry, `reference_data.py` allows that metric on that asset type.

What is not enforced:

- Event type is not tied to the asset's system. An air handler can accept `forced_entry`.
- Severity is not checked against the event type. `forced_entry` can be submitted as `info`.
- The SQLite timestamp `CHECK` is weaker than the API. This SQLite build accepts `2026-02-31` and hour `24`. The API rejects both. `test_schema.py` does not cover those two values.

### Retrieval parameters

| Parameter | Rule |
|---|---|
| `asset_id` | Integer greater than 0 |
| `location_id` | Integer greater than 0 |
| `system_type` | `HVAC`, `NETWORKING`, `ACCESS_CONTROL`, `CCTV`, or `FIRE_ALARM` |
| `start_time` | Inclusive UTC timestamp |
| `end_time` | Exclusive UTC timestamp, must be later than `start_time` |
| `limit` | 1 to 1000, default 100 |
| `offset` | Default 0 |

The response fields are `returned`, `limit`, `offset`, `has_more`, `next_offset`, and `items`. Rows are ordered by timestamp, then id. A filter that matches nothing returns HTTP 200 and an empty `items` list, not 404.

## Load a fresh database

Do this only on a copy. The steps below move the committed database aside and build a new one.

Stop the API first.

```powershell
Move-Item data\anzma_building.db data\anzma_building.snapshot.db
python init_db.py
python seed_reference.py
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

There is no loader script in the repository. The JSONL files are not themselves request bodies. Each request must be `{"records": [ ... ]}`. From a second shell, in the project root:

```powershell
python -c @"
import json
from pathlib import Path
from urllib.request import Request, urlopen

def post(path, name):
    records = [json.loads(line) for line in Path(name).read_text(encoding='utf-8').splitlines()]
    req = Request(
        'http://127.0.0.1:8000' + path,
        data=json.dumps({'records': records}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urlopen(req) as resp:
        print(path, resp.status, resp.read().decode())

post('/api/v1/telemetry/batch', 'data/generated/telemetry.jsonl')
post('/api/v1/events/batch', 'data/generated/events.jsonl')
"@
```

A clean load inserts 7,500 telemetry rows and 210 events. Posting either file again returns 409 and does not add rows.

The loader example above is PowerShell. In `cmd.exe`, save the Python block as `load_sample.py` and run `python load_sample.py`. Do not commit that file. It is a review tool, not part of the service.

Restore the submitted snapshot before pushing or demonstrating retrieval again. Stop the server first.

```powershell
Remove-Item data\anzma_building.db
Move-Item data\anzma_building.snapshot.db data\anzma_building.db
```

`python init_db.py` refuses to replace a database that is already there. `--reset` deletes the file. Do not point `--reset` at the only copy of the snapshot.

`seed_reference.py` refuses to run when the reference tables already contain rows.

## Schema

Reference tables: `buildings` (1), `locations` (10), `system_types` (5), `assets` (29), `metric_types` (7), `event_types` (15).

Fact tables: `telemetry_records`, `event_records`.

Foreign keys link locations to the building, assets to a system type and a location, and fact rows to an asset plus a metric or event type. SQLite does not enable foreign keys by default. `db.py` sets `PRAGMA foreign_keys = ON` for application connections. A `sqlite3` shell will not enforce them unless the same pragma is set.

Asset type is a string on `assets`, not its own table. Which metrics an asset type may emit is a Python rule in `reference_data.py`, applied by the API, not a foreign key.

```powershell
python test_schema.py
```

The script builds an in-memory database, checks valid inserts, and checks that broken foreign keys, duplicate natural keys, illegal system codes, illegal severities, and several bad timestamps are rejected. It does not call the API and it does not modify `data/anzma_building.db`.

## Project layout

| Path | Role |
|---|---|
| `main.py` | FastAPI application |
| `db.py` | Connection and `PRAGMA foreign_keys` |
| `schema.sql` | Tables, checks, indexes |
| `init_db.py` | Create the database and the five system codes |
| `reference_data.py` | Buildings, locations, assets, metrics, events |
| `seed_reference.py` | Insert reference rows into an empty database |
| `generate_data.py` | Write and check the JSONL sample |
| `test_schema.py` | In-memory constraint checks |
| `DATA_FLOW.md` | Flow from generator to API to SQLite |
| `data/anzma_building.db` | Submitted snapshot |
| `data/generated/*.jsonl` | Generated sample |

## Setup

Python 3.10 or newer. The syntax uses `str | None`.

```powershell
git clone https://github.com/Amr-69/task2-anzma-building-data-ingestion.git
cd task2-anzma-building-data-ingestion
git checkout day3-dashboard
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Pinned direct dependencies: FastAPI 0.162.0, Uvicorn 0.54.0, Pydantic 2.14.2.

On a machine that already has the dependencies, the virtual environment is optional. The run command is still `python -m uvicorn main:app --host 127.0.0.1 --port 8000`.

## Limits

- No authentication or authorization. The documented command binds to `127.0.0.1`. Do not expose this process on a network.
- No asset-code or location-name filter. Use the ids, or read the codes from the response.
- No total row count in the page body. Use `has_more` and `next_offset`.
- Access-control, CCTV, and fire-alarm assets do not emit telemetry.
- Re-posting an existing natural key rejects the whole batch.
- The four test rows listed above are part of the committed file on purpose, so the published counts stay stable. They are not part of the 25-hour sample.

## Data flow

```text
reference_data.py
    -> generate_data.py -> data/generated/*.jsonl
    -> HTTP client (not shipped; see "Load a fresh database")
    -> FastAPI validation
    -> SQLite transaction
    -> GET /api/v1/telemetry and GET /api/v1/events
```

The diagram with the same steps is in [DATA_FLOW.md](DATA_FLOW.md).
