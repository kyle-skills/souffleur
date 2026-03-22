<skill name="souffleur-example-standard-compact-fail-closed" version="1.0">

<metadata>
type: example
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- scenario
- first-attempt-timeout
- retry-timeout
- fail-closed
- summary
</sections>

<section id="scenario">
<context>
# Example: Standard Compact Retry Then Fail Closed

## Scenario

Souffleur enters standard compact provider (either direct fallback or export-gate
escalation). Compact watcher times out twice in the same recovery cycle.

Policy allows one retry only.
</context>
</section>

<section id="first-attempt-timeout">
<core>
## Step 1: First Compact Attempt Times Out

Attempt 1:
- baseline captured
- watcher launched
- compact session launched with `/compact`
- no `compact_boundary` within 300s

Watcher reports `COMPACT_TIMEOUT`.
Provider records attempt 1 failure and retries once.
</core>
</section>

<section id="retry-timeout">
<core>
## Step 2: Retry Also Times Out

Attempt 2 repeats the same sequence.
Again no compact completion signal appears before timeout.

Provider exits recovery path with terminal compact failure for this cycle.
</core>
</section>

<section id="fail-closed">
<mandatory>
## Step 3: Fail Closed

Souffleur executes fail-closed state transition:

```sql
UPDATE orchestration_tasks
SET state = 'error', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';

INSERT INTO orchestration_messages (task_id, from_session, message, message_type)
VALUES ('souffleur', '$CLAUDE_SESSION_ID',
    'SOUFFLEUR ERROR: Standard compact recovery failed after 2 attempts.
     Cycle failed closed to prevent unsafe relaunch.
     Manual intervention required.',
    'error');
```

No export fallback is executed after compact retry exhaustion.
No additional relaunch is attempted in this cycle.
</mandatory>
</section>

<section id="summary">
<context>
## Summary

Compact failure policy is deterministic:
- 1 retry allowed
- second failure -> fail closed

This prevents relaunch loops and unsafe multi-generation behavior when compact
completion cannot be validated.
</context>
</section>

</skill>
