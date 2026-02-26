---
name: souffleur
description: >-
  This skill should be used when the Conductor launches a watchdog session via
  "/souffleur PID:$PID SESSION_ID:$SESSION_ID". Monitors Conductor liveness
  using a three-layer monitoring architecture and recovers Conductor sessions
  via a provider router: prefer Lethe compaction when available, otherwise use
  claude_export relaunch.
version: 1.2
---

<skill name="souffleur" version="1.2">

<metadata>
type: skill
tier: 3
</metadata>

<sections>
- mandatory-rules
- identity
- bootstrap-protocol
- monitoring-architecture
- recovery-router
- recovery-providers
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
- The `awaiting_session_id` flag is `true` for exactly one watcher generation after each Conductor relaunch that needs session ID rediscovery
- New watcher launches BEFORE old teammate is killed — ordering invariant is non-negotiable
- All subagents and teammates must use `model="opus"` — sonnet is insufficient for orchestration
- Recovery providers are mutually exclusive per recovery event cycle
- Lethe launch failure before relaunch starts gets one retry, then fallback to claude_export provider
- No double-relaunch: once Lethe has started a new Conductor generation, do not execute claude_export for that cycle
- If Lethe succeeds but no PID is available after one discovery attempt, switch to heartbeat-only watcher mode and emit a warning message
- Default recovery prompt (when not provided) must begin with `/conductor --recovery-bootstrap`
- The Souffleur does not perform implementation work — it only watches, recovers, and exits
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
The Conductor has internal monitoring (a background watcher refreshing task-00's heartbeat), and Musicians detect Conductor death via a 540-second staleness threshold. But nothing external recovers the Conductor when it dies or requests context recovery. The Souffleur fills this gap.

The Souffleur's main session stays near-zero context by delegating all polling to a background subagent (watcher) and monitoring the watcher via a teammate (self-monitor). Recovery behavior is routed through provider references so compaction and relaunch mechanics can evolve without destabilizing monitoring logic.
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
| **Watcher** | Background subagent | Polls Conductor liveness and/or heartbeat, updates Souffleur heartbeat | ~60s (after ~240s initial wait) |
| **Teammate** | Foreground teammate | Monitors watcher via Souffleur heartbeat staleness | ~180s (after ~360s initial wait) |
| **Main session** | This session | Routes events, orchestrates recoveries | Event-driven (idle between events) |

The watcher's heartbeat update is both its primary side effect and the teammate's detection mechanism. If the watcher dies, the heartbeat goes stale, and the teammate detects it within one cycle (~180 seconds).
</core>

<mandatory>
Ordering invariant: new watcher launches BEFORE old teammate is killed. At least one monitoring entity must always be active.
</mandatory>

<reference path="references/monitoring-architecture.md" load="required">
Layer details: timing constants, normal vs heartbeat-only watcher modes, poll cycles, exit reasons, awaiting_session_id semantics.
</reference>

<reference path="references/subagent-prompts.md" load="required">
Verbatim prompts for normal watcher, heartbeat-only watcher, and teammate self-monitor.
</reference>

<guidance>
See examples/example-initial-launch.md for a complete bootstrap-to-WATCHING walkthrough.
</guidance>
</section>

<section id="recovery-router">
<core>
## Recovery Router

When the watcher exits with `CONTEXT_RECOVERY`, route recovery through provider selection.

### Router Inputs

- Internal state: `conductor_pid`, `conductor_session_id`, `relaunch_generation`, retry/task counters
- Optional payload from latest Souffleur instruction message:
  - `permission_mode`
  - `resume_prompt`

Payload format is tagged plaintext:

```text
CONTEXT_RECOVERY_PAYLOAD_V1
permission_mode: <value>
resume_prompt: <value>
```

Parsing rules:
- Must start with `CONTEXT_RECOVERY_PAYLOAD_V1` header line.
- `permission_mode` and `resume_prompt` are optional fields.
- Unknown fields are ignored.
- Missing fields resolve through provider defaults (see conductor-launch-prompts.md).
- Malformed or absent payload is non-fatal — recovery proceeds with defaults.

### Router Sequence

1. Resolve payload/defaults (see database-queries and provider references).
2. Run Lethe preflight (strict soft dependency check).
3. If preflight passes: set `active_recovery_provider = lethe`, run Lethe provider.
4. If preflight fails: set `active_recovery_provider = claude_export`, run claude_export provider.
5. Execute shared wrap-up sequence (clears `active_recovery_provider` on completion).

Lethe preflight is selection-time only. It does not commit to relaunch. `active_recovery_provider` enforces the no-double-relaunch rule: if Lethe starts a relaunch generation, the guard value prevents claude_export from executing in the same cycle even if Lethe reports a partial failure.
</core>

<reference path="references/database-queries.md" load="required">
Payload read queries and warning message templates.
</reference>

<reference path="references/lethe-recovery-provider.md" load="required">
Lethe provider procedure: preflight, launch attempts, completion contract, PID resolution, degraded mode.
</reference>

<reference path="references/claude-export-recovery-provider.md" load="required">
claude_export provider procedure: kill/export/size check/relaunch and default prompt+permission handling.
</reference>
</section>

<section id="recovery-providers">
<core>
## Recovery Providers

### Provider Summary

- **Lethe provider (preferred):** compacts and relaunches through a teammate workflow.
- **claude_export provider (fallback):** uses export transcript and relaunch prompt workflow.

### Common Provider Inputs

Both providers receive from the recovery router:
- `conductor_pid`, `conductor_session_id`, `relaunch_generation`
- `retry_count`, `last_task_count`, `current_task_count`
- Optional payload fields: `permission_mode`, `resume_prompt` (resolved from `CONTEXT_RECOVERY_PAYLOAD_V1` or defaults)

Retry and task counters are passed through to wrap-up for progress tracking. Providers themselves use PID, session ID, generation, and payload fields for their core operations.

### Shared Return Contract

Both providers return enough data for shared monitoring re-entry:
- `status`: success or failure
- `provider_used`: lethe or claude_export
- `new_conductor_pid`: PID when known, null when unresolved
- `session_id_mode`: `reused` or `rediscover`

Lethe provider can return `new_conductor_pid = null` when unavailable. In that case the router runs one PID discovery attempt. If still unresolved, the Souffleur transitions to heartbeat-only watcher mode and logs a warning.
</core>

<reference path="references/recovery-wrap-up.md" load="required">
Shared post-provider sequence: retry/task progress logic, watcher/teammate relaunch, WATCHING re-entry.
</reference>

<reference path="references/conductor-launch-prompts.md" load="required">
Default recovery prompt text and claude_export launch template fields.
</reference>

<guidance>
See examples/example-context-recovery.md for Lethe-primary flow and recovery-wrap-up integration.
</guidance>
</section>

<section id="event-loop">
<core>
## Event Loop & Lifecycle

### State Machine

```
VALIDATING → SETTLING → WATCHING → EXITED
                           ↑↓
                      (recovery cycles)
```

| State | Description | Transitions to |
|---|---|---|
| **VALIDATING** | Parsing and validating args | SETTLING (success) or VALIDATING (retry) or EXITED (3 failures) |
| **SETTLING** | Launching watcher + teammate, initial wait | WATCHING |
| **WATCHING** | Idle, waiting for events | WATCHING (recovery cycle) or EXITED (exhaustion/completion) |
| **EXITED** | Terminal | — |

### Event Routing (WATCHING State)

| Event | Exit Reason | Action |
|---|---|---|
| Watcher exits | `CONDUCTOR_DEAD:pid` | Recovery via claude_export provider |
| Watcher exits | `CONDUCTOR_DEAD:heartbeat` | Recovery via claude_export provider |
| Watcher exits | `SESSION_ID_FOUND:{id}` | Update session ID, new watcher (normal mode) |
| Watcher exits | `CONDUCTOR_COMPLETE` | Clean shutdown |
| Watcher exits | `CONTEXT_RECOVERY` | Recovery router (Lethe preferred, fallback to claude_export pre-relaunch only) |
| Teammate message | `WATCHER_DEAD` | New watcher (same mode), kill+relaunch teammate |

### Tracked State

Minimal state held in-session between cycles:

| Variable | Purpose | Updated when |
|---|---|---|
| `conductor_pid` | Current Conductor PID (or null in degraded mode) | On provider completion and PID discovery |
| `conductor_session_id` | Current Conductor session ID | On discovery or provider completion |
| `retry_count` | Consecutive deaths with no progress | On recovery (reset on new tasks) |
| `last_task_count` | Task count at last Conductor launch | On recovery |
| `awaiting_session_id` | True when session ID rediscovery is required | Provider-dependent in wrap-up |
| `relaunch_generation` | Counter for kitty window titles (S2, S3...) | On successful relaunch |
| `watcher_mode` | `normal` or `heartbeat-only` | On PID resolution outcome |
| `active_recovery_provider` | Double-relaunch guard: current provider or null (`lethe`/`claude_export`/null) | Set on provider entry, cleared on wrap-up completion |
</core>
</section>

<section id="exit-conditions">
<mandatory>
## Exit Conditions

The Souffleur exits in exactly three scenarios:

### 1. Arg Validation Failure (3 retries exhausted)
Set row to `exited`, insert terminal message, exit session.

### 2. Retry Exhaustion (3 consecutive Conductor deaths with no progress)
Set row to `error`, print alert with last recovery artifact path, exit session.

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

### Malformed or missing context-recovery payload
If no valid `CONTEXT_RECOVERY_PAYLOAD_V1` message is found, defaults apply and recovery proceeds. Payload parsing errors are non-fatal.

### Lethe relaunch succeeded but PID unavailable
The Souffleur attempts one PID discovery scan. If it still cannot resolve a PID, it switches to heartbeat-only watcher mode and emits a warning message. It does not execute a second recovery provider for the same cycle.

### Multiple watcher exits queued
Events are handled sequentially. Recovery steps are idempotent where possible. Stale queued `WATCHER_DEAD` messages are ignored when watcher heartbeat is already fresh.

### comms-link unavailable
Both watcher and teammate fail their queries. The watcher cannot update heartbeat, so teammate flags it. The Souffleur relaunches watcher/teammate layers until database access recovers.

### Souffleur context exhaustion
Unlikely due to near-zero context design. If it occurs, watcher/teammate can continue temporarily. Musicians' 540-second staleness detection remains the final safety net.
</context>

<guidance>
A validation script is available at scripts/validate-souffleur-state.sh for spot-checking database consistency. Run with optional Conductor PID argument.
</guidance>
</section>

</skill>
