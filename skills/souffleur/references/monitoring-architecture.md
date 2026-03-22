<skill name="souffleur-monitoring-architecture" version="1.2">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- layer-1-watcher
- watcher-modes
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

The primary monitoring loop. Polls the Conductor's liveness state and maintains the Souffleur heartbeat as a side effect.

Launch as a background subagent: `Task(subagent_type="general-purpose", model="opus", run_in_background=True)`.

**Timing:**
- **Initial wait:** ~240 seconds before first check (gives Conductor time to heartbeat after launch)
- **Poll cadence:** ~60 seconds

**Each poll cycle (all modes):**
1. Update Souffleur heartbeat:
   ```sql
   UPDATE orchestration_tasks SET last_heartbeat = datetime('now')
   WHERE task_id = 'souffleur';
   ```
2. Heartbeat staleness check on `task-00`:
   ```sql
   SELECT last_heartbeat,
     (julianday('now') - julianday(last_heartbeat)) * 86400 AS age_seconds
   FROM orchestration_tasks WHERE task_id = 'task-00';
   ```
3. Task count snapshot:
   ```sql
   SELECT COUNT(*) FROM orchestration_tasks;
   ```
4. Check `task-00` state for complete/context_recovery.
5. If `awaiting_session_id=true`, check `task-00.session_id`.

EXIT immediately on detection. Report which trigger fired.
</core>
</section>

<section id="watcher-modes">
<core>
## Watcher Modes

### Normal Mode

Used when `conductor_pid` is known.

Additional check each cycle:
```bash
kill -0 $PID
```

Can emit `CONDUCTOR_DEAD:pid` on PID failure.

### Heartbeat-Only Mode

Used when a relaunch succeeded but PID could not be resolved (after one discovery attempt).

Rules:
- Skip PID check entirely.
- Use heartbeat staleness + task state for liveness/recovery signals.
- Keep all other cycle behavior unchanged.

This mode is degraded but acceptable until a future recovery cycle restores a known PID.
</core>

<mandatory>
When in heartbeat-only mode, a warning must be present in session history/database so operators know PID checks are disabled.
</mandatory>
</section>

<section id="watcher-exit-reasons">
<mandatory>
## Watcher Exit Reasons

In normal mode, watcher exits for exactly five reasons:

| Exit reason | Trigger |
|---|---|
| `CONDUCTOR_DEAD:pid` | PID dead (`kill -0` returns non-zero) |
| `CONDUCTOR_DEAD:heartbeat` | task-00 heartbeat >240 seconds stale |
| `SESSION_ID_FOUND:{id}` | New session ID on task-00 (only when `awaiting_session_id = true`) |
| `CONDUCTOR_COMPLETE` | task-00 state = `complete` |
| `CONTEXT_RECOVERY` | task-00 state = `context_recovery` |

In heartbeat-only mode, `CONDUCTOR_DEAD:pid` is unavailable; all other reasons remain valid.

The watcher must NOT exit for any other reason. On detection, EXIT immediately — do not loop, do not send additional messages. Report the current task count in the exit message for retry tracking.
</mandatory>
</section>

<section id="awaiting-session-id">
<core>
## The `awaiting_session_id` Flag

This flag controls whether the watcher checks for a new session ID on task-00.

- **Set to `true`:** When provider return requires session ID rediscovery (`session_id_mode=rediscover`).
- **Set to `false`:** On initial skill load and when provider reports reused session ID (`session_id_mode=reused`).

This prevents infinite exit loops. When true, the flag should only be active for one watcher generation after relaunch.
</core>
</section>

<section id="layer-2-teammate">
<core>
## Layer 2 — Teammate (Self-Monitor)

Watches the watcher by monitoring the Souffleur heartbeat.

Launch as a teammate: `Task(subagent_type="general-purpose", model="opus")` (foreground, NOT background).

**Timing:**
- **Initial wait:** ~360 seconds before first check
- **Poll cadence:** ~180 seconds

**Each cycle:**
```sql
SELECT last_heartbeat,
  (julianday('now') - julianday(last_heartbeat)) * 86400 AS age_seconds
FROM orchestration_tasks WHERE task_id = 'souffleur';
```

If `age_seconds > 180`: send message to Souffleur main session:
```
WATCHER_DEAD: Souffleur heartbeat is {age_seconds}s stale.
Watcher has likely crashed. Relaunch needed.
```
</core>

<mandatory>
The teammate NEVER exits on its own. It keeps nagging every ~180 seconds until heartbeat refreshes. It is only killed by the Souffleur main session after a new watcher has been confirmed launched.
</mandatory>
</section>

<section id="layer-3-main-session">
<core>
## Layer 3 — Souffleur Main Session

Orchestrates the other two layers. Sits idle between events.

**Two event types:**

| Event | Source | Meaning | Response |
|---|---|---|---|
| Watcher exits | Background subagent | See exit reason table | Route by exit reason |
| Teammate message | Teammate | Watcher is dead | Relaunch watcher, kill+relaunch teammate |

**Routing watcher exits:**
- `CONDUCTOR_DEAD` -> route to claude_export provider first, then standard-compact escalation if export path is unavailable or gate-fails
- `CONTEXT_RECOVERY` -> route through recovery router (Lethe preferred, claude_export + standard-compact fallback chain)
- `SESSION_ID_FOUND:{id}` -> update `conductor_session_id`, launch new watcher (normal mode, `awaiting_session_id=false`)
- `CONDUCTOR_COMPLETE` -> clean shutdown (kill teammate, set Souffleur row to `complete`, exit)

**Handling teammate messages:**
- `WATCHER_DEAD` -> launch new watcher (same mode as previous), kill old teammate, launch new teammate
</core>
</section>

<section id="ordering-invariant">
<mandatory>
## Ordering Invariant

New watcher launches BEFORE old teammate is killed. At least one monitoring entity must always be active. The sequence for any relaunch cycle is:

1. Launch new watcher
2. Kill old teammate
3. Launch new teammate

Never reverse steps 1 and 2. If new watcher launch fails, old teammate continues nagging and the system remains monitored.
</mandatory>
</section>

</skill>
