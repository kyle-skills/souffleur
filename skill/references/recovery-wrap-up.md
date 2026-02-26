<skill name="souffleur-recovery-wrap-up" version="1.0">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- retry-tracking
- session-id-mode
- watcher-and-teammate-relaunch
- watching-reentry
</sections>

<section id="overview">
<context>
# Reference: Recovery Wrap-Up

Shared post-provider steps run after either recovery provider returns.

This reference intentionally excludes provider-specific relaunch mechanics.
Provider outputs are treated as inputs here.
</context>
</section>

<section id="retry-tracking">
<mandatory>
## Retry Tracking

Track consecutive no-progress recoveries:

1. Compare `current_task_count` (watcher snapshot) with `last_task_count`.
2. If new tasks appeared: reset `retry_count` to 0.
3. If no new tasks: increment `retry_count`.
4. Update `last_task_count` to current snapshot.

If `retry_count` reaches 3:
- set Souffleur row to `error`
- print terminal alert
- exit session

```sql
UPDATE orchestration_tasks
SET state = 'error', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';
```
</mandatory>
</section>

<section id="session-id-mode">
<core>
## Session ID Mode Handling

Use provider return field `session_id_mode`:

- `rediscover`:
  - keep prior `conductor_session_id` until watcher reports `SESSION_ID_FOUND:{id}`
  - set `awaiting_session_id=true`

- `reused`:
  - set `conductor_session_id` from provider return
  - set `awaiting_session_id=false`

This keeps session discovery behavior aligned with provider semantics.
</core>
</section>

<section id="watcher-and-teammate-relaunch">
<mandatory>
## Relaunch Monitoring Layers

Select watcher mode from provider result:
- `watcher_mode=normal` if PID is available
- `watcher_mode=heartbeat-only` if PID unresolved

Then relaunch monitoring entities in strict order:
1. Launch new watcher (mode + awaiting_session_id according to state)
2. Kill old teammate
3. Launch new teammate

Never reverse steps 1 and 2.
</mandatory>

<guidance>
If watcher launch fails, do not kill old teammate. Keep existing monitoring alive and surface an error.
</guidance>
</section>

<section id="watching-reentry">
<core>
## WATCHING Re-Entry

On successful wrap-up:
- increment `relaunch_generation`
- clear `active_recovery_provider`
- return to WATCHING idle state

At re-entry, main session state should contain:
- current provider result summary
- updated retry/task counters
- watcher mode
- awaiting_session_id flag
</core>

<mandatory>
If `watcher_mode=heartbeat-only`, emit or preserve a warning in session history so operators know PID liveness checks are disabled.
</mandatory>
</section>

</skill>
