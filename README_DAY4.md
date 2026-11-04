# AnzmaTech — Day 4: AI Analysis, Alerting & Recommendations

Day 4 extends the existing building-data service and Day 3 operational dashboard with simulated fault detection, incident evidence, AI-assisted explanations, and corrective-action recommendations.

**All records and fault scenarios are synthetic demonstration data. No live building systems are connected.**

## 1. Deliverables

| Requirement | Implementation |
|---|---|
| Threshold-based alert detection | Per-metric warning and critical thresholds in `alerting/config.py` |
| Statistical anomaly detection | Rolling robust Z-score using median and MAD |
| Incident severity and lifecycle | Warning/Critical classification, incident opening and resolution rules |
| Five simulated fault scenarios | S1–S5 scenario databases and manifests under `alerting/scenarios/generated/` |
| Evidence-backed explanations | Read-only telemetry evidence packet and cited readings |
| AI-assisted incident analysis | Local Ollama model `qwen2.5:3b` generates possible causes |
| Corrective actions | Metric-specific candidate-action catalog, selected by Python |
| Dashboard integration | Day 4 AI Monitoring Center added to the existing `/dashboard` page |
| Automated tests | `alerting/tests/test_alerting.py` plus existing dashboard tests |

The existing Day 3 Operations dashboard remains available. The AI Monitoring Center is a separate page within the same dashboard.

## 2. Run the application

From the repository root, activate the project virtual environment and start FastAPI:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open:

**http://127.0.0.1:8000/dashboard**

Use the page navigation to switch between **Operations** and **AI Monitoring Center**. In AI Monitoring Center, choose Baseline or one of S1–S5. Select an incident's View action to load its evidence and explanation.

Other useful endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/dashboard/alerts/scenarios` | Lists the allowlisted baseline and five scenarios |
| GET | `/api/v1/dashboard/alerts?scenario=S1` | Returns detected incidents for a selected scenario |
| GET | `/api/v1/dashboard/alerts/{incident_index}?scenario=S1` | Returns incident evidence, explanation, and actions |

The scenario selector accepts only server-configured scenario names. Scenario database paths are not supplied by the client.

## 3. Simulated fault scenarios

Each scenario is a copy of the baseline SQLite database with a targeted set of telemetry readings changed. The baseline database is not modified.

| Scenario | Asset | Metric | Injected condition | Window (UTC) |
|---|---|---|---|---|
| S1 — Cooling failure | `HVAC-AHU-02` | `supply_air_temp` | Supply-air temperature ramps to 23.5°C | 1 Nov 2026, 10:00–12:00 |
| S2 — Fan collapse | `HVAC-AHU-01` | `fan_speed_pct` | Fan speed drops to 8% | 1 Nov 2026, 14:00–16:00 |
| S3 — Packet loss | `NET-SW-2` | `packet_loss_pct` | Packet loss rises to 4% | 1 Nov 2026, 18:00–18:20 |
| S4 — CPU overload | `NET-CORE-01` | `cpu_load_pct` | CPU load rises to 92% | 1 Nov 2026, 08:00–10:00 |
| S5 — Bandwidth collapse | `NET-SW-3` | `bandwidth_mbps` | Bandwidth drops to 30 Mbps | 1 Nov 2026, 12:00–14:00 |

The scenario builder writes a manifest for each scenario. The manifests identify the modified telemetry records. A verification check matched all 105 modified records to their corresponding scenario database rows. The original baseline database hash remained unchanged.

## 4. Detection and incident rules

Detection combines configured metric thresholds with a rolling robust statistical anomaly check.

- **Thresholds:** Each configured metric has a direction (high or low) and warning/critical levels. These are project detection settings based on the observed sample and selected margins; they are not vendor specifications.
- **Robust Z-score:** Uses a rolling window of up to 24 readings, a minimum of 12 samples, and median/MAD-based scaling. A 15-minute data gap resets the rolling history.
- **Anomaly threshold:** The configured Z-score anomaly threshold is 8.0. The Z-score escalation threshold is also 8.0.
- **Incident opening:** Two abnormal readings are required to open an incident.
- **Incident resolution:** Three consecutive normal readings are required to resolve an incident.
- **Sustained escalation:** A warning incident can escalate to Critical after six or more sustained threshold-violating readings, even if no individual reading crosses the configured critical threshold.

Severity depends on the configured threshold direction, critical threshold crossings, statistical anomaly escalation, and sustained threshold violations. For example, S4 reaches the CPU warning threshold (90%) but not its critical threshold (95%); its incident escalates due to sustained warning-level readings.

These are deterministic configured rules. They should not be interpreted as a universal safety standard for real equipment.

## 5. Evidence and AI explanation design

The explanation pipeline is deliberately split between deterministic Python logic and the local language model.

**Python produces and validates the factual parts:**

- Asset, metric, location, incident severity, and configured thresholds.
- Key telemetry readings with their database telemetry IDs, values, timestamps, and statistical context.
- References to related events when available.
- A factual incident summary and severity justification.
- Recommended action IDs selected from the metric-specific candidate-action catalog.
- Evidence limitations where the available data is insufficient.

**Local Ollama model contribution:**

- The configured model is `qwen2.5:3b`.
- The model is asked to generate possible causes from the supplied evidence and candidate context.
- Possible causes are explicitly marked as hypotheses, not confirmed root causes.
- The response is checked against the expected structure and evidence constraints.
- If Ollama is unavailable or its response is invalid, the pipeline uses a visible template fallback.

**Important limitation:** The LLM does not independently select the corrective actions. Python selects recommended action IDs from the predefined metric-specific action catalog. The LLM contributes possible causes; Python supplies the factual summary, severity justification, evidence citations, and selected recommendations. This is an AI-assisted explanation, not a fully LLM-generated incident report.

The dashboard loads incident explanations when an incident is opened, rather than calling the LLM for every incident during initial page load.

### Local model setup

Install and run Ollama separately, then make the configured model available:

```powershell
ollama pull qwen2.5:3b
```

The explanation service calls the local Ollama API at `http://localhost:11434/api/chat`. If the local model service is unavailable, the application can return its template fallback. A fallback response should not be reported as a successful live-model explanation.

## 6. Run the tests

From the repository root with the virtual environment active:

```powershell
python -m pytest -v
```

The latest recorded automated result for the Day 4 branch was:

- **46 tests passed**
- **38 subtests passed**

The Day 4 alerting tests cover detection rules, evidence construction, output validation, and fallback behavior. The existing dashboard tests continue to cover the Day 3 dashboard behavior.

The incident-detail API checks also verified the scenario list, expected incidents for S1–S5, invalid-scenario rejection, invalid-incident rejection, evidence and recommendation fields, continued Day 3 endpoint behavior, and baseline database integrity. The detail endpoint's LLM success-path contract was checked with the Ollama call mocked.

**Verification limitation:** Automated tests mock Ollama for relevant success/failure paths. They do not establish consistent explanation quality across live model responses. Browser navigation and visual rendering should also be manually checked before claiming full UI verification.

## 7. Important files

| Path | Responsibility |
|---|---|
| `alerting/config.py` | Metric thresholds and detection parameters |
| `alerting/detection/engine.py` | Threshold and rolling robust Z-score detection; incident lifecycle |
| `alerting/scenarios/build_scenarios.py` | Creates the five simulated scenario databases and manifests |
| `alerting/scenarios/generated/` | Generated scenario databases and manifests |
| `alerting/ai/evidence.py` | Builds read-only, telemetry-backed incident evidence |
| `alerting/ai/actions.py` | Metric-specific candidate corrective actions |
| `alerting/ai/explain.py` | Deterministic explanation fields and local Ollama integration |
| `alerting/ai/validator.py` | Validates model output against evidence and candidate IDs |
| `alerting/tests/test_alerting.py` | Day 4 automated tests |
| `dashboard/dashboard.py` | Existing dashboard routes and Day 4 alert API routes |
| `dashboard/static/index.html` | Operations and AI Monitoring Center page structure |
| `dashboard/static/app.js` | Dashboard navigation, data loading, and interactions |
| `README_DAY3.md` | Day 3 dashboard implementation and verification |
| `KPI_DEFINITIONS.md` | Day 3 KPI definitions |

## 8. Scope and limitations

- All scenario readings are simulated. They are not live telemetry.
- Detection thresholds are configured for this demonstration dataset and are not validated operating limits for real equipment.
- Statistical anomaly scores are signals for investigation, not proof of equipment failure.
- Possible causes are hypotheses, not confirmed root causes.
- Recommended actions come from a predefined catalog and are selected by Python; they are not generated or independently approved by the LLM.
- The application does not automatically control equipment or execute corrective actions.
- Local Ollama availability and response quality affect whether model-generated possible causes are returned; a template fallback is available.
- The service is intended for local demonstration and does not add authentication or authorization.

---

**Day 4 Deliverable: AI Analysis, Alerting & Recommendations**
