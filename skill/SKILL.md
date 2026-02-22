---
name: souffleur
description: >-
  This skill should be used when the Conductor launches a watchdog session via
  "/souffleur PID:$PID SESSION_ID:$SESSION_ID". Monitors Conductor liveness
  using a three-layer monitoring architecture, relaunches the Conductor on
  crash or context exhaustion with conversation context recovery via claude-export.
version: 1.1
---

<skill name="souffleur" version="1.1">

<metadata>
type: skill
tier: 3
</metadata>

<sections>
- mandatory-rules
- identity
- bootstrap-protocol
- monitoring-architecture
- relaunch-protocol
- event-loop
- exit-conditions
- error-edge-cases
</sections>

<section id="mandatory-rules">
<mandatory>
# Souffleur — Conductor Watchdog

## Mandatory Rules

- Use comms-link MCP for ALL database operations — never use sqlite3 directly (WAL isolation)
- Every INSERT into orchestration_messages must include `message_type` — no NULL values
- Every state transition must include `last_heartbeat = datetime('now')`
- A watcher must always be running while the Souffleur is in WATCHING state
- The main session must stay near-zero context — delegate all polling to subagents
- Guard PID kills with `kill -0` before `kill` — never kill blindly
- The `awaiting_session_id` flag is `true` for exactly one watcher generation after each Conductor relaunch — never on initial launch or same-Conductor watcher relaunches
- New watcher launches BEFORE old teammate is killed — ordering invariant is non-negotiable
- All subagents and teammates must use `model="opus"` — sonnet is insufficient for orchestration
- The Souffleur does not perform implementation work — it only watches, relaunches, and exits
- The export file path is always passed to the new Conductor in the prompt — never inline the content
</mandatory>
</section>

<section id="identity">
<core>
## Identity & Role

The Souffleur is the external watchdog in the orchestration system. Named after the opera house prompter who watches from a booth and intervenes when something goes wrong.

**Invocation:** `/souffleur PID:$PID SESSION_ID:$SESSION_ID`

Launched by the Conductor at the start of an orchestration plan. Runs in its own kitty window as a full Claude Code session. The Conductor does not manage the Souffleur's lifecycle — the Souffleur outlives the Conductor by design.
</core>

<context>
The Conductor has internal monitoring (a background watcher refreshing task-00's heartbeat), and Musicians detect Conductor death via a 540-second staleness threshold. But nothing external relaunches the Conductor when it dies. The Souffleur fills this gap.

The Souffleur's main session stays near-zero context by delegating all polling to a background subagent (watcher) and monitoring the watcher via a teammate (self-monitor). This three-layer architecture ensures no blind windows while keeping the main session available to respond to events for the full duration of orchestration.
</context>
</section>

<section id="bootstrap-protocol">
<core>
## Bootstrap Protocol

On launch, parse `PID` and `SESSION_ID` from the invocation string and validate before settling.

Three checks in order:
1. PID check — `kill -0 $PID` confirms the Conductor is alive
2. Session ID check — verify sentinel file exists: `~/.claude/projects/*/$SESSION_ID*.jsonl`
3. Table check — query comms-link for `souffleur` row existence

On success: set state to `confirmed`, proceed to SETTLING.
On failure: set state to `error`, insert diagnostic, enter retry loop (max 3 attempts).
</core>

<reference path="references/bootstrap-validation.md" load="required">
Full validation procedure: arg parsing, check details, success/failure paths, retry loop, terminal failure.
</reference>
</section>

<section id="monitoring-architecture">
<core>
## Three-Layer Monitoring

Three layers ensure continuous monitoring with no blind windows:

| Layer | Type | Role | Cadence |
|---|---|---|---|
| **Watcher** | Background subagent | Polls Conductor liveness, updates Souffleur heartbeat | ~60s (after ~240s initial wait) |
| **Teammate** | Foreground teammate | Monitors watcher via Souffleur heartbeat staleness | ~180s (after ~360s initial wait) |
| **Main session** | This session | Routes events, orchestrates relaunches | Event-driven (idle between events) |

The watcher's heartbeat update is both its primary side effect and the teammate's detection mechanism. If the watcher dies, the heartbeat goes stale, and the teammate detects it within one cycle (~180 seconds).
</core>

<mandatory>
Ordering invariant: new watcher launches BEFORE old teammate is killed. At least one monitoring entity must always be active.
</mandatory>

<reference path="references/monitoring-architecture.md" load="required">
Layer details: timing constants, poll cycles, exit reasons, awaiting_session_id flag semantics.
</reference>

<reference path="references/subagent-prompts.md" load="required">
Verbatim prompts for watcher subagent and teammate self-monitor.
</reference>

<guidance>
See examples/example-initial-launch.md for a complete bootstrap-to-WATCHING walkthrough.
</guidance>
</section>

<section id="relaunch-protocol">
<core>
## Conductor Relaunch Protocol

When the watcher exits with `CONDUCTOR_DEAD` or `CONTEXT_RECOVERY`, execute the six-step relaunch sequence:

1. **Kill old Conductor** — guard with `kill -0` before `kill`
2. **Export conversation log** — `claude-export $SESSION_ID`
3. **Size check & truncation** — if export >800k chars, truncate to summary + tail
4. **Launch new Conductor** — Recovery Bootstrap Prompt with `{RECOVERY_REASON}` substitution
5. **Retry tracking** — increment counter, reset on progress (new tasks), exit at 3
6. **Relaunch monitoring** — new watcher (`awaiting_session_id=true`), kill+relaunch teammate
</core>

<reference path="references/conductor-relaunch.md" load="required">
Full 6-step procedure with bash commands, retry logic, and monitoring layer relaunch.
</reference>

<reference path="references/conductor-launch-prompts.md" load="required">
Recovery Bootstrap Prompt template with {RECOVERY_REASON} substitution table.
</reference>

<guidance>
See examples/example-conductor-relaunch.md for a complete death-detection-to-relaunch walkthrough.
</guidance>
</section>

<section id="event-loop">
<core>
## Event Loop & Lifecycle

### State Machine

```
VALIDATING → SETTLING → WATCHING → EXITED
                           ↑↓
                      (relaunch cycles)
```

| State | Description | Transitions to |
|---|---|---|
| **VALIDATING** | Parsing and validating args | SETTLING (success) or VALIDATING (retry) or EXITED (3 failures) |
| **SETTLING** | Launching watcher + teammate, initial wait | WATCHING |
| **WATCHING** | Idle, waiting for events | WATCHING (relaunch cycle) or EXITED (exhaustion/completion) |
| **EXITED** | Terminal | — |

### Event Routing (WATCHING State)

| Event | Exit Reason | Action |
|---|---|---|
| Watcher exits | `CONDUCTOR_DEAD:pid` | Relaunch sequence (see relaunch-protocol) |
| Watcher exits | `CONDUCTOR_DEAD:heartbeat` | Relaunch sequence (see relaunch-protocol) |
| Watcher exits | `SESSION_ID_FOUND:{id}` | Update session ID, new watcher (normal mode) |
| Watcher exits | `CONDUCTOR_COMPLETE` | Clean shutdown |
| Watcher exits | `CONTEXT_RECOVERY` | Relaunch sequence (see relaunch-protocol) |
| Teammate message | `WATCHER_DEAD` | New watcher (same mode), kill+relaunch teammate |

### Tracked State

Minimal state held in-session between cycles:

| Variable | Purpose | Updated when |
|---|---|---|
| `conductor_pid` | Current Conductor PID | On relaunch |
| `conductor_session_id` | Current Conductor session ID | On discovery (SESSION_ID_FOUND) |
| `retry_count` | Consecutive deaths with no progress | On relaunch (reset on new tasks) |
| `last_task_count` | Task count at last Conductor launch | On relaunch |
| `awaiting_session_id` | True after relaunch until discovered | On relaunch (set true), on discovery (set false) |
| `relaunch_generation` | Counter for kitty window titles (S2, S3...) | On relaunch |
</core>
</section>

<section id="exit-conditions">
<mandatory>
## Exit Conditions

The Souffleur exits in exactly three scenarios:

### 1. Arg Validation Failure (3 retries exhausted)
Set row to `exited`, insert terminal message, exit session.

### 2. Retry Exhaustion (3 consecutive Conductor deaths with no progress)
Set row to `error`, print alert with last export path, exit session.

### 3. Conductor Completes the Plan
Watcher exits with `CONDUCTOR_COMPLETE`. Kill teammate. Set row to `complete`. Exit cleanly.

No other scenario causes the Souffleur to exit. Watcher deaths and teammate messages result in relaunches, not exits.
</mandatory>
</section>

<section id="error-edge-cases">
<context>
## Error Recovery & Edge Cases

### Conductor dies during bootstrap
Arg validation includes `kill -0 $PID` — if the Conductor is already dead, the PID check fails and enters the retry loop. If it dies after validation but before the watcher launches, the watcher's initial wait (~240s) covers this — by first check, the heartbeat is already stale.

### Souffleur's own context exhaustion
Unlikely given the near-zero context design. If it happens, the watcher and teammate keep running independently. The teammate nags about a stale heartbeat. Without a Souffleur to relaunch, the system degrades to Musicians' 540-second staleness detection as the final safety net.

### Multiple watcher exits queued
Events are handled sequentially. The relaunch sequence is idempotent — killing an already-dead PID is a no-op, exporting the same session twice produces the same file, launching a new Conductor is always safe.

### comms-link unavailable
Both watcher and teammate fail their queries. The watcher can't update the heartbeat, so the teammate flags it. The Souffleur relaunches the watcher, which also fails. This loops until the database recovers — bounded by cheap cycles and transient WAL locks.

### Worst-case overlap (WATCHER_DEAD during mid-relaunch)
The Souffleur checks current state before acting. If a watcher is already running (heartbeat is fresh), the queued WATCHER_DEAD message is stale and no action is needed.
</context>

<guidance>
A validation script is available at scripts/validate-souffleur-state.sh for spot-checking database consistency. Run with optional Conductor PID argument.
</guidance>
</section>

</skill>
