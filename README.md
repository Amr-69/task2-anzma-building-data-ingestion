# Anzma Tech — Building Data Ingestion Service

## 1. Project Overview

A Python-based data ingestion and retrieval service for a simulated commercial building environment.

The service handles two types of operational data:

- **Telemetry:** Periodic measurements from building assets, such as temperatures, humidity, network bandwidth, packet loss, and CPU load.
- **Events:** Discrete operational events, such as access-control activity, equipment alarms, network failures, camera status changes, and heartbeats.

**Technology stack**

| Component | Technology |
|---|---|
| Programming language | Python 3.11 |
| REST API | FastAPI |
| Request validation | Pydantic |
| Database | SQLite |
| API documentation | OpenAPI / Swagger UI |
| Data format | JSON / JSONL |

> All included records are synthetic sample data. They do not represent live production building telemetry.

## 2. Architecture and Data Flow

The implementation follows this processing flow:

1. Reference definitions describe buildings, locations, assets, system types, metric types, and event types.
2. `generate_data.py` generates synthetic telemetry and operational event records.
3. The generator saves the records as JSONL files and validates the persisted files.
4. An HTTP client submits batches to the FastAPI ingestion endpoints.
5. Pydantic validates request structure and field values.
6. The API resolves asset and reference identifiers and validates relationships.
7. SQLite transactions persist accepted records.
8. Retrieval endpoints return records based on optional filters and pagination.

See [DATA_FLOW.md](DATA_FLOW.md) for the implementation diagram.

**Important distinction:** Data generation and database ingestion are separate operations. Running the generator does not automatically insert records into SQLite.

## 3. Project Structure

| File or directory | Purpose |
|---|---|
| `main.py` | FastAPI application, request models, ingestion and retrieval endpoints |
| `db.py` | SQLite connection configuration and database paths |
| `schema.sql` | Relational database schema, constraints, and indexes |
| `init_db.py` | Database initialization |
| `reference_data.py` | Building, location, asset, system, metric, and event definitions |
| `seed_reference.py` | Validated reference-data seeding |
| `generate_data.py` | Synthetic telemetry and event generation and verification |
| `test_schema.py` | Database schema and integrity constraint tests |
| `requirements.txt` | Pinned Python dependencies |
| `.gitignore` | Excludes local environments, caches, secrets, logs, and database backups |
| `DATA_FLOW.md` | Data-flow diagram |
| `data/anzma_building.db` | Populated SQLite database snapshot |
| `data/generated/telemetry.jsonl` | Generated telemetry records |
| `data/generated/events.jsonl` | Generated event records |

## 4. Environment Setup

The project uses Python 3.11.

### Clone the repository

```powershell
git clone https://github.com/Amr-69/task2-anzma-building-data-ingestion.git
cd task2-anzma-building-data-ingestion
```

Access to this private repository must be granted through GitHub.

### Create and activate a virtual environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Install dependencies

```powershell
python -m pip install -r requirements.txt
```

The direct dependencies are pinned in `requirements.txt`:

- FastAPI 0.162.0
- Uvicorn 0.54.0
- Pydantic 2.14.2

## 5. Run the API

The repository includes an initialized and populated SQLite database snapshot.

From the project root, start the application:

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The API will be available locally at:

| Resource | URL |
|---|---|
| Swagger UI | http://127.0.0.1:8000/docs |
| OpenAPI schema | http://127.0.0.1:8000/openapi.json |

Swagger UI provides interactive request schemas and endpoint documentation.

Stop the server using `Ctrl+C`.

**Database safety:** The existing database is already populated. Do not run `init_db.py --reset` against this database. The `--reset` option deletes the existing database file before recreating it.

## 6. Database Design

The database contains six reference tables and two operational record tables.

### Reference tables

| Table | Purpose | Records |
|---|---|---:|
| `buildings` | Building definitions | 1 |
| `locations` | Building locations | 10 |
| `system_types` | Approved building system categories | 5 |
| `assets` | Registered building assets | 29 |
| `metric_types` | Telemetry measurement definitions | 7 |
| `event_types` | Operational event definitions | 15 |

### Operational tables

| Table | Purpose |
|---|---|
| `telemetry_records` | Timestamped asset measurements |
| `event_records` | Timestamped operational events |

The schema uses foreign keys to preserve relationships between operational records and their reference definitions.

Natural-key uniqueness constraints prevent duplicate telemetry records for the same asset, metric, and timestamp, and duplicate events for the same asset, event type, and timestamp.

SQLite foreign-key enforcement is enabled for application connections.

## 7. API Endpoint Reference

The API exposes four main endpoints.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/telemetry/batch` | Ingest a telemetry batch |
| `POST` | `/api/v1/events/batch` | Ingest an event batch |
| `GET` | `/api/v1/telemetry` | Retrieve telemetry records |
| `GET` | `/api/v1/events` | Retrieve operational events |

### 7.1 Telemetry ingestion

`POST /api/v1/telemetry/batch`

Each submitted record contains:

| Field | Description |
|---|---|
| `asset_code` | Registered asset code |
| `metric_name` | Existing metric definition |
| `ts` | UTC timestamp in `YYYY-MM-DDTHH:MM:SSZ` format |
| `value` | Finite numeric measurement |

Telemetry validation includes asset existence, metric existence, and compatibility between the asset type and the submitted metric.

### 7.2 Event ingestion

`POST /api/v1/events/batch`

Each submitted record contains:

| Field | Description |
|---|---|
| `asset_code` | Registered asset code |
| `event_type` | Existing event type |
| `ts` | UTC timestamp in `YYYY-MM-DDTHH:MM:SSZ` format |
| `severity` | `info`, `warning`, or `critical` |
| `details` | Optional event details |

### 7.3 Batch transaction behavior

Both POST endpoints:

- Require a non-empty `records` array.
- Reject unexpected request fields.
- Validate records before committing the batch.
- Use SQLite transactions.
- Roll back the entire batch if a record fails reference validation or violates database integrity constraints.

A successful batch returns HTTP `201 Created`.

The two ingestion endpoints use separate transactions. There is no single transaction spanning both telemetry and event batches.

### 7.4 Retrieval filters

Both GET endpoints support the following optional query parameters:

| Parameter | Description |
|---|---|
| `asset_id` | Filter by asset ID |
| `location_id` | Filter by location ID |
| `system_type` | Filter by approved system code |
| `start_time` | Inclusive UTC timestamp boundary |
| `end_time` | Exclusive UTC timestamp boundary |
| `limit` | Page size, minimum 1, maximum 1000; default 100 |
| `offset` | Number of records to skip; default 0 |

Filters can be combined.

Retrieval responses include:

- `returned`
- `limit`
- `offset`
- `has_more`
- `next_offset`
- `items`

Results are ordered by timestamp and record ID.

## 8. Synthetic Sample Dataset

The generated sample period is a fixed 25-hour UTC window.

| Property | Value |
|---|---|
| Start (inclusive) | `2026-11-01T00:00:00Z` |
| End (exclusive) | `2026-11-02T01:00:00Z` |
| Telemetry interval | 5 minutes |
| Telemetry series | 25 |
| Samples per series | 300 |
| Total telemetry records | 7,500 |
| Total event records | 210 |
| Hourly coverage | 25 of 25 hours |

The generator uses a fixed random seed to support reproducible sample generation.

It validates timestamp boundaries, metric value ranges, asset and metric references, event types, event severities, duplicate natural keys, telemetry intervals, hourly coverage, and the saved JSONL files.

The telemetry file contains 7,500 records and the event file contains 210 records.

### Regenerate sample files

```powershell
python generate_data.py
```

This regenerates and overwrites the JSONL sample files in `data/generated/`.

The generator does not modify the SQLite database or send records to the API.

The generated JSONL files are not themselves batch API request bodies. An HTTP client must submit the records using the API's JSON batch request structure, with a `records` array.

## 9. Included Database Snapshot

The committed SQLite database contains:

| Record type | Total database records |
|---|---:|
| Telemetry | 7,502 |
| Events | 212 |

The totals include two pre-existing telemetry records and two pre-existing event records outside the generated sample window.

The generated sample records were ingested through their respective REST batch endpoints.

The database snapshot can be queried immediately after starting the API. Reinitialization and reseeding are not required.

## 10. Database Initialization for a New Environment

The included database is already initialized and seeded. This section is only for creating a new, empty database.

First ensure that the target database file does not already exist or that its existing contents have been safely backed up.

Initialize the schema:

```powershell
python init_db.py
```

Seed the reference data:

```powershell
python seed_reference.py
```

The initialization script refuses to replace an existing database unless `--reset` is explicitly supplied.

**Warning:** `python init_db.py --reset` deletes the current database file. Do not use it against the included populated database unless its destruction is intentional and an appropriate backup exists.

Reference seeding refuses to proceed when protected tables already contain records and validates the relationships before committing.

After initialization and seeding, records must still be submitted through the REST ingestion endpoints.

## 11. Schema Verification

Run the database schema checks:

```powershell
python test_schema.py
```

The test script creates an in-memory SQLite database. It checks valid inserts and rejection of invalid relationships, duplicate natural keys, malformed timestamps, invalid system types, and invalid event severities.

These checks do not modify the committed database snapshot.

The script tests database constraints; it is not a substitute for the API retrieval integration tests.

## 12. Verified Day 2 Results

The following implementation results were verified for the Day 2 sample snapshot:

| Verification | Result |
|---|---|
| Telemetry batch ingestion | 7,500 accepted |
| Event batch ingestion | 210 accepted |
| Database telemetry count | 7,502 |
| Database event count | 212 |
| SQLite integrity check | `ok` |
| Foreign-key violations | 0 |
| Asset filtering | Verified |
| Location filtering | Verified |
| System-type filtering | Verified |
| Timestamp filtering | Verified |
| Combined filters | Verified |
| Pagination and page-boundary behavior | Verified |
| Inclusive start / exclusive end boundaries | Verified |
| API/OpenAPI documentation | Available |

Retrieval integration checks compared API results against independent read-only SQLite queries. Both telemetry and event retrieval were checked for individual filters, combined filters, pagination, and timestamp boundaries.

## 13. Operational and Security Notes

- The current API has no authentication or authorization layer.
- The documented startup command binds to `127.0.0.1`, restricting the demonstration server to the local machine.
- Do not expose the service to an external network or production environment without appropriate authentication, authorization, transport security, and deployment controls.
- The repository contains synthetic sample data, not live building telemetry.
- Database initialization and sample generation are separate from REST ingestion.

## 14. Project Deliverables

- Working FastAPI ingestion and retrieval service.
- Relational SQLite database with reference and operational tables.
- Reproducible synthetic telemetry and event sample data.
- Batch ingestion with transactional rollback behavior.
- Filtered retrieval with pagination.
- API documentation through OpenAPI and Swagger UI.
- Data-flow diagram.
- Database schema verification script.
- Populated database snapshot and recorded Day 2 verification results.
