<skill name="souffleur-example-context-recovery" version="1.2">

<metadata>
type: example
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- scenario
- watcher-detection
- router-selection
- lethe-provider-run
- shared-wrap-up
- summary
</sections>

<section id="scenario">
<context>
# Example: Context Recovery (Lethe Primary Path)

## Scenario

The Conductor (PID 45231) has been running for 3 hours and context usage is high.
It writes handoff state, then sets task-00 state to `context_recovery`.

A payload message is also present for Souffleur:

```text
CONTEXT_RECOVERY_PAYLOAD_V1
permission_mode: acceptEdits
resume_prompt: /conductor --recovery-bootstrap

The session history was cleaned, review handoff documents and resume plan implementation.
```

The Souffleur watcher detects `context_recovery` and exits.
</context>
</section>

<section id="watcher-detection">
<core>
## Step 1: Watcher Detects Recovery Trigger

Watcher poll reads task-00 state:

```sql
SELECT state FROM orchestration_tasks WHERE task_id = 'task-00';
-- Returns: context_recovery
```

Watcher exits immediately:

```text
CONTEXT_RECOVERY
Task count: 14
```

Souffleur main session receives the watcher exit and enters recovery router.
</core>
</section>

<section id="router-selection">
<core>
## Step 2: Router Resolves Provider

Router reads latest payload from `orchestration_messages` and resolves defaults.

Router runs Lethe preflight:
- Lethe available in skill registry -> preflight pass
- Provider selected: `lethe`

No claude_export steps are executed in this cycle.
</core>
</section>

<section id="lethe-provider-run">
<core>
## Step 3: Lethe Provider Runs

Souffleur launches Lethe teammate in autonomous mode with:
- Conductor session ID: `abc12345-def6-7890-ghij-klmnopqrstuv`
- Conductor PID: `45231`
- permission: `acceptEdits`
- resume prompt from payload

Lethe teammate reports completion:

```text
LETHE_RECOVERY_COMPLETE
status: success
relaunch_started: true
new_conductor_pid: 52847
resumed_session_id: abc12345-def6-7890-ghij-klmnopqrstuv
notes: compacted and relaunched via --resume
```

Because PID is present, no discovery fallback is needed.
</core>
</section>

<section id="shared-wrap-up">
<core>
## Step 4: Shared Wrap-Up and Monitoring Relaunch

Retry tracking:
- `last_task_count` was 2, watcher reported 14 -> progress detected
- reset `retry_count` to 0
- update `last_task_count` to 14

Provider return includes `session_id_mode=reused`, so:
- `conductor_session_id` remains `abc12345-def6-7890-ghij-klmnopqrstuv`
- `awaiting_session_id=false`

Monitoring relaunch sequence:
1. Launch new watcher in normal mode (`PID=52847`, `awaiting_session_id=false`)
2. Kill old teammate
3. Launch new teammate

Transition: WATCHING -> WATCHING (same state, new generation)
</core>
</section>

<section id="summary">
<context>
## Summary

Lethe-primary context recovery flow:
1. Conductor sets `context_recovery` and writes payload
2. Watcher exits with `CONTEXT_RECOVERY`
3. Router selects Lethe provider after successful preflight
4. Lethe teammate compacts + relaunches Conductor
5. Shared wrap-up updates retry counters and relaunches monitoring layers
6. Souffleur returns to idle WATCHING state

This path preserves the no-double-relaunch rule: claude_export provider is not executed after Lethe has started relaunch for the cycle.
</context>
</section>

</skill>
