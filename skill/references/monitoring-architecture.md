<skill name="souffleur-monitoring-architecture" version="1.0">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- layer-1-watcher
- watcher-exit-reasons
- awaiting-session-id
- layer-2-teammate
- layer-3-main-session
- ordering-invariant
</sections>

<section id="overview">
<context>
# Reference: Three-Layer Monitoring Architecture

Three layers ensure continuous monitoring with no blind windows. The watcher does the polling, the teammate watches the watcher, and the main session orchestrates both while staying near-zero context.
</context>
</section>

<section id="layer-1-watcher">
<core>
## Layer 1 — Watcher (Background Subagent)

The primary monitoring loop. Polls the Conductor's liveness and maintains the Souffleur's own heartbeat as a side effect.

Launch as a background subagent: `Task(subagent_type="general-purpose", model="opus", run_in_background=True)`.

**Timing:**
- **Initial wait:** ~240 seconds before first check (gives Conductor time to heartbeat after launch)
- **Poll cadence:** ~60 seconds

**Each poll cycle:**
1. Update Souffleur heartbeat:
   ```sql
   UPDATE orchestration_tasks SET last_heartbeat = datetime('now')
   WHERE task_id = 'souffleur';
   ```
2. PID liveness check: `kill -0 $PID`
3. Heartbeat staleness check: query `task-00` heartbeat, flag if >240 seconds stale:
   ```sql
   SELECT last_heartbeat,
     (julianday('now') - julianday(last_heartbeat)) * 86400 AS age_seconds
   FROM orchestration_tasks WHERE task_id = 'task-00';
   ```
4. Task count snapshot:
   ```sql
   SELECT COUNT(*) FROM orchestration_tasks;
   ```
5. (Only if `awaiting_session_id = true`) Check `task-00` session_id:
   ```sql
   SELECT session_id FROM orchestration_tasks WHERE task_id = 'task-00';
   ```

EXIT immediately on detection. Report which trigger fired.
</core>
</section>

<section id="watcher-exit-reasons">
<mandatory>
## Watcher Exit Reasons

The watcher exits for exactly four reasons:

| Exit reason | Trigger |
|---|---|
| `CONDUCTOR_DEAD:pid` | PID dead (`kill -0` returns non-zero) |
| `CONDUCTOR_DEAD:heartbeat` | task-00 heartbeat >240 seconds stale |
| `SESSION_ID_FOUND:{id}` | New session ID on task-00 (only when `awaiting_session_id = true`) |
| `CONDUCTOR_COMPLETE` | task-00 state = `complete` |

The watcher must NOT exit for any other reason. On detection, EXIT immediately — do not loop, do not send additional messages. Report the current task count in the exit message for retry tracking.
</mandatory>
</section>

<section id="awaiting-session-id">
<core>
## The `awaiting_session_id` Flag

This flag controls whether the watcher checks for a new session ID on task-00.

- **Set to `true`:** Only when the Souffleur launches a watcher after a Conductor relaunch. The new Conductor's session ID is unknown at launch time — the watcher discovers it by detecting a change in task-00's session_id.
- **Set to `false`:** On initial skill load and on watcher re-launches for the same Conductor (e.g., after a watcher crash detected by the teammate).

This prevents infinite exit loops. The flag is `true` for exactly one watcher generation after each Conductor relaunch. Once the session ID is discovered and the watcher exits with `SESSION_ID_FOUND`, the replacement watcher launches with `false`.
</core>
</section>

<section id="layer-2-teammate">
<core>
## Layer 2 — Teammate (Self-Monitor)

Watches the watcher by monitoring the Souffleur's heartbeat (which the watcher maintains as a side effect of its poll cycle).

Launch as a teammate: `Task(subagent_type="general-purpose", model="opus")` (foreground, NOT background).

**Timing:**
- **Initial wait:** ~360 seconds before first check (watcher needs its own ~240s initial wait + first poll cycle)
- **Poll cadence:** ~180 seconds (3x slower than watcher)

**Each cycle:**
```sql
SELECT last_heartbeat,
  (julianday('now') - julianday(last_heartbeat)) * 86400 AS age_seconds
FROM orchestration_tasks WHERE task_id = 'souffleur';
```

If `age_seconds > 180` (single missed watcher cycle): send message to Souffleur main session:
```
WATCHER_DEAD: Souffleur heartbeat is {age_seconds}s stale.
Watcher has likely crashed. Relaunch needed.
```
</core>

<mandatory>
The teammate NEVER exits on its own. It keeps nagging every ~180 seconds until the heartbeat refreshes. It is only killed by the Souffleur main session after a new watcher has been confirmed launched.

If the heartbeat recovers (new watcher launched), the teammate resumes silent monitoring. If it stays stale, the teammate keeps sending every ~180 seconds.
</mandatory>
</section>

<section id="layer-3-main-session">
<core>
## Layer 3 — Souffleur Main Session

Orchestrates the other two layers. Sits idle between events, consuming near-zero context.

**Two event types:**

| Event | Source | Meaning | Response |
|---|---|---|---|
| Watcher exits | Background subagent | See exit reason table | Route by exit reason |
| Teammate message | Teammate | Watcher is dead | Relaunch watcher, kill+relaunch teammate |

**Routing watcher exits:**
- `CONDUCTOR_DEAD` → Execute Conductor relaunch sequence (see conductor-relaunch.md)
- `SESSION_ID_FOUND:{id}` → Update `conductor_session_id`, launch new watcher (normal mode, `awaiting_session_id=false`)
- `CONDUCTOR_COMPLETE` → Clean shutdown (kill teammate, set souffleur row to `complete`, exit)

**Handling teammate messages:**
- `WATCHER_DEAD` → Launch new watcher (same mode as previous), kill old teammate, launch new teammate
</core>
</section>

<section id="ordering-invariant">
<mandatory>
## Ordering Invariant

New watcher launches BEFORE old teammate is killed. At least one monitoring entity must always be active. The sequence for any relaunch cycle is:

1. Launch new watcher
2. Kill old teammate
3. Launch new teammate

Never reverse steps 1 and 2. If the new watcher launch fails, the old teammate continues nagging — the system remains monitored.
</mandatory>
</section>

</skill>
