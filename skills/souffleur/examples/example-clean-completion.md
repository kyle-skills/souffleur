<skill name="souffleur-example-clean-completion" version="1.0">

<metadata>
type: example
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- scenario
- watcher-detection
- clean-shutdown
- summary
</sections>

<section id="scenario">
<context>
# Example: Clean Completion

## Scenario

The Conductor has finished executing the orchestration plan. All Musicians have completed their tasks. The Conductor sets task-00 state to `complete`. The Souffleur's watcher detects this and exits.
</context>
</section>

<section id="watcher-detection">
<core>
## Step 1: Watcher Detects Completion

The watcher's poll cycle checks task-00 state:

```sql
SELECT state FROM orchestration_tasks WHERE task_id = 'task-00';
-- Returns: complete
```

The watcher exits immediately with:
```
CONDUCTOR_COMPLETE
Task count: 12
```
</core>
</section>

<section id="clean-shutdown">
<core>
## Step 2: Clean Shutdown

The Souffleur main session receives the watcher exit and parses the exit reason as `CONDUCTOR_COMPLETE`.

### Kill Teammate
Terminate the self-monitor teammate. No more monitoring is needed.

### Update Souffleur Row
```sql
UPDATE orchestration_tasks
SET state = 'complete', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';
```

### Exit Session
The Souffleur exits cleanly. The orchestration is complete.

Transition: WATCHING → EXITED
</core>
</section>

<section id="summary">
<context>
## Summary

Clean completion workflow:
1. Conductor sets task-00 to `complete`
2. Watcher detects completion, exits with `CONDUCTOR_COMPLETE`
3. Souffleur kills teammate
4. Souffleur sets its own row to `complete`
5. Souffleur exits cleanly

This is the happy path — the orchestration plan ran to completion without any Conductor crashes. The Souffleur's total context usage across the entire session was near-zero: initial validation, two agent launches, and one clean shutdown.
</context>
</section>

</skill>
