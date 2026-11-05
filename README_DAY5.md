# Task 5 — Conversational AI Assistant for Smart Building Monitoring

Task 5 adds an AI-powered chat assistant to the existing smart-building
monitoring dashboard. The assistant helps users understand building status,
detected incidents, network problems, corrective actions, and energy
consumption using natural-language questions.

The assistant is read-only. It does not modify the database or change building
data. It only reads approved scenario databases and explains the results.

---

## Project Goal

The goal of Task 5 was to let a user ask questions such as:

```text
What is wrong with the building?
```

```text
Which device is most affected?
```

```text
Explain the most critical incident.
```

```text
What should the maintenance team check first?
```

The assistant understands the question, selects the correct internal tool,
reads the required data, and returns a clear answer.

It also supports follow-up questions using conversation memory. For example:

```text
What is wrong with the building?
```

```text
Which device is affected?
```

```text
Explain the most critical issue.
```

The assistant understands that “the most critical issue” refers to the previous
conversation.

---

## Main Features

### 1. Conversational AI Assistant

The assistant can answer questions about:

- Building status
- Recent faults and incidents
- CCTV availability
- Network issues
- Corrective-action priorities
- Energy-consumption changes
- Scenario-specific problems

### 2. Conversation Memory

The assistant remembers the last messages in the conversation. This allows
natural follow-up questions without repeating all details.

The frontend sends the last eight messages to the backend:

```javascript
history: chatHistory.slice(-8)
```

The backend passes this history to the AI model:

```python
history=req.history
```

### 3. Multiple AI Models

The assistant supports:

- OpenAI
- Anthropic Claude
- Google Gemini

The user can choose the model from the dashboard chat interface.

### 4. Scenario Selection

The user can select the data scenario before asking a question:

- `baseline`
- `S1` — Cooling failure
- `S2` — Fan collapse
- `S3` — Packet loss
- `S4` — CPU overload
- `S5` — Bandwidth collapse
- Existing validated custom scenario databases

Custom scenarios are accepted only if:

1. The scenario ID uses safe characters.
2. The database already exists in the generated-scenarios folder.
3. The database path stays inside the approved scenario directory.

This prevents unsafe file access such as:

```text
../../data/anzma_building.db
```

### 5. Time-Window Selection

The user can choose the analysis period:

- Last 1 hour
- Last 6 hours
- Last 12 hours
- Last 24 hours

The default time window is 24 hours.

### 6. Read-Only Database Access

The assistant uses read-only database connections. It cannot insert, update, or
delete records.

---

## How to Run the Project

### 1. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Start the FastAPI server

```powershell
uvicorn main:app --reload
```

The terminal should show:

```text
Uvicorn running on http://127.0.0.1:8000
```

### 3. Open the dashboard

Open this URL in the browser:

```text
http://127.0.0.1:8000/dashboard
```

### 4. Open the AI Assistant

Click the chat button in the dashboard.

Then select:

- AI model
- Scenario
- Time window

After that, write a question in natural language.

---

## Example Questions

The user does not need to use fixed questions. Any natural question can be used.

Examples:

```text
What is wrong with the building right now?
```

```text
Is there anything unusual in the network?
```

```text
Which equipment has the biggest problem?
```

```text
Explain the latest alert in simple words.
```

```text
What should the maintenance team check first?
```

```text
Are there any critical incidents in this scenario?
```

```text
What happened to the cooling system?
```

```text
Why is the network slow?
```

```text
Show me the most important issue.
```

---

## API Endpoint

### `POST /api/v1/assistant/chat`

This is the main endpoint used by the dashboard chat interface.

### Example request

```json
{
  "question": "What is wrong with the building?",
  "model": "openai",
  "building_id": 1,
  "scenario": "baseline",
  "hours": 24,
  "history": []
}
```

### Example follow-up request

```json
{
  "question": "Which device is most affected?",
  "model": "openai",
  "building_id": 1,
  "scenario": "S1",
  "hours": 24,
  "history": [
    {
      "role": "user",
      "content": "What is wrong with the building?"
    },
    {
      "role": "assistant",
      "content": "The cooling system shows an abnormal supply-air temperature."
    }
  ]
}
```

---

## Test Results

The Task 5 assistant tests are located in:

```text
tests/test_assistant_day5.py
```

Run them with:

```powershell
pytest tests\test_assistant_day5.py -v
```

Current result:

```text
tests/test_assistant_day5.py::test_chat_rejects_invalid_scenario PASSED
tests/test_assistant_day5.py::test_chat_rejects_invalid_time_window PASSED
tests/test_assistant_day5.py::test_chat_accepts_conversation_history PASSED
tests/test_assistant_day5.py::test_scenarios_endpoint_returns_required_scenarios PASSED

4 passed
```

The tests verify that:

- Unsafe or invalid scenario IDs are rejected.
- Invalid time windows are rejected.
- Conversation history is accepted by the assistant endpoint.
- All mandatory scenarios are available: `baseline`, `S1`, `S2`, `S3`, `S4`, and `S5`.

---

## Project Files and Their Jobs

### `main.py`

Creates the FastAPI application and registers the dashboard and assistant
routers.

It is the entry point for running the server:

```powershell
uvicorn main:app --reload
```

---

### `assistant/__init__.py`

Marks the `assistant` folder as a Python package.

---

### `assistant/schemas.py`

Defines the request and response models for the assistant API.

Main additions in Task 5:

```python
history: list[dict[str, str]] = Field(default_factory=list)
```

This field stores the previous user and assistant messages so the AI can
understand follow-up questions.

---

### `assistant/router.py`

Contains the assistant API endpoint:

```text
POST /api/v1/assistant/chat
```

Its main jobs are:

- Receive the user question
- Detect the question language
- Validate the selected model
- Resolve the selected scenario
- Pass the conversation history to the AI agent
- Return the assistant answer, selected tool, evidence, and metadata

Important line added in Task 5:

```python
history=req.history
```

This sends the previous chat messages to the AI model.

---

### `assistant/llm.py`

Contains the AI agent logic.

Its main jobs are:

- Connect to the selected AI provider
- Build the system prompt
- Send the user question and conversation history to the model
- Decide which internal tool should be used
- Call the correct read-only data function
- Return a clear final answer

It supports OpenAI, Anthropic, and Google Gemini.

---

### `assistant/language.py`

Detects the language of the user question.

This helps the assistant reply in the same language used by the user.

---

### `assistant/tools.py`

Contains general building-data tools used by the assistant.

Main functions:

- `get_building_status`
- `get_cctv_availability`
- `get_energy_consumption_change`

These functions read data from the approved database and return structured
results to the AI model.

---

### `assistant/incident_tools.py`

Contains incident and alert tools used by the assistant.

Main functions:

- `get_recent_faults`
- `get_network_issues`
- `get_corrective_priorities`

These functions help the assistant explain detected incidents, network issues,
and recommended corrective actions.

---

### `assistant/services.py`

Contains shared helper services for the assistant.

Main functions:

- `resolve_scenario`
- `resolve_time_range`

`resolve_scenario` checks that the selected scenario is valid and returns its
database path.

`resolve_time_range` calculates the requested time window, such as the last
24 hours, based on the dataset end time.

It also defines:

```python
class AssistantError(Exception)
```

This is used to return clear error messages for invalid requests.

---

### `dashboard/dashboard.py`

Contains the dashboard API, alert API, and scenario allowlist.

Task 5 changes:

- Keeps the fixed scenarios: `baseline`, `S1`, `S2`, `S3`, `S4`, and `S5`
- Adds safe support for existing custom scenario databases
- Validates custom scenario IDs before opening their database
- Prevents path-traversal attacks
- Returns a clear error if a custom scenario database does not exist

Important validation rule:

```python
SAFE_SCENARIO_ID = re.compile(r"^[A-Za-z0-9_-]+$")
```

This means a custom scenario ID can contain only:

- Letters
- Numbers
- Hyphens
- Underscores

---

### `dashboard/dashboard_core.py`

Contains the core dashboard database functions.

It is used by the assistant to open read-only database connections, read
filters, calculate KPIs, and query building telemetry.

---

### `dashboard/static/index.html`

Contains the main dashboard page structure.

Task 5 additions:

- AI Assistant chat button
- Chat panel
- Model selector
- Scenario selector
- Time-window selector
- Chat message area
- User input box
- Send button

---

### `dashboard/static/assistant_chat.js`

Contains the JavaScript logic for the AI chat interface.

Its main jobs are:

- Open and close the chat panel
- Store the conversation history
- Send the user question to `/api/v1/assistant/chat`
- Send the selected model, scenario, and time window
- Display the assistant response
- Handle loading and error states

Important conversation-memory line:

```javascript
var chatHistory = [];
```

The chat history is updated when the user sends a message and when the
assistant replies.

The frontend sends only the last eight messages:

```javascript
history: chatHistory.slice(-8)
```

---

### `dashboard/static/styles.css`

Contains the visual styling for the dashboard and chat interface.

---

### `tests/test_assistant_day5.py`

Contains automated tests for the Task 5 assistant.

It tests:

- Rejection of unsafe scenario IDs
- Rejection of invalid time windows
- Acceptance of conversation history
- Availability of all mandatory scenarios

---

### `DEMO_SCRIPT.md`

Contains the five-minute live product demonstration script and checklist.

It explains how to demonstrate:

- The dashboard
- The AI Assistant
- Natural-language questions
- Conversation memory
- Scenario analysis
- Custom scenarios
- Error handling

---

### `TECHNICAL_NOTES.md`

Contains the five-minute technical explanation.

It explains:

- The assistant architecture
- Request flow
- Conversation memory
- AI model support
- Scenario validation
- Read-only database access
- Internal tools
- Error handling
- Implemented files

---

### `alerting/scenarios/generated/`

Contains the generated scenario databases.

Examples:

```text
S1.db
S2.db
S3.db
S4.db
S5.db
```

A custom scenario database can also be placed here, for example:

```text
custom_test_1.db
```

Then it can be used in the assistant as:

```text
custom_test_1
```

---

## Git Commands Used in Task 5

### Check the current branch

```powershell
git branch
```

### Check changed files

```powershell
git status
```

### Add changed files

```powershell
git add .
```

### Commit the work

```powershell
git commit -m "Complete Task 5: conversational AI assistant with memory, scenarios, and custom scenario support"
```

### Push the Task 5 branch

```powershell
git push origin day5-conversational-ai
```

### Check the latest commits

```powershell
git log --oneline -5
```

---

## Security and Safety Rules

The assistant follows these rules:

- It never writes to the database.
- It only opens approved scenario databases.
- It validates scenario IDs before using them.
- It does not allow arbitrary file paths.
- It does not expose database credentials.
- It returns clear errors instead of exposing internal technical details.
- It uses the existing dashboard and alerting logic instead of duplicating it.

---

## Reflection: Improvements Required Before Production Deployment

Before deploying this assistant in a real production environment, several
improvements would be required.

First, authentication and authorization must be added. Currently, the assistant
is intended for an individual demonstration environment. In production, users
should log in, and their access should determine which buildings, systems, and
data they can query.

Second, the assistant should use a more robust evaluation process. Although the
tools return data-grounded results, the system should include automated tests
for tool selection, response accuracy, refusal behavior, and handling of
insufficient data.

Third, model responses should be monitored in production. The system should log
the selected model, tool used, response time, token usage, and user feedback so
that incorrect or unhelpful answers can be identified and improved.

Fourth, secrets and API keys must be managed securely. Local Ollama models reduce
dependency on external providers, but any external model integration should use
environment variables or a secure secret manager rather than hardcoded keys.

Fifth, the assistant should include stronger guardrails for ambiguous questions.
For example, if a user asks about a device or incident that cannot be identified,
the assistant should ask a clarifying question instead of guessing.

Finally, the user interface should support conversation reset, clearer citations
to the underlying data, and better handling of long conversations. These changes
would make the assistant safer, more transparent, and more reliable for
operational use.

---

## Summary

Task 5 converts the monitoring dashboard from a visual reporting tool into an
interactive AI assistant.

The user can now ask natural questions, choose a scenario and time window, and
receive clear explanations about building status, incidents, network problems,
corrective priorities, and energy consumption.

The assistant uses conversation memory, multiple AI providers, read-only
database tools, safe scenario validation, automated tests, and production
readiness planning.