# Day 2 — Data Flow Diagram

## 1. Processing flow

```mermaid
flowchart TD
    A["Synthetic data generator<br/>generate_data.py"] --> B["JSONL sample files<br/>telemetry.jsonl and events.jsonl"]

    B --> C["HTTP client / batch submission<br/>Reads generated records and submits JSON"]
    C --> D["FastAPI batch endpoints<br/>POST /api/v1/telemetry/batch<br/>POST /api/v1/events/batch"]

    D --> E["Request validation<br/>Pydantic schemas"]
    E --> F["Reference and relationship validation"]
    R["Reference tables<br/>assets, locations, system types,<br/>metric types, event types"] --> F

    F --> G["SQLite transaction"]
    G --> H[("SQLite database<br/>telemetry_records and event_records")]

    H --> I["Retrieval endpoints<br/>GET /api/v1/telemetry<br/>GET /api/v1/events"]
    R --> I

    I --> J["Optional filters<br/>asset, location, system type,<br/>time range, limit and offset"]

    J --> K["JSON response<br/>Records and pagination metadata"]
```

The validation step checks that the asset, metric, and event type exist. Telemetry also checks that the asset type is allowed to emit that metric. It does not check that an event type belongs to the asset's system, and it does not check severity against the event type. The HTTP client in the diagram is not a file in this repository. The README section "Load a fresh database" is that step.

## 2. Database structure

How the tables relate. Boxes are tables. Arrows point from the child table to the parent table (foreign key direction).

```mermaid
erDiagram
    buildings ||--o{ locations : "has"
    locations ||--o{ assets : "contains"
    system_types ||--o{ assets : "classifies"
    assets ||--o{ telemetry_records : "measures"
    assets ||--o{ event_records : "emits"
    metric_types ||--o{ telemetry_records : "defines"
    event_types ||--o{ event_records : "defines"

    buildings {
        int building_id PK
        text name
    }

    locations {
        int location_id PK
        int building_id FK
        int floor
        text name
    }

    system_types {
        int system_type_id PK
        text code
    }

    assets {
        int asset_id PK
        text asset_code
        text name
        text asset_type
        int system_type_id FK
        int location_id FK
    }

    metric_types {
        int metric_id PK
        text name
        text unit
    }

    event_types {
        int event_type_id PK
        text name
    }

    telemetry_records {
        int telemetry_id PK
        int asset_id FK
        int metric_id FK
        text ts
        real value
    }

    event_records {
        int event_id PK
        int asset_id FK
        int event_type_id FK
        text ts
        text severity
        text details
    }
```

### Relationships in plain language

| Parent | Child | Meaning |
|---|---|---|
| `buildings` | `locations` | Each location belongs to one building |
| `locations` | `assets` | Each asset is installed in one location |
| `system_types` | `assets` | Each asset belongs to one system (HVAC, CCTV, …) |
| `assets` | `telemetry_records` | Each measurement is for one asset |
| `metric_types` | `telemetry_records` | Each measurement uses one metric definition |
| `assets` | `event_records` | Each event is for one asset |
| `event_types` | `event_records` | Each event uses one event type definition |

### Keys and constraints

- Unique natural key on telemetry: `(asset_id, metric_id, ts)`
- Unique natural key on events: `(asset_id, event_type_id, ts)`
- `severity` must be `info`, `warning`, or `critical`
- `system_types.code` must be one of: `HVAC`, `NETWORKING`, `ACCESS_CONTROL`, `CCTV`, `FIRE_ALARM`
- Foreign keys are enforced when the application opens the connection (`PRAGMA foreign_keys = ON`)

### What is not stored as a relationship

- Which metrics an asset type may emit is a Python rule in `reference_data.py`, not a database table
- Event type is not linked to system type in the schema; the API does not block cross-system event names
