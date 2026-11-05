# Task 5 — Five-Minute Live Product Demonstration

## Demonstration Checklist

Before starting:

- [ ] FastAPI server is running
- [ ] Dashboard opens successfully
- [ ] AI Assistant chat panel opens
- [ ] At least one AI model is selected
- [ ] Baseline scenario is available
- [ ] S1–S5 scenarios are available
- [ ] Conversation memory works
- [ ] Custom scenario support works

## Demonstration Steps

### Step 1 — Open the dashboard (30 seconds)

Open:

```text
http://127.0.0.1:8000/dashboard
```

Say:

> This is the smart-building monitoring dashboard. Task 5 adds an AI assistant
> that lets users ask natural-language questions about building status,
> incidents, network issues, and corrective actions.

### Step 2 — Open the AI Assistant (30 seconds)

Click the AI Assistant chat button.

Say:

> The user can choose the AI model, building scenario, and analysis time window.
> The assistant uses read-only database tools, so it cannot modify building data.

### Step 3 — Ask a general question (1 minute)

Select:

```text
Scenario: baseline
Time window: 24 hours
```

Type:

```text
What is wrong with the building right now?
```

Say:

> The assistant understands the question, selects the correct internal tool,
> reads the approved database, and explains the result in natural language.

### Step 4 — Test conversation memory (1 minute)

After the first answer, type:

```text
Which device is most affected?
```

Then type:

```text
Explain the most critical issue.
```

Say:

> The assistant remembers the recent conversation. It understands follow-up
> questions such as “which device”, “the most critical issue”, and “explain them”.
> The frontend sends the last eight messages to the backend.

### Step 5 — Test a fault scenario (1 minute)

Select:

```text
Scenario: S1 - Cooling failure
```

Type:

```text
What is happening with the cooling system?
```

Then type:

```text
What should the maintenance team check first?
```

Say:

> The assistant can analyze simulated fault scenarios and recommend corrective
> actions based on detected incidents.

### Step 6 — Test a custom scenario (30 seconds)

Select or enter:

```text
custom_test_1
```

Type:

```text
What is the main issue in this scenario?
```

Say:

> Custom scenarios are supported only when the database already exists in the
> generated-scenarios folder. The scenario ID is validated to prevent unsafe
> file access.

### Step 7 — Show error handling (30 seconds)

Enter an invalid scenario, for example:

```text
../../data/anzma_building.db
```

Or select a scenario database that does not exist.

Say:

> The system rejects unsafe or unknown scenarios. It does not allow arbitrary
> database paths, and it returns a clear error message.

## Closing Statement

> Task 5 turns the monitoring dashboard into an interactive AI assistant.
> Users can ask natural questions, receive evidence-based explanations, and
> understand the most important building issues without manually exploring
> charts or database records.