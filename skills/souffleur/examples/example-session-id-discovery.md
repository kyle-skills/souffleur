<skill name="souffleur-example-session-id-discovery" version="1.0">

<metadata>
type: example
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- scenario
- watcher-detection
- session-id-update
- new-watcher
- summary
</sections>

<section id="scenario">
<context>
# Example: Session ID Discovery

## Scenario

The Souffleur has just relaunched the Conductor (S2). The new watcher is running with `awaiting_session_id = true`. After ~4 minutes, the new Conductor bootstraps, claims task-00, and updates its session_id. The watcher detects this change.
</context>
</section>

<section id="watcher-detection">
<core>
## Step 1: Watcher Detects New Session ID

The watcher's poll cycle includes the session ID check (because `awaiting_session_id = true`):

```sql
SELECT session_id FROM orchestration_tasks WHERE task_id = 'task-00';
-- Previous value: abc12345-def6-7890-ghij-klmnopqrstuv
-- New value: xyz98765-uvw4-3210-abcd-efghijklmnop
```

Session ID has changed. The watcher exits immediately with:
```
SESSION_ID_FOUND:xyz98765-uvw4-3210-abcd-efghijklmnop
Task count: 8
```
</core>
</section>

<section id="session-id-update">
<core>
## Step 2: Update In-Session State

The Souffleur main session receives the watcher exit and parses the exit reason:

- `conductor_session_id` = xyz98765-uvw4-3210-abcd-efghijklmnop
- `awaiting_session_id` = false
</core>
</section>

<section id="new-watcher">
<core>
## Step 3: Launch Normal-Mode Watcher

Launch a replacement watcher with the updated session ID and `awaiting_session_id = false`:

```python
Task("Monitor Conductor liveness", prompt="""
Poll the Conductor's liveness every ~60 seconds using comms-link.

Conductor PID: 52847
Conductor session ID: xyz98765-uvw4-3210-abcd-efghijklmnop
Awaiting session ID: false
...
""", subagent_type="general-purpose", model="opus", run_in_background=True)
```

The teammate is NOT killed or relaunched — it continues monitoring the Souffleur heartbeat as before. The watcher transition is seamless.

Return to idle (WATCHING state).
</core>
</section>

<section id="summary">
<context>
## Summary

Session ID discovery workflow:
1. Watcher running with `awaiting_session_id = true`
2. New Conductor bootstraps and updates task-00 session_id
3. Watcher detects change, exits with `SESSION_ID_FOUND:{id}`
4. Souffleur updates `conductor_session_id` and `awaiting_session_id = false`
5. New watcher launches in normal mode (no session ID monitoring)
6. Teammate continues unchanged

This is a lightweight event — no Conductor kill, no export, no retry tracking. Just a state update and watcher swap. The `awaiting_session_id` flag ensures this check only runs for exactly one watcher generation after each Conductor relaunch, preventing infinite exit loops.
</context>
</section>

</skill>
