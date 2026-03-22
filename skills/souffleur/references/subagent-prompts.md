<skill name="souffleur-subagent-prompts" version="1.2">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- watcher-prompt-normal
- watcher-prompt-heartbeat-only
- compact-watcher-prompt
- teammate-prompt
</sections>

<section id="overview">
<context>
# Reference: Subagent and Teammate Prompts

Contains verbatim prompts for the Souffleur's watcher and teammate monitors.
Use the normal watcher prompt when PID is known and heartbeat-only watcher prompt when PID is unresolved after Lethe recovery.
</context>
</section>

<section id="watcher-prompt-normal">
<core>
## Watcher Prompt (Normal Mode)

Launch with: `Task(subagent_type="general-purpose", model="opus", run_in_background=True)`

Substitute `{PID}`, `{SESSION_ID}`, and `{true|false}` with actual values before launching.

```
Poll the Conductor's liveness every ~60 seconds using comms-link.

Conductor PID: {PID}
Conductor session ID: {SESSION_ID}
Awaiting session ID: {true|false}
Watcher mode: normal

**Initial wait:** Sleep ~240 seconds before your first check.

**Each poll cycle:**
1. Update Souffleur heartbeat:
   UPDATE orchestration_tasks SET last_heartbeat = datetime('now')
   WHERE task_id = 'souffleur'
2. PID check: kill -0 {PID}
3. Heartbeat check: query task-00 last_heartbeat, calculate staleness
4. Task count: SELECT COUNT(*) FROM orchestration_tasks
5. Read task-00 state
6. (Only if awaiting_session_id = true) Check task-00 session_id

**EXIT immediately and report reason when:**
- PID is dead -> report: "CONDUCTOR_DEAD:pid"
- Heartbeat >240 seconds stale -> report: "CONDUCTOR_DEAD:heartbeat"
- task-00 state = complete -> report: "CONDUCTOR_COMPLETE"
- task-00 state = context_recovery -> report: "CONTEXT_RECOVERY"
- (Only if awaiting_session_id = true) task-00 session_id changed
  -> report: "SESSION_ID_FOUND:{new_session_id}"

Do NOT exit for any other reason. Do NOT loop after detecting a
trigger. EXIT immediately so the Souffleur is notified.

Report the current task count in your exit message for retry tracking.
```
</core>
</section>

<section id="watcher-prompt-heartbeat-only">
<core>
## Watcher Prompt (Heartbeat-Only Mode)

Launch with: `Task(subagent_type="general-purpose", model="opus", run_in_background=True)`

Substitute `{SESSION_ID}` and `{true|false}` with actual values before launching.

```
Poll the Conductor's liveness every ~60 seconds using comms-link.

Conductor session ID: {SESSION_ID}
Awaiting session ID: {true|false}
Watcher mode: heartbeat-only (PID unavailable)

**Initial wait:** Sleep ~240 seconds before your first check.

**Each poll cycle:**
1. Update Souffleur heartbeat:
   UPDATE orchestration_tasks SET last_heartbeat = datetime('now')
   WHERE task_id = 'souffleur'
2. Heartbeat check: query task-00 last_heartbeat, calculate staleness
3. Task count: SELECT COUNT(*) FROM orchestration_tasks
4. Read task-00 state
5. (Only if awaiting_session_id = true) Check task-00 session_id

**EXIT immediately and report reason when:**
- Heartbeat >240 seconds stale -> report: "CONDUCTOR_DEAD:heartbeat"
- task-00 state = complete -> report: "CONDUCTOR_COMPLETE"
- task-00 state = context_recovery -> report: "CONTEXT_RECOVERY"
- (Only if awaiting_session_id = true) task-00 session_id changed
  -> report: "SESSION_ID_FOUND:{new_session_id}"

Do NOT attempt PID checks in this mode.
Do NOT exit for any other reason.
Do NOT loop after detecting a trigger.

Report the current task count in your exit message for retry tracking.
```
</core>

<mandatory>
Heartbeat-only mode is degraded monitoring. It is only valid when Souffleur has already logged a warning about unresolved PID after recovery.
</mandatory>
</section>

<section id="compact-watcher-prompt">
<core>
## Compact Watcher Prompt

Launch with: `Task(subagent_type="general-purpose", model="opus", run_in_background=True)`

Substitute `{JSONL_PATH}` and `{BASELINE_LINES}` before launching.

```
Monitor JSONL for compact completion.

JSONL path: {JSONL_PATH}
Baseline lines: {BASELINE_LINES}
Timeout: 300 seconds

Every ~1 second:
1. Read lines with index > baseline
2. Parse each line as JSON (skip malformed lines)
3. If a line matches:
   {"type":"system","subtype":"compact_boundary"}
   then EXIT immediately and report:
   "COMPACT_COMPLETE"

If timeout expires before compact_boundary appears:
EXIT and report:
"COMPACT_TIMEOUT"

Do not emit additional messages after reporting a terminal result.
```
</core>

<mandatory>
Watcher must start before launching `claude --resume {SESSION_ID} \"/compact\"`.
</mandatory>
</section>

<section id="teammate-prompt">
<core>
## Teammate (Self-Monitor) Prompt

Launch with: `Task(subagent_type="general-purpose", model="opus")` (foreground, NOT background).

```
You are the Souffleur's self-monitor. Your job is to ensure the
background watcher is alive by checking the Souffleur's heartbeat.

**Initial wait:** Sleep ~360 seconds before your first check.

**Each cycle (~180 seconds):**
1. Query souffleur heartbeat:
   SELECT last_heartbeat,
     (julianday('now') - julianday(last_heartbeat)) * 86400 AS age_seconds
   FROM orchestration_tasks WHERE task_id = 'souffleur'
2. If age_seconds > 180: send message —
   "WATCHER_DEAD: Souffleur heartbeat is {age_seconds}s stale.
    Watcher has likely crashed. Relaunch needed."

**Rules:**
- NEVER exit. Keep checking and messaging until you are shut down.
- If heartbeat recovers (new watcher launched), resume silent monitoring.
- If heartbeat stays stale, keep sending every ~180 seconds.
```
</core>

<guidance>
The teammate runs in the foreground so its messages are delivered to the Souffleur main session. It never exits voluntarily — it is only killed by the main session after a new watcher has been confirmed launched.
</guidance>
</section>

</skill>
