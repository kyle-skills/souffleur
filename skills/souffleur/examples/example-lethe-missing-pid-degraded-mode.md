<skill name="souffleur-example-lethe-missing-pid-degraded-mode" version="1.0">

<metadata>
type: example
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- scenario
- lethe-completion-without-pid
- single-pid-discovery-attempt
- degraded-mode-transition
- summary
</sections>

<section id="scenario">
<context>
# Example: Lethe Success Without PID (Heartbeat-Only Degraded Mode)

## Scenario

`CONTEXT_RECOVERY` routes to Lethe provider. Lethe completes successfully and relaunches Conductor, but completion message omits `new_conductor_pid`.

Souffleur must resolve PID once, then degrade if unresolved.
</context>
</section>

<section id="lethe-completion-without-pid">
<core>
## Step 1: Lethe Completion Contract

Teammate returns:

```text
LETHE_RECOVERY_COMPLETE
status: success
relaunch_started: true
new_conductor_pid:
resumed_session_id: abc12345-def6-7890-ghij-klmnopqrstuv
notes: relaunched, pid not captured by teammate
```

Because relaunch already started, claude_export fallback is prohibited for this cycle.
</core>
</section>

<section id="single-pid-discovery-attempt">
<core>
## Step 2: One PID Discovery Attempt

Souffleur attempts one process scan by session ID:

```bash
ps -eo pid,args | rg "claude.*(--resume|--session-id)[[:space:]]+abc12345-def6-7890-ghij-klmnopqrstuv"
```

Outcome in this scenario: no unambiguous PID match.

Souffleur does not retry discovery.
</core>
</section>

<section id="degraded-mode-transition">
<core>
## Step 3: Enter Heartbeat-Only Mode

Souffleur inserts warning message:

```sql
INSERT INTO orchestration_messages (task_id, from_session, message, message_type)
VALUES ('souffleur', '$CLAUDE_SESSION_ID',
    'SOUFFLEUR WARNING: Lethe recovery succeeded but Conductor PID could not be resolved.
     Switched watcher to heartbeat-only mode for this generation.
     PID liveness checks are temporarily disabled.',
    'warning');
```

Wrap-up then relaunches monitoring layers with:
- `watcher_mode=heartbeat-only`
- `session_id_mode=reused`
- `awaiting_session_id=false`

Watcher continues using heartbeat and task-state checks only.
</core>
</section>

<section id="summary">
<context>
## Summary

Missing-PID degraded recovery sequence:
1. Lethe relaunch succeeds but PID missing
2. Souffleur performs one discovery attempt
3. PID unresolved -> emit warning
4. relaunch watcher in heartbeat-only mode
5. continue WATCHING without executing claude_export fallback

This satisfies safety constraints:
- no double-relaunch
- uninterrupted monitoring
- explicit operator visibility via warning message
</context>
</section>

</skill>
