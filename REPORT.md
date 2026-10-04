# Computer-Use Automation System — Technical Report

## 1. Architecture and Design

The system separates model-driven workflow discovery from deterministic workflow execution.

The main architecture is:

```text
Natural-Language Goal
        |
        v
Discovery Agent (LLM)
        |
        | observe → decide → act
        v
Surface Adapter
        |
        v
Playwright Browser
        |
        v
Legacy Banking Demo UI
        |
        | successful run
        v
Capability Artifact (JSON)
        |
        v
Replay Executor (No LLM Decisions)
        |
        v
Surface Adapter → Browser → UI
```

Supporting components provide:

- safety policy checks
- structured observability
- screenshots
- expected-state verification
- bounded retry
- structured error handling
- human handoff

The implementation intentionally focuses on one thin but complete vertical slice: looking up a member and returning the current savings balance.

### Separation of Discovery and Replay

Discovery is allowed to use an LLM because the system does not initially know how to operate the interface.

Replay is intentionally different.

Once a successful workflow has been discovered, the actions are persisted as structured data. Future executions use those saved actions rather than asking the model to rediscover the workflow.

This provides the core separation:

```text
Discovery:
Goal + UI observation + LLM decisions

Replay:
Artifact + runtime inputs + deterministic executor
```

---

## 2. Goal-Driven Discovery

The discovery agent implements an observe → decide → act loop.

For every iteration, the system obtains a structured observation of the current browser state.

The observation can include:

- URL
- page title
- visible body text
- form controls
- current input values
- buttons
- links
- identified elements

The observation, goal, and previously extracted values are supplied to the model.

The model is constrained to return a structured action rather than unrestricted prose.

Supported discovery decisions include:

```text
fill
click
extract
wait
complete
escalate
```

The agent validates the model decision before executing it.

### Genuine LLM Discovery

A genuine model-driven discovery run was completed for the goal:

```text
Look up member 12345 and return the current savings balance.
```

The observed sequence was:

```text
Observe Member ID input
        ↓
LLM chooses fill 12345
        ↓
Observe input now contains 12345
        ↓
LLM chooses Search Member
        ↓
Observe Member Details
        ↓
LLM identifies savings balance
        ↓
LLM chooses extraction
        ↓
Extract $4,280.31
        ↓
LLM completes the goal
```

The successful run generated the reusable capability:

```text
artifacts/discovered_lookup_member_balance.json
```

Screenshots from the discovery run are stored as evidence.

---

## 3. Capability Artifact

A central design goal was to make a successful computer-use workflow reusable.

The system represents the discovered workflow using Pydantic models and persists it as JSON.

The artifact includes:

- schema version
- capability name
- description
- typed inputs
- typed outputs
- ordered steps
- action type
- target
- parameterized values
- output names
- expected states
- retry count
- final checkpoint

Example structure:

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

### Parameterization

The discovery value is not permanently stored as a fixed member ID.

Instead, the artifact records:

```json
"value": "{{member_id}}"
```

During replay, the executor resolves the placeholder from runtime inputs.

This allows the workflow structure to be reused with values such as:

```text
12345
99999
55555
77777
```

without requiring a new LLM discovery for each value.

### Versioning

The artifact includes:

```json
"schema_version": "1.0"
```

This provides a basic version boundary for future artifact evolution.

A production implementation could extend this with capability revisions, migration rules, compatibility checks, and tenant-specific versions.

---

## 4. Deterministic Replay

The replay executor consumes the saved capability artifact and runtime inputs.

It does not ask an LLM to determine the next UI action.

The replay flow is:

```text
Load Capability
        ↓
Resolve Runtime Parameters
        ↓
Safety Check
        ↓
Execute Saved Action
        ↓
Verify Expected State
        ↓
Inspect Structured Outcome
        ↓
Continue / Retry / Escalate / Return
```

For example:

```powershell
python -m src.main replay --artifact artifacts/discovered_lookup_member_balance.json --member-id 12345
```

produces a successful result containing:

```text
$4,280.31
```

This demonstrates the core transition from model-driven discovery to deterministic execution.

---

## 5. Error Handling and Recovery

The system distinguishes different classes of outcomes rather than treating every unexpected UI state as the same failure.

The result taxonomy includes:

```text
success
business_outcome
recoverable_error
failure
```

### Known Business Outcome

Member ID:

```text
99999
```

produces:

```text
No member found.
```

The system maps this to:

```text
status: business_outcome
code: MEMBER_NOT_FOUND
```

This is intentionally not classified as a system crash because the UI behaved correctly and produced a valid domain outcome.

### Recoverable Transient Failure

Member ID:

```text
77777
```

produces a temporary system error on the initial request.

The system detects:

```text
Temporary system error.
```

and applies a bounded retry policy.

The retry budget is stored in the capability step:

```json
"retry_count": 1
```

The replay executor reads `step.retry_count` instead of hardcoding the retry count.

The recovery flow is:

```text
Search
   ↓
Temporary system error
   ↓
Read artifact retry_count
   ↓
Return to safe start state
   ↓
Re-enter runtime member ID
   ↓
Repeat search
   ↓
Successful member result
   ↓
Continue deterministic replay
```

For the demonstration, the retry succeeds and returns:

```text
$7,777.77
```

If the retry budget is exhausted, replay returns a structured `recoverable_error` result instead of retrying indefinitely.

### Hard Failure

Unexpected execution failures are converted into structured replay failures containing information such as:

- error code
- message
- failed step ID
- expected state
- observed page state

A screenshot is also attempted for failure evidence.

---

## 6. Safety

Safety is applied before saved actions are executed.

The replay executor invokes the safety policy for each step before interacting with the UI.

The implementation also performs URL safety checking when navigating during transient recovery.

The safety approach for this vertical slice includes:

- validating allowed actions
- validating navigation targets
- explicit handling of human-required states
- bounded retry
- separating secrets from artifacts
- avoiding uncontrolled model decisions during replay

API credentials are loaded from environment configuration.

They are not stored in capability artifacts.

A production implementation would extend this with stronger tenant-specific policies, action risk classification, authorization checks, secret management, and approval workflows.

---

## 7. Observability

The system records structured events throughout discovery and replay.

Events include information such as:

```text
run_id
step_id
action
target
retry attempt
retry budget
result status
error code
```

Example event categories include:

```text
discovery_started
discovery_observation
model_decision
extracted_value
replay_started
step_started
step_completed
recoverable_error_detected
retry_started
retry_succeeded
retry_exhausted
replay_finished
```

Screenshots are captured during important states, including discovery steps, recoverable errors, permission-denied states, handoff, and failures.

This makes it possible to reconstruct what the automation attempted and why a run succeeded or failed.

---

## 8. Human Handoff

The system includes a human-in-the-loop path for situations where automation should not continue independently.

Member ID:

```text
55555
```

produces:

```text
Permission denied.
```

This triggers a handoff.

The important design requirement is that the browser session remains alive.

The implemented flow is:

```text
Automation owns browser
        ↓
Permission denied
        ↓
Screenshot + intervention context captured
        ↓
Automation pauses
        ↓
Human operates the same browser session
        ↓
Human performs Manual Review
        ↓
Human returns control
        ↓
System verifies expected post-handoff state
```

The expected state is:

```text
Operator action completed.
```

If verified, the system returns:

```text
status: business_outcome
code: HUMAN_INTERVENTION_COMPLETED
```

This demonstrates explicit control ownership and same-session intervention.

### Current Handoff Boundary

In the current vertical slice, successful manual intervention produces a structured completion outcome.

The implementation does not claim to resume arbitrary later artifact steps after the handoff.

A production implementation could persist execution position and resume from the next appropriate step after control is returned.

---

## 9. Heterogeneous Legacy Surfaces

Browser-specific interaction is isolated behind `PlaywrightSurfaceAdapter`.

Higher-level components operate using concepts such as:

```text
fill
click
read
extract
wait
target
expected state
```

rather than spreading raw browser calls throughout the system.

Conceptually:

```text
Discovery / Replay
        |
        v
Common Surface Boundary
        |
        +---- Playwright Browser Adapter
        |
        +---- Future Desktop Adapter
        |
        +---- Future Remote/Legacy Adapter
```

Only the Playwright browser implementation is included in this assignment.

The purpose of the boundary is to provide a clear extension seam rather than pretending that all heterogeneous legacy surfaces have already been implemented.

---

## 10. Multi-Tenant Reuse

The capability artifact separates workflow structure from runtime data.

For example:

```text
Capability:
lookup_member_balance

Input:
member_id
```

This means the discovered interaction pattern can be reused with different runtime member IDs.

For a production multi-tenant system, the same concept could be extended with:

- tenant-specific capability registries
- capability versions
- tenant-specific safety policies
- tenant-specific target configuration
- authorization boundaries
- isolated secrets
- audit logs
- tenant-specific overrides

Those production features are outside the implemented vertical slice, but the artifact and adapter boundaries provide design seams for them.

---

## 11. Testing

The automated test suite currently validates core unit-level behavior.

Tests cover areas including:

- loading a saved capability artifact
- safety policy behavior
- runtime parameter substitution
- preservation of literal values
- handling `None`
- explicit failure for missing required parameters
- reuse with different runtime parameter values

The test suite is run using:

```powershell
python -m pytest -v
```

The final development run completed successfully with:

```text
8 passed
```

In addition to unit tests, the primary end-to-end scenarios were exercised manually through the real Playwright browser flow:

```text
12345 → successful balance lookup

99999 → MEMBER_NOT_FOUND

55555 → human handoff

77777 → transient error → bounded retry → success
```

---

## 12. Tradeoffs and Scope Decisions

The implementation intentionally prioritizes a complete vertical slice over breadth.

### Local Legacy UI

A deterministic local banking interface was used instead of automating a real banking website.

This makes failure conditions reproducible and avoids depending on external services while still exercising a real browser UI through Playwright.

### Semantic Locators

Semantic targets are preferred because they are easier to understand and can be more robust than arbitrary CSS selectors.

CSS remains available as a fallback when a specific identified element is needed.

### Discovery vs. Replay

LLM reasoning is used where flexibility is useful: discovering an unknown workflow.

Once discovered, replay favors deterministic execution.

This reduces cost and variability and makes execution easier to audit.

### Bounded Retry

Retries are explicit and stored in the capability artifact.

The executor does not retry forever and does not ask an LLM whether it should retry during deterministic replay.

### Human Intervention

Human intervention is explicit rather than allowing automation to guess its way through a permission or authorization boundary.

---

## 13. Known Limitations

The implementation has several intentional limitations.

### Browser Surface Only

Only the Playwright browser surface is implemented.

Other legacy surface types are represented as architectural extension points.

### Workflow-Specific Transient Recovery

The demonstrated transient recovery path is specialized to the member-search workflow.

A more general production executor would replay an artifact-defined recovery strategy or deterministic prefix rather than containing workflow-specific recovery behavior.

### Handoff Completion

After successful human review, the current implementation returns a structured `HUMAN_INTERVENTION_COMPLETED` outcome.

It does not continue through arbitrary later capability steps.

### Navigate Action

`navigate` exists in the action model, but generic replay execution of a saved `navigate` action is not currently implemented.

Navigation used by transient recovery goes through the surface adapter's URL safety checking.

### Test Breadth

The automated test suite focuses on core unit behavior.

The major browser scenarios were validated manually rather than all being represented as automated end-to-end tests.

### Production Concerns

The project is not intended to provide production-grade:

- authentication
- distributed orchestration
- tenant management
- secret infrastructure
- durable queues
- distributed locking
- capability migration
- large-scale monitoring

Those concerns were intentionally excluded to keep the assignment focused on the requested computer-use automation architecture.

---

## 14. What I Would Build Next

If continuing toward production, the next priorities would be:

1. generalize retry/recovery into artifact-defined recovery policies rather than workflow-specific code,
2. add automated end-to-end replay tests with mocked model boundaries,
3. implement execution resumption after human handoff,
4. support `navigate` as a validated replay action,
5. introduce capability revisioning and migration,
6. add tenant-scoped capability storage and policy configuration,
7. add richer action risk classification and approval controls,
8. implement additional surface adapters,
9. add durable run state for crash recovery,
10. add centralized metrics, tracing, and audit storage.

---

## 15. Summary

The project demonstrates the complete core lifecycle:

```text
Natural-Language Goal
        ↓
LLM Observes Live UI
        ↓
LLM Chooses UI Actions
        ↓
Successful Workflow
        ↓
Typed + Versioned Capability Artifact
        ↓
Runtime Parameterization
        ↓
Deterministic Replay Without Model Decisions
        ↓
Expected-State Verification
        ↓
Structured Success / Business Outcome /
Recovery / Human Handoff / Failure
```

The most important architectural decision is the separation between **intelligent discovery** and **deterministic replay**.

The LLM is used to discover how an unfamiliar interface should be operated. Once the workflow is known, that knowledge is persisted as a reusable capability artifact and executed deterministically.

The resulting vertical slice demonstrates reusable computer-use automation while retaining explicit safety boundaries, observability, bounded recovery, and human intervention.