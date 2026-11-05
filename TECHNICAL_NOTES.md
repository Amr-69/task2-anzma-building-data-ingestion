# Task 5 — Five-Minute Technical Explanation

## Architecture Overview

Task 5 adds a conversational AI layer on top of the existing smart-building
monitoring system.

The main flow is:

```text
Dashboard chat UI
        |
        v
POST /api/v1/assistant/chat
        |
        v
assistant/router.py
        |
        v
assistant/llm.py
        |
        v
Read-only tools and scenario databases
        |
        v
AI-generated answer
        |
        v
Dashboard chat UI
```

## Request Flow

1. The user writes a question in the dashboard chat.
2. The frontend sends the question, selected model, scenario, time window, and
   recent conversation history to the assistant API.
3. `assistant/router.py` validates the request and detects the language.
4. `assistant/llm.py` sends the question and history to the selected AI model.
5. The AI model chooses the correct internal tool.
6. The tool reads data from the approved scenario database.
7. The assistant returns a clear answer, the tool used, and supporting evidence.

## Conversation Memory

Conversation memory allows follow-up questions.

The frontend stores messages in:

```javascript
var chatHistory = [];
```

It sends only the last eight messages:

```javascript
history: chatHistory.slice(-8)
```

The request schema includes:

```python
history: list[dict[str, str]] = Field(default_factory=list)
```

The router passes it to the AI agent:

```python
history=req.history
```

This lets the assistant understand questions such as:

```text
Which device is most affected?
```

```text
Explain the most critical issue.
```

## AI Model Support

The assistant supports multiple providers:

- OpenAI
- Anthropic Claude
- Google Gemini

The selected model is passed from the frontend to the backend. The backend maps
the model key to the correct provider implementation.

## Scenario Handling

The system supports fixed scenarios:

```text
baseline
S1
S2
S3
S4
S5
```

It also supports existing custom scenario databases.

Custom scenario IDs are validated using:

```python
SAFE_SCENARIO_ID = re.compile(r"^[A-Za-z0-9_-]+$")
```

A custom scenario is accepted only when:

1. The ID contains only safe characters.
2. The database exists in `alerting/scenarios/generated/`.
3. The resolved path remains inside the approved scenario directory.

This prevents path-traversal attacks such as:

```text
../../data/anzma_building.db
```

## Read-Only Safety

The assistant does not write to the database.

It uses read-only connections through the existing dashboard services. It cannot
insert, update, or delete building data.

## Internal Tools

The assistant can use these tools:

| Tool | Purpose |
|---|---|
| `get_building_status` | Returns current building and equipment status |
| `get_recent_faults` | Returns recent detected incidents |
| `get_cctv_availability` | Returns CCTV camera availability |
| `get_network_issues` | Returns network-related issues |
| `get_corrective_priorities` | Returns recommended corrective actions |
| `get_energy_consumption_change` | Returns energy-consumption changes |

## Error Handling

The system returns clear errors for:

- Invalid scenario IDs
- Missing scenario databases
- Unsupported AI models
- Invalid time windows
- Database connection failures
- AI-provider failures

The goal is to avoid exposing internal technical details while still giving the
user a useful message.

## Files Implemented

| File | Purpose |
|---|---|
| `assistant/schemas.py` | Defines the chat request/response and conversation history |
| `assistant/router.py` | Handles `/api/v1/assistant/chat` |
| `assistant/llm.py` | Runs the AI agent and selects tools |
| `assistant/language.py` | Detects the user language |
| `assistant/tools.py` | Provides building, CCTV, and energy tools |
| `assistant/incident_tools.py` | Provides incident, network, and corrective-action tools |
| `assistant/services.py` | Validates scenarios and time ranges |
| `dashboard/dashboard.py` | Manages scenario allowlist and custom-scenario validation |
| `dashboard/static/index.html` | Contains the chat interface |
| `dashboard/static/assistant_chat.js` | Handles chat history and API requests |
| `README.md` | Documents Task 5 |
| `DEMO_SCRIPT.md` | Provides the live demonstration script |
| `TECHNICAL_NOTES.md` | Provides the technical explanation |

## Testing Performed

The following behavior was tested:

- Starting FastAPI successfully
- Opening the dashboard
- Opening the AI Assistant
- Asking baseline questions
- Asking follow-up questions using conversation memory
- Analyzing S1–S5 scenarios
- Using a validated custom scenario database
- Rejecting invalid or unsafe scenario IDs
- Committing and pushing the Task 5 branch