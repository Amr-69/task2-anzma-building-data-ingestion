# AnzmaTech — Day 4: AI Analysis, Alerting & Recommendations

## 1. Project Overview

Day 4 extends the existing AnzmaTech building-data ingestion service and Day 3 operational dashboard by introducing automated fault detection, incident classification, evidence collection, AI-assisted explanations, and corrective-action recommendations.

The objective is to identify abnormal building-system telemetry, determine the severity of detected incidents, and provide explanations and recommended actions that can be traced to actual measurements in the database.

The implementation combines:

- Rule-based threshold detection.
- Statistical anomaly detection using a rolling robust Z-score.
- Incident severity classification and lifecycle management.
- Five simulated fault scenarios.
- Evidence collection from SQLite.
- AI-assisted possible-cause generation using a local Ollama model.
- Evidence validation and fallback explanations.
- A dashboard interface for reviewing incidents.

**Important:** All building records and fault scenarios are synthetic demonstration data. No live building systems are connected, and the application does not automatically control equipment.

## 2. Day 4 Requirements and Deliverables

| Requirement | Implementation |
|---|---|
| Threshold-based alert detection | Configurable warning and critical thresholds |
| Statistical anomaly detection | Rolling robust Z-score using median and MAD |
| Alert severity classification | Warning and Critical classification |
| Incident lifecycle | Incident opening, tracking, and resolution |
| At least five simulated fault scenarios | Five separate scenario databases |
| AI-generated incident explanations | Local Qwen model through Ollama |
| Evidence-based recommendations | Python-selected actions from a predefined catalog |
| Evidence traceability | Telemetry IDs, timestamps, and measured values |
| Dashboard integration | AI Monitoring Center added to the existing Day 3 dashboard |
| Automated testing | Alerting tests and existing dashboard tests |

## 3. System Architecture

The implementation is divided into five main stages.

### Stage 1 — Scenario Generation

The scenario generator creates five separate copies of the original building database.

Each copy contains a simulated fault affecting a specific asset and metric.

The original database remains unchanged.

### Stage 2 — Detection Engine

The detection engine reads telemetry from the selected database and analyzes each asset/metric time series.

It combines:

- Fixed threshold rules.
- Rolling statistical anomaly detection.
- Incident opening and resolution rules.
- Severity escalation.

The result is a structured incident containing the asset, metric, abnormal readings, detection reasons, severity, and timestamps.

### Stage 3 — Evidence Collection

When an incident is selected for explanation, the evidence module retrieves supporting information from the same scenario database.

This includes:

- Asset details.
- System and location.
- Metric and measurement unit.
- Configured thresholds.
- Normal readings before the incident.
- Key abnormal readings.
- Telemetry record IDs.
- Related events, if available.
- Candidate corrective actions.

Database access is read-only.

### Stage 4 — AI-Assisted Explanation

The explanation module constructs a factual incident summary using Python and sends the evidence packet to the local Qwen model.

The model is asked to generate possible causes, not to invent measurements or independently decide corrective actions.

The generated output is validated. If the model is unavailable or its response is invalid, a template fallback is used.

### Stage 5 — Dashboard

The existing Day 3 dashboard has been extended with a separate AI Monitoring Center.

The user can:

1. Open the dashboard.
2. Switch between Operations and AI Monitoring Center.
3. Select the baseline or one of the five scenarios.
4. View detected incidents.
5. Open an incident.
6. Review its evidence, possible causes, severity justification, and recommended actions.

The explanation is requested when an incident is opened, not for every incident during initial dashboard loading.

## 4. Simulated Fault Scenarios

Five fault scenarios were created using the original SQLite database as the baseline.

Each scenario changes only the selected asset and metric during a defined time window.

| Scenario | Asset | Metric | Simulated Fault | Target Value |
|---|---|---|---|---:|
| S1 — Cooling Failure | HVAC-AHU-02 | supply_air_temp | Supply-air temperature increases | 23.5°C |
| S2 — Fan Collapse | HVAC-AHU-01 | fan_speed_pct | Fan speed drops significantly | 8% |
| S3 — Packet Loss | NET-SW-2 | packet_loss_pct | Network packet loss increases | 4% |
| S4 — CPU Overload | NET-CORE-01 | cpu_load_pct | Sustained CPU load increases | 92% |
| S5 — Bandwidth Collapse | NET-SW-3 | bandwidth_mbps | Available bandwidth decreases | 30 Mbps |

### Scenario Time Windows

All timestamps below are UTC on 1 November 2026.

| Scenario | Start | End |
|---|---|---|
| S1 | 10:00 | 12:00 |
| S2 | 14:00 | 16:00 |
| S3 | 18:00 | 18:20 |
| S4 | 08:00 | 10:00 |
| S5 | 12:00 | 14:00 |

### Scenario Integrity

The scenario generator:

- Copies the baseline database.
- Updates only the targeted telemetry records.
- Uses a fixed random seed for reproducibility.
- Creates a JSON manifest for each scenario.
- Records the original and modified values.
- Calculates the baseline database hash before and after generation.

The manifests allow the injected changes to be traced to the corresponding telemetry records.

The five scenario databases are generated locally. They are not committed as database files; the generated directory contains the scenario manifests in Git.

This keeps the repository from storing five additional copies of the SQLite database.

## 5. Detection Engine

Main implementation:

`alerting/detection/engine.py`

Configuration:

`alerting/config.py`

The detection engine combines threshold-based detection and statistical anomaly detection.

### 5.1 Threshold-Based Detection

Each supported metric has:

- A detection direction.
- A warning threshold.
- A critical threshold.

For high-direction metrics, values above the thresholds are abnormal.

For low-direction metrics, values below the thresholds are abnormal.

Current configuration:

| Metric | Direction | Warning | Critical |
|---|---|---:|---:|
| supply_air_temp | High | 19.0 | 22.0 |
| fan_speed_pct | Low | 20.0 | 10.0 |
| zone_temp | High | 27.0 | 29.0 |
| zone_humidity_pct | High | 65.0 | 75.0 |
| bandwidth_mbps | Low | 150.0 | 50.0 |
| packet_loss_pct | High | 3.0 | 5.0 |
| cpu_load_pct | High | 90.0 | 95.0 |

Threshold values are project detection settings based on the observed baseline data and selected margins. They are not vendor specifications or validated operating limits for real equipment.

### 5.2 Statistical Anomaly Detection

The engine uses a rolling robust Z-score.

Instead of relying on the mean and standard deviation, it uses:

- The median of previous readings.
- The median absolute deviation (MAD).
- A minimum scale for metrics with very low variation.

The scale is calculated using:

`scale = max(1.4826 × MAD, minimum_metric_scale)`

The Z-score is then calculated relative to the rolling median.

The score is directional: a positive score represents movement toward the configured failure direction.

The implementation uses previous clean readings as the reference window. Threshold-violating readings are not added to the normal reference window.

### 5.3 Rolling Window Configuration

| Parameter | Value | Purpose |
|---|---:|---|
| WINDOW | 24 | Maximum number of previous readings |
| MIN_SAMPLES | 12 | Minimum readings required before calculating Z-score |
| Z_ANOMALY | 8.0 | Statistical anomaly threshold |
| Z_ESCALATE | 8.0 | Z-score escalation threshold |
| GAP_RESET_S | 900 seconds | Reset the rolling window after a gap longer than 15 minutes |

The telemetry interval is five minutes, so 24 readings represent approximately two hours.

The anomaly threshold was calibrated against the clean baseline. A lower initial threshold generated false incidents in the baseline dataset, so the final configuration uses 8.0.

### 5.4 Incident Opening and Resolution

| Parameter | Value | Meaning |
|---|---:|---|
| OPEN_AFTER | 2 | Two consecutive abnormal readings are required to open an incident |
| CLOSE_AFTER | 3 | Three consecutive normal readings are required to resolve an incident |
| SUSTAINED_READINGS | 6 | Six consecutive threshold violations can escalate a warning incident |

The engine records the abnormal readings that contribute to each incident.

Each incident contains its asset, metric, status, severity, timestamps, detection reasons, and supporting telemetry records.

### 5.5 Severity Classification

The engine classifies incidents as Warning or Critical.

Critical severity can result from:

- A critical threshold violation.
- A warning threshold violation combined with a sufficiently high directional Z-score.
- Sustained threshold violations that meet the configured escalation rule.

A statistical anomaly without a threshold violation is treated as Warning unless an applicable escalation condition is met.

For example, S4 reaches the CPU warning threshold of 90% but does not cross the critical threshold of 95%.

Its severity becomes Critical because the warning-level threshold violation is sustained for the required number of readings.

This distinction is important: a Critical incident does not necessarily mean that the configured critical threshold itself was crossed.

## 6. AI Explanation and Recommendation Layer

The AI implementation is located under:

`alerting/ai/`

The design separates factual information from AI-generated hypotheses.

### 6.1 Evidence Collection

File:

`alerting/ai/evidence.py`

This module builds an evidence packet for an incident.

It retrieves:

- Asset name and code.
- Asset type.
- System and location.
- Metric name and unit.
- Warning and critical thresholds.
- Incident severity and status.
- Detection reasons.
- Number of abnormal readings.
- Incident duration.
- Normal readings before the incident.
- First, worst, and last key readings.
- Telemetry IDs and timestamps.
- Related events within the surrounding time window.
- Candidate corrective actions.

The SQLite connection is configured as read-only.

The evidence packet is the factual input for the explanation layer.

### 6.2 Corrective-Action Catalog

File:

`alerting/ai/actions.py`

This module contains predefined candidate actions for each supported metric.

Examples:

| Metric | Example Action |
|---|---|
| supply_air_temp | Check the chilled-water valve and cooling coil |
| fan_speed_pct | Inspect the fan motor and variable-frequency drive |
| bandwidth_mbps | Check the uplink port, cable, and transceiver |
| packet_loss_pct | Inspect interface errors and duplex settings |
| cpu_load_pct | Identify processes or traffic flows driving CPU load |

Each action has a unique ID.

The action catalog prevents the LLM from inventing corrective actions that are not part of the approved candidate list.

**Important:** Python selects the recommended action IDs from the predefined catalog. The LLM does not independently select or approve the recommended actions.

### 6.3 Explanation Generation

File:

`alerting/ai/explain.py`

Configured model:

`qwen2.5:3b`

The model runs locally through Ollama.

API endpoint:

`http://localhost:11434/api/chat`

The Python explanation layer generates:

- Factual incident summary.
- Severity justification.
- Telemetry citations.
- Recommended action IDs.
- Evidence limitations.

The LLM receives the evidence packet and is asked to generate one or two possible causes.

The model is instructed to:

- Use only the supplied evidence.
- Mark each cause as a possibility.
- Reference only numerical values that already appear in the supplied evidence packet.
- Avoid inventing numbers, dates, measurements, asset identifiers, or telemetry IDs.
- Avoid recommending actions.
- Return the required JSON structure.

The validator permits a numerical value in an AI-generated possible cause only when that value is already present in the evidence packet, such as a configured threshold, key reading, Z-score, telemetry ID, or baseline statistic. Any unsupported numerical claim is rejected, and the system uses the template fallback.

### 6.4 Output Validation

File:

`alerting/ai/validator.py`

This module validates the structured explanation response.

It checks:

- Required fields.
- Correct data types.
- Telemetry citations against the available key readings.
- Recommended action IDs against the candidate-action catalog.
- Duplicate citations or actions.
- Possible-cause formatting.
- Unsupported numerical claims in generated prose.
- Numerical values in possible causes that do not exist in the evidence packet.

The purpose is to prevent unsupported model output from being treated as factual incident evidence.

This validation allows the LLM to refer to evidence-backed values, such as a configured threshold or an observed reading, while still rejecting invented measurements. The factual incident summary, telemetry citations, severity justification, and corrective-action selection remain generated by Python.

### 6.5 Fallback Behavior

If Ollama is unavailable or its response fails validation, the explanation layer returns a template possible cause.

The output identifies whether its possible causes came from the LLM or from the fallback template.

The factual incident information and Python-selected recommendations remain available.

A fallback response must not be described as a successful live-model explanation.

### 6.6 AI Design Summary

| Component | Responsibility |
|---|---|
| Python detection engine | Detects abnormal readings and classifies incidents |
| Python evidence module | Retrieves supporting measurements and context |
| Python explanation builder | Produces factual summary, severity justification, and citations |
| Qwen 2.5 3B | Suggests possible causes |
| Python validator | Checks the generated possible causes |
| Python action catalog | Provides candidate corrective actions |
| Python recommendation selection | Selects recommended action IDs |
| Template fallback | Supplies a safe alternative when AI output is unavailable or invalid |

The implementation is therefore an AI-assisted incident explanation system, not a system in which the LLM independently makes every operational decision.

## 7. Dashboard Integration

The Day 4 monitoring interface extends the existing Day 3 dashboard.

Dashboard URL:

`http://127.0.0.1:8000/dashboard`

The interface contains two pages:

### Operations

The original Day 3 dashboard remains available with:

- KPIs.
- System and building filters.
- Time-period filters.
- Historical trend charts.
- Equipment status.
- Equipment-health summary.

### AI Monitoring Center

The new monitoring page provides:

- Scenario selection.
- Incident count.
- Incident list.
- Severity and status.
- Asset and metric information.
- Incident details.
- Evidence readings.
- AI-generated possible causes.
- Recommended corrective actions.
- Evidence limitations.
- A visible AI source badge showing whether the explanation came from the live local model or the safe template fallback.
- AI generation time and validation status.

The Day 3 dashboard API and calculations remain separate from the Day 4 alert API.

The Day 4 scenario selector uses a fixed server-side allowlist. A client cannot submit an arbitrary database path.

### Live AI indicator

When an incident is opened, the dashboard displays one of two source badges:

| Badge | Meaning |
|---|---|
| `LIVE AI — qwen2.5:3b` | The possible causes were generated by the local Qwen model and passed evidence validation. |
| `SAFE FALLBACK — TEMPLATE` | Ollama was unavailable or the model response failed validation, so the system displayed a safe template explanation. |

The dashboard also shows the generation time and whether the AI response passed evidence validation. The factual incident summary, telemetry citations, severity justification, and corrective actions are always generated by Python from the database evidence.

## 8. API Endpoints

The Day 4 endpoints use the existing dashboard API prefix:

`/api/v1/dashboard`

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/alerts/scenarios` | Returns the baseline and available scenarios |
| GET | `/alerts?scenario=S1` | Returns incidents for a selected scenario |
| GET | `/alerts/{incident_index}?scenario=S1` | Returns detailed evidence and explanation |

Examples:

### List scenarios

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/dashboard/alerts/scenarios"
```

### Get baseline incidents

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/dashboard/alerts?scenario=baseline"
```

Expected result: zero incidents in the baseline dataset.

### Get S1 incidents

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/dashboard/alerts?scenario=S1"
```

Expected result: one incident affecting `HVAC-AHU-02` and `supply_air_temp`.

### Get an incident explanation

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/dashboard/alerts/0?scenario=S1"
```

This endpoint runs the detection engine for the selected scenario, builds the evidence packet, and requests the explanation.

The LLM request occurs when the detail endpoint is called.

Invalid scenario names are rejected. An incident index that does not exist in the selected scenario returns an error response.

## 9. Project File Structure and Responsibilities

### 9.1 Day 4 Alerting Files

| File | Responsibility |
|---|---|
| `alerting/__init__.py` | Marks the alerting directory as a Python package |
| `alerting/config.py` | Central configuration for metric thresholds, Z-score settings, and incident lifecycle parameters |
| `alerting/detection/__init__.py` | Marks the detection directory as a Python package |
| `alerting/detection/engine.py` | Reads telemetry, calculates directional robust Z-scores, detects threshold violations, groups abnormal readings into incidents, and assigns severity |
| `alerting/scenarios/__init__.py` | Marks the scenario directory as a Python package |
| `alerting/scenarios/build_scenarios.py` | Copies the baseline database, injects the five simulated faults, writes scenario manifests, and checks the baseline hash |
| `alerting/scenarios/generated/S1_manifest.json` | Records the telemetry modifications for the cooling-failure scenario |
| `alerting/scenarios/generated/S2_manifest.json` | Records the telemetry modifications for the fan-collapse scenario |
| `alerting/scenarios/generated/S3_manifest.json` | Records the telemetry modifications for the packet-loss scenario |
| `alerting/scenarios/generated/S4_manifest.json` | Records the telemetry modifications for the CPU-overload scenario |
| `alerting/scenarios/generated/S5_manifest.json` | Records the telemetry modifications for the bandwidth-collapse scenario |
| `alerting/ai/__init__.py` | Marks the AI directory as a Python package |
| `alerting/ai/actions.py` | Stores predefined metric-specific corrective actions and returns candidate actions |
| `alerting/ai/evidence.py` | Retrieves incident context and supporting telemetry from SQLite using read-only access |
| `alerting/ai/explain.py` | Builds deterministic factual explanations, calls Ollama for possible causes, validates evidence-backed numerical references, handles fallback behavior, and renders incident reports |
| `alerting/ai/validator.py` | Validates the structured explanation output against required fields, evidence citations, and candidate actions |
| `alerting/tests/__init__.py` | Marks the alerting tests directory as a Python package |
| `alerting/tests/test_alerting.py` | Tests detection, evidence construction, validation, and fallback behavior |

The scenario `.db` files are generated locally by `build_scenarios.py`. They are not committed as five additional database copies.

### 9.2 Dashboard Files

| File | Responsibility |
|---|---|
| `dashboard/__init__.py` | Dashboard package initialization and registration support |
| `dashboard/dashboard.py` | Registers dashboard routes, serves the dashboard page, exposes Day 3 endpoints, and provides Day 4 scenario and incident APIs |
| `dashboard/dashboard_core.py` | Existing Day 3 KPI calculations, database queries, filters, and equipment-health logic |
| `dashboard/static/index.html` | Defines the Operations and AI Monitoring Center page structure and styling, including the live-AI source badge styles |
| `dashboard/static/app.js` | Handles page navigation, Day 3 data loading, scenario selection, incident rendering, live-AI source indication, and incident-detail requests |
| `dashboard/static/charts.js` | Existing SVG chart-rendering utilities used by the Day 3 dashboard |

### 9.3 Existing Application and Supporting Files

| File | Responsibility |
|---|---|
| `main.py` | Creates the FastAPI application, registers existing application routes, and registers the dashboard |
| `db.py` | Provides the existing SQLite connection functionality |
| `schema.sql` | Defines the database tables, constraints, and indexes |
| `init_db.py` | Initializes the SQLite database |
| `seed_reference.py` | Inserts the reference data required by the application |
| `reference_data.py` | Defines the building, location, asset, metric, and event reference information |
| `generate_data.py` | Generates the original synthetic telemetry and event JSONL files |
| `data/anzma_building.db` | Original baseline SQLite database used by the application and scenario generator |
| `requirements.txt` | Lists the project's pinned direct application dependencies |
| `test_dashboard.py` | Existing Day 3 dashboard regression tests |
| `test_schema.py` | Existing database schema and constraint tests |
| `README_DAY3.md` | Documents the Day 3 dashboard implementation |
| `KPI_DEFINITIONS.md` | Documents the Day 3 KPI definitions and calculation methods |
| `DATA_FLOW.md` | Documents the original data-generation and ingestion flow |
| `README_DAY4.md` | This document: Day 4 architecture, implementation, commands, and verification |

## 10. Environment Setup

### Requirements

- Windows with PowerShell.
- Python 3.11 recommended.
- Git.
- Ollama for live AI-generated possible causes.
- The `qwen2.5:3b` model for the configured explanation service.

The application uses the existing pinned dependencies in `requirements.txt`.

### Clone the repository

```powershell
git clone [https://github.com/Amr-69/task2-anzma-building-data-ingestion.git](https://github.com/Amr-69/task2-anzma-building-data-ingestion.git)
cd task2-anzma-building-data-ingestion
git checkout task4
```

### Create and activate a virtual environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Install application dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Install testing dependencies

The project test environment also uses pytest and the HTTP client dependency required by the existing dashboard tests.

```powershell
python -m pip install pytest httpx
```

These testing dependencies were installed separately in the development environment and are not listed as application dependencies in `requirements.txt`.

### Set up Ollama

Install Ollama separately if it is not already installed.

Pull the configured model:

```powershell
ollama pull qwen2.5:3b
```

Ensure the Ollama service is running locally.

The explanation module connects to:

`http://localhost:11434/api/chat`

The detection engine and scenario generation do not require the LLM.

## 11. Generate the Five Scenario Databases

From the repository root, with the virtual environment activated:

```powershell
python -m alerting.scenarios.build_scenarios
```

The script creates:

```text
alerting/
└── scenarios/
    └── generated/
        ├── S1.db
        ├── S1_manifest.json
        ├── S2.db
        ├── S2_manifest.json
        ├── S3.db
        ├── S3_manifest.json
        ├── S4.db
        ├── S4_manifest.json
        ├── S5.db
        └── S5_manifest.json
```

The script prints the number of altered rows for each scenario and reports whether the baseline database remained unchanged.

**Important:** The original baseline database must exist before generating scenarios.

The scenario generator does not replace or modify the original baseline database.

If the scenario databases are missing after cloning the repository, run the generation command again.

## 12. Run the Detection Engine

The detection engine can be executed directly against the baseline and all five generated scenarios.

```powershell
python -m alerting.detection.engine
```

This uses the default baseline and S1–S5 database paths.

To analyze one specific database:

```powershell
python -m alerting.detection.engine alerting/scenarios/generated/S1.db
```

The output reports:

- Database name.
- Number of detected incidents.
- Severity.
- Asset and metric.
- Incident start and detection timestamps.
- Incident status.
- Last abnormal timestamp.
- Number of abnormal readings.
- Peak or minimum value.
- Detection reasons.

## 13. Run an AI Incident Explanation from the Command Line

The explanation module can be run independently of the dashboard.

First ensure the scenario databases have been generated and Ollama is running.

Example for S1:

```powershell
python -m alerting.ai.explain S1
```

Other scenarios:

```powershell
python -m alerting.ai.explain S2
python -m alerting.ai.explain S3
python -m alerting.ai.explain S4
python -m alerting.ai.explain S5
```

The output includes:

1. Incident summary.
2. Severity justification.
3. Asset and location details.
4. Thresholds.
5. Normal baseline statistics.
6. Key evidence readings.
7. Possible causes.
8. Recommended actions.
9. Evidence limitations.
10. Related events, if available.

The output identifies whether possible causes came from the LLM or from the template fallback.

## 14. Start the FastAPI Application and Dashboard

From the project root:

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### How to open the dashboard

1. Ensure the FastAPI application is running:

   ```powershell
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

2. Open a web browser.

3. Go to:

   [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)

4. Use **Operations Overview** to view the Day 3 KPIs, filters, trends, and equipment health.

5. Select **AI Monitoring Center** to review Day 4 incidents, evidence, AI-generated possible causes, and recommended corrective actions.

If the page does not open:

- Confirm that the Uvicorn command is still running and shows `Application startup complete.`
- Confirm that you are using `http://127.0.0.1:8000/dashboard`, not only `http://127.0.0.1:8000`.
- Refresh the browser with `Ctrl+F5`.
- Check the Uvicorn terminal for errors.

The dashboard is served by the existing FastAPI application. A separate dashboard server is not required.

Useful URLs:

| Resource | URL |
|---|---|
| Dashboard | [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard) |
| Swagger UI | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |
| OpenAPI specification | [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json) |

Stop the server using `Ctrl+C`.

## 15. Testing and Verification

### Run the complete automated test suite

```powershell
python -m pytest -v
```

The latest recorded test result during Day 4 development was:

- 46 tests passed.
- 38 subtests passed.

The suite includes the Day 4 alerting tests and existing Day 3 dashboard tests.

### Run only the Day 4 alerting tests

```powershell
python -m pytest .\alerting\tests\test_alerting.py -v
```

### Run only the Day 3 dashboard tests

```powershell
python -m pytest .\test_dashboard.py -v
```

### Compile the main Python files

```powershell
python -m py_compile main.py dashboard\dashboard.py dashboard\dashboard_core.py alerting\config.py alerting\detection\engine.py alerting\scenarios\build_scenarios.py alerting\ai\actions.py alerting\ai\evidence.py alerting\ai\explain.py alerting\ai\validator.py
```

### Verification evidence

The following results were recorded during Day 4 development:

| Verification | Result |
|---|---|
| Baseline detection | Zero incidents |
| S1 cooling failure | One expected incident |
| S2 fan collapse | One expected incident |
| S3 packet loss | One expected incident |
| S4 CPU overload | One expected incident |
| S5 bandwidth collapse | One expected incident |
| Scenario manifest integrity | All 105 modified telemetry records matched their scenario database records |
| Baseline database integrity | Baseline hash unchanged after scenario generation |
| Evidence citation traceability | 14 cited readings checked against the database with zero errors |
| Automated test suite | 46 tests and 38 subtests passed |
| Dashboard API checks | Scenario, incident, invalid-input, and Day 3 regression checks passed |
| Live AI explanation | S1 returned `source: llm`, zero validation errors, and Qwen-generated evidence-aligned possible causes |
| Dashboard live-AI indicator | Incident details display `LIVE AI — qwen2.5:3b`, generation time, and validation status |

### Important verification limitations

Automated tests validate the explanation structure, evidence references, and fallback behavior. They do not prove that live LLM explanations will always be accurate or consistent.

The incident-detail API success path was also tested with the Ollama call mocked.

Live model quality and browser rendering were checked manually. The S1 incident-detail endpoint returned a live Qwen explanation with `source: llm`, zero validation errors, and evidence-aligned possible causes. The dashboard displays the live-AI source badge, generation time, validation status, evidence readings, possible causes, and Python-selected corrective actions.

## 16. Known Limitations

1. **Synthetic data:** All telemetry and injected faults are simulated.
2. **Threshold calibration:** Thresholds are demonstration settings based on the existing baseline dataset, not validated equipment specifications.
3. **Statistical interpretation:** A Z-score anomaly indicates unusual behavior; it does not prove an equipment failure.
4. **Possible causes:** LLM-generated causes are hypotheses, not confirmed root causes.
5. **Corrective actions:** Recommendations are selected by Python from a predefined catalog. The LLM does not independently select or approve them.
6. **Local model dependency:** Live possible-cause generation depends on the local Ollama service and configured model.
7. **Fallback:** Template explanations are available when the model is unavailable or its output is invalid.
8. **No automatic control:** The system does not execute recommendations or control building equipment.
9. **No live integration:** The application is not connected to real building management or network monitoring systems.
10. **Local demonstration:** The application does not add authentication or authorization.

## 17. Git Branch and Delivery

Day 4 development branch:

`task4`

Repository:

[https://github.com/Amr-69/task2-anzma-building-data-ingestion](https://github.com/Amr-69/task2-anzma-building-data-ingestion)

The Day 4 detection engine, AI explanation layer, tests, and dashboard extension are committed on the `task4` branch.

To get the latest branch:

```powershell
git checkout task4
git pull origin task4
```

To check the working tree:

```powershell
git status
```

## 18. Day 4 Final Summary

Day 4 adds an evidence-based alerting and AI-assisted incident analysis layer to the existing building-data application.

The completed implementation includes:

- Configurable threshold detection.
- Rolling robust Z-score anomaly detection.
- Warning and Critical severity classification.
- Incident opening and resolution.
- Five reproducible simulated fault scenarios.
- Read-only evidence collection.
- Local Qwen-assisted possible-cause generation with evidence-backed numerical validation.
- Output validation and template fallback.
- Python-selected corrective-action recommendations.
- Integration into the existing Day 3 dashboard with a visible live-AI source indicator.
- Automated regression and alerting tests.

The central design principle is that incident explanations and recommendations must remain traceable to actual simulated measurements and configured detection rules.

**Day 4 Deliverable: AI Analysis, Alerting & Recommendations.**