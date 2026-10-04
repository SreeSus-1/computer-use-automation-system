# Computer-Use Automation System

A thin end-to-end computer-use automation system that uses an LLM to discover how to complete a task through a user interface, records the successful interaction as a reusable capability artifact, and later replays that capability deterministically without requiring LLM decisions.

This project was built as a take-home assignment for interface.ai.

## Overview

The system demonstrates two distinct execution modes:

1. **Discovery Mode** – an LLM observes a live browser UI, decides what action to take, executes the action through Playwright, and records successful interactions.
2. **Replay Mode** – a saved capability artifact is executed deterministically using Playwright without asking an LLM what to do.

The implemented vertical slice uses a local mock legacy banking interface.

The primary task is:

> Look up a member and return the current savings balance.

The implementation also demonstrates business outcomes, bounded transient-error recovery, structured failures, safety controls, observability, and human handoff.

---

## Architecture

```text
Natural-Language Goal
        |
        v
+---------------------+
|   Discovery Agent   |
|        LLM          |
+---------------------+
        |
        | observe / decide / act
        v
+---------------------+
|   Surface Adapter   |
|     Playwright      |
+---------------------+
        |
        v
+---------------------+
| Legacy Banking UI   |
|   Local Demo App    |
+---------------------+
        |
        | successful discovery
        v
+---------------------+
| Capability Artifact |
|        JSON         |
+---------------------+
        |
        v
+---------------------+
|   Replay Executor   |
|      NO LLM         |
+---------------------+
        |
        v
+---------------------+
|   Surface Adapter   |
|     Playwright      |
+---------------------+
        |
        v
+---------------------+
| Legacy Banking UI   |
+---------------------+
```

Safety policy checks, observability, screenshots, structured errors, retry behavior, and human handoff surround the execution flow.

---

## Key Features

### LLM-Guided Discovery

The discovery agent follows an observe → decide → act loop.

The browser surface is converted into a structured observation containing information such as:

- page URL
- page title
- visible text
- form inputs and current values
- buttons
- links
- identified page elements

The model chooses from a constrained set of actions such as:

- `fill`
- `click`
- `extract`
- `wait`
- `complete`
- `escalate`

Successful actions are recorded as reusable steps.

### Reusable Capability Artifact

A successful discovery run produces a typed and versioned JSON capability artifact.

Example:

```json
{
  "schema_version": "1.0",
  "name": "lookup_member_balance",
  "inputs": {
    "member_id": {
      "type": "string",
      "required": true
    }
  }
}
```

Runtime values are parameterized rather than permanently storing the discovery value.

For example:

```json
"value": "{{member_id}}"
```

This allows the same capability to be reused with different member IDs.

### Deterministic Replay

Replay executes the saved capability artifact directly.

The replay executor does not ask the LLM what action should happen next.

```text
Capability Artifact
        |
        v
Resolve Parameters
        |
        v
Safety Check
        |
        v
Execute Saved Step
        |
        v
Verify Expected State
        |
        v
Continue / Return Structured Outcome
```

### Locator Strategy

The Playwright surface adapter supports semantic and fallback targeting.

The preferred targeting approach is:

```text
role + accessible name
        ↓
label
        ↓
visible text
        ↓
CSS selector
```

This keeps artifacts more understandable and less dependent on brittle selectors where possible.

### Structured Outcomes

Replay distinguishes between different result categories:

```text
success
business_outcome
recoverable_error
failure
```

A known business outcome such as:

```text
No member found.
```

is returned as a structured business result rather than treated as a system crash.

### Artifact-Driven Retry

Transient recovery is bounded by the capability artifact.

For example:

```json
"retry_count": 1
```

The replay executor reads this value from the saved step.

The LLM does not decide the retry count during replay.

### Human Handoff

A permission-denied state can transfer control to a human operator while keeping the same browser session alive.

The implemented flow is:

```text
Automation owns browser
        |
        v
Permission denied
        |
        v
Automation pauses
        |
        v
Human receives control
        |
        v
Human performs manual review
        |
        v
Post-handoff state verified
        |
        v
Control returned
```

For the implemented vertical slice, successful manual intervention returns a structured `HUMAN_INTERVENTION_COMPLETED` business outcome.

### Safety

The project includes safety checks around execution.

Controls include:

- action policy validation
- URL safety checking
- bounded retry behavior
- explicit escalation for human-required conditions
- no API keys stored in capability artifacts

Secrets are loaded from environment configuration rather than hardcoded into artifacts.

### Observability

Execution produces structured logs containing information such as:

- run ID
- step ID
- action
- target
- retry events
- result status
- error code

Screenshots are also captured for discovery and important replay/error states.

---

## Demo Scenarios

The local banking application provides several deterministic scenarios.

| Member ID | Behavior |
|---|---|
| `12345` | Successful member lookup |
| `99999` | Member not found business outcome |
| `55555` | Permission denied / human review |
| `77777` | Transient failure followed by successful retry |

### Successful Lookup

Member:

```text
12345
```

Expected balance:

```text
$4,280.31
```

### Business Outcome

Member:

```text
99999
```

Expected structured outcome:

```text
MEMBER_NOT_FOUND
```

### Human Handoff

Member:

```text
55555
```

The UI produces a permission-denied condition requiring manual review.

The operator completes the manual action in the same browser session and returns control.

Expected structured outcome after successful intervention:

```text
HUMAN_INTERVENTION_COMPLETED
```

### Transient Recovery

Member:

```text
77777
```

The first lookup produces:

```text
Temporary system error.
```

The saved capability permits a bounded retry.

After recovery, the expected balance is:

```text
$7,777.77
```

---

## Project Structure

```text
interface_ai_assignment_starter/
|
├── artifacts/
│   ├── lookup_member_balance.json
│   └── discovered_lookup_member_balance.json
|
├── demo_app/
│   └── app.py
|
├── evidence/
│   ├── discovery/
│   └── replay/
|
├── src/
│   ├── agent/
│   │   ├── discovery.py
│   │   └── prompts.py
│   |
│   ├── artifact/
│   │   ├── models.py
│   │   └── storage.py
│   |
│   ├── escalation/
│   │   └── handoff.py
│   |
│   ├── observability/
│   │   └── logger.py
│   |
│   ├── replay/
│   │   └── executor.py
│   |
│   ├── safety/
│   │   └── policy.py
│   |
│   ├── surface/
│   │   └── playwright_adapter.py
│   |
│   ├── config.py
│   └── main.py
|
├── tests/
│   ├── test_artifact.py
│   ├── test_parameter_substitution.py
│   └── test_policy.py
|
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Create a Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

### 3. Install Playwright Chromium

```powershell
python -m playwright install chromium
```

### 4. Configure Environment Variables

Copy:

```text
.env.example
```

to:

```text
.env
```

Configure:

```text
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
TARGET_URL=http://127.0.0.1:8000
```

Do not commit `.env`.

---

## Running the Demo Application

Open a terminal with the virtual environment activated.

Run:

```powershell
python -m uvicorn demo_app.app:app --host 127.0.0.1 --port 8000
```

Keep this terminal running.

The demo application will be available at:

```text
http://127.0.0.1:8000
```

---

## Running LLM Discovery

Open another terminal, activate the virtual environment, and run the discovery command supported by `src.main`.

Use the goal:

```text
Look up member 12345 and return the current savings balance.
```

During a successful discovery, the agent:

1. observes the Member ID input,
2. fills `12345`,
3. observes the updated input value,
4. clicks `Search Member`,
5. observes the member details,
6. extracts the savings balance,
7. completes the goal.

The successful run generates:

```text
artifacts/discovered_lookup_member_balance.json
```

The recorded runtime member ID is parameterized as:

```text
{{member_id}}
```

Evidence screenshots are stored under:

```text
evidence/discovery/
```

---

## Running Deterministic Replay

Replay the artifact produced by discovery:

```powershell
python -m src.main replay --artifact artifacts/discovered_lookup_member_balance.json --member-id 12345
```

Expected result:

```json
{
  "status": "success",
  "outputs": {
    "savings_balance": "$4,280.31"
  }
}
```

Replay executes the saved capability steps without asking an LLM to decide the next action.

---

## Running the Business Outcome Scenario

```powershell
python -m src.main replay --artifact artifacts/discovered_lookup_member_balance.json --member-id 99999
```

Expected result includes:

```text
status: business_outcome
code: MEMBER_NOT_FOUND
```

This demonstrates that an expected domain outcome is distinguished from a system failure.

---

## Running the Transient Recovery Scenario

```powershell
python -m src.main replay --artifact artifacts/lookup_member_balance.json --member-id 77777
```

The first search intentionally returns a temporary system error.

Replay then uses the retry budget stored in the capability step and retries deterministically.

Expected final balance:

```text
$7,777.77
```

---

## Running the Human Handoff Scenario

```powershell
python -m src.main replay --artifact artifacts/lookup_member_balance.json --member-id 55555
```

When the permission-denied state appears:

1. automation pauses,
2. the same browser session remains open,
3. the operator performs the manual review action,
4. the operator returns control,
5. the system verifies the expected post-handoff state.

Expected result includes:

```text
status: business_outcome
code: HUMAN_INTERVENTION_COMPLETED
```

---

## Tests

Run:

```powershell
python -m pytest -v
```

The test suite covers the current core unit-level behavior, including:

- capability artifact loading
- safety policy behavior
- runtime parameter substitution
- literal values
- missing required parameters
- reusable parameter values

---

## Evidence

The repository includes evidence from discovery and replay runs.

A successful genuine LLM discovery run demonstrated:

```text
observe empty Member ID
        ↓
LLM chooses fill
        ↓
observe Member ID = 12345
        ↓
LLM chooses Search Member
        ↓
observe member details
        ↓
LLM chooses extraction
        ↓
extract $4,280.31
        ↓
LLM completes
```

The resulting artifact can then be replayed independently.

---

## Capability Model

The capability schema includes:

- schema version
- capability name
- description
- typed inputs
- typed outputs
- ordered steps
- action type
- target
- parameterized value
- output name
- expected state
- retry count
- final checkpoint

This separates discovery-time reasoning from replay-time execution.

---

## Heterogeneous Surface Design

Browser interaction is isolated behind a surface adapter.

The discovery agent and replay executor operate on capability actions rather than directly embedding Playwright logic throughout the system.

This provides a design seam for supporting additional legacy surfaces in the future.

For example:

```text
Capability / Agent
        |
        v
Surface Interface
     /     \
    v       v
Browser   Future Adapter
Adapter   (desktop/other)
```

Only the Playwright browser adapter is implemented in this vertical slice.

---

## Multi-Tenant Reuse

Capability artifacts separate runtime inputs from discovered workflow structure.

For example:

```text
Workflow:
lookup_member_balance

Runtime input:
member_id
```

A discovered workflow can therefore be reused with different runtime values without rediscovering the UI for every request.

A production multi-tenant implementation would additionally require tenant-specific authorization, capability storage/version management, policy configuration, audit boundaries, and secret isolation.

Those production concerns are outside the scope of this thin vertical slice.

---

## Known Limitations

This project intentionally prioritizes a small, working vertical slice over broad platform functionality.

Current limitations include:

- only the browser/Playwright surface is implemented
- transient recovery is demonstrated using the member-search workflow
- the human-handoff demonstration returns a structured completion outcome after manual review rather than continuing through arbitrary later artifact steps
- `navigate` exists in the action model but is not currently executed as a replay artifact action
- the local banking interface is intentionally a deterministic demonstration surface rather than a production banking application
- multi-tenant architecture is represented through design boundaries rather than a deployed tenant-management system

These are intentional scope boundaries rather than claims of production completeness.

---

## Technology Stack

- Python
- FastAPI
- Playwright
- Pydantic
- OpenAI API
- JSON capability artifacts
- pytest

---

## Design Principle

The central design principle is:

```text
Use intelligence to discover the workflow once.

Persist the successful workflow as data.

Replay that workflow deterministically when possible.

Escalate explicitly when automation should not proceed.
```

This keeps model-driven exploration separate from repeatable execution while preserving safety, observability, and human intervention boundaries.