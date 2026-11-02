# Day 2 — Data Flow Diagram

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
