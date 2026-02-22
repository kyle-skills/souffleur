<skill name="souffleur-subagent-prompts" version="1.0">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- watcher-prompt
- teammate-prompt
</sections>

<section id="overview">
<context>
# Reference: Subagent & Teammate Prompts

Contains the verbatim prompts for the Souffleur's own subagents: the watcher and the teammate self-monitor. These prompts are carefully crafted and must not be paraphrased or modified. Conductor launch prompts are in conductor-launch-prompts.md.
</context>
</section>

<section id="watcher-prompt">
<core>
## Watcher Subagent Prompt

Launch with: `Task(subagent_type="general-purpose", model="opus", run_in_background=True)`

Substitute `{PID}`, `{SESSION_ID}`, and `{true|false}` with actual values before launching.

```
Poll the Conductor's liveness every ~60 seconds using comms-link.

Conductor PID: {PID}
Conductor session ID: {SESSION_ID}
Awaiting session ID: {true|false}

**Initial wait:** Sleep ~240 seconds before your first check.

**Each poll cycle:**
1. Update Souffleur heartbeat:
   UPDATE orchestration_tasks SET last_heartbeat = datetime('now')
   WHERE task_id = 'souffleur'
2. PID check: kill -0 {PID}
3. Heartbeat check: query task-00 last_heartbeat, calculate staleness
4. Task count: SELECT COUNT(*) FROM orchestration_tasks
5. (Only if awaiting_session_id = true) Check task-00 session_id

**EXIT immediately and report reason when:**
- PID is dead → report: "CONDUCTOR_DEAD:pid"
- Heartbeat >240 seconds stale → report: "CONDUCTOR_DEAD:heartbeat"
- task-00 state = complete → report: "CONDUCTOR_COMPLETE"
- task-00 state = context_recovery → report: "CONTEXT_RECOVERY"
- (Only if awaiting_session_id = true) task-00 session_id changed
  → report: "SESSION_ID_FOUND:{new_session_id}"

Do NOT exit for any other reason. Do NOT loop after detecting a
trigger. EXIT immediately so the Souffleur is notified.

Report the current task count in your exit message for retry tracking.
```
</core>

<guidance>
The watcher is the primary monitoring entity. Its heartbeat update (step 1) is how the teammate detects watcher liveness — this is a side effect, not the primary purpose. The watcher's `awaiting_session_id` flag is `true` for exactly one generation after each Conductor relaunch.
</guidance>
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
The teammate runs in the foreground so its messages are delivered to the Souffleur main session. It never exits voluntarily — it is only killed by the main session after a new watcher has been confirmed launched. This ensures the ordering invariant: new watcher launches BEFORE old teammate is killed.
</guidance>
</section>

</skill>
