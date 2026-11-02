CREATE TABLE buildings (
    building_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE locations (
    location_id INTEGER PRIMARY KEY,
    building_id INTEGER NOT NULL REFERENCES buildings(building_id),
    floor       INTEGER NOT NULL,
    name        TEXT NOT NULL,
    UNIQUE (building_id, name)
);

CREATE TABLE system_types (
    system_type_id INTEGER PRIMARY KEY,
    code           TEXT NOT NULL UNIQUE
        CHECK (code IN ('HVAC','NETWORKING','ACCESS_CONTROL','CCTV','FIRE_ALARM'))
);

CREATE TABLE assets (
    asset_id       INTEGER PRIMARY KEY,
    asset_code     TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    asset_type     TEXT NOT NULL,
    system_type_id INTEGER NOT NULL REFERENCES system_types(system_type_id),
    location_id    INTEGER NOT NULL REFERENCES locations(location_id)
);

CREATE TABLE metric_types (
    metric_id INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    unit      TEXT NOT NULL
);

CREATE TABLE event_types (
    event_type_id INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE
);

CREATE TABLE telemetry_records (
    telemetry_id INTEGER PRIMARY KEY,
    asset_id     INTEGER NOT NULL REFERENCES assets(asset_id),
    metric_id    INTEGER NOT NULL REFERENCES metric_types(metric_id),
    ts           TEXT NOT NULL
        CHECK (length(ts) = 20
           AND ts GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'
           AND datetime(ts) IS NOT NULL),
    value        REAL NOT NULL,
    UNIQUE (asset_id, metric_id, ts)
);

CREATE TABLE event_records (
    event_id      INTEGER PRIMARY KEY,
    asset_id      INTEGER NOT NULL REFERENCES assets(asset_id),
    event_type_id INTEGER NOT NULL REFERENCES event_types(event_type_id),
    ts            TEXT NOT NULL
        CHECK (length(ts) = 20
           AND ts GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'
           AND datetime(ts) IS NOT NULL),
    severity      TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
    details       TEXT,
    UNIQUE (asset_id, event_type_id, ts)
);

CREATE INDEX idx_assets_location    ON assets(location_id);
CREATE INDEX idx_assets_system_type ON assets(system_type_id);
CREATE INDEX idx_telemetry_ts       ON telemetry_records(ts);
CREATE INDEX idx_event_ts           ON event_records(ts);