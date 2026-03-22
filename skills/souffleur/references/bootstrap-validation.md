<skill name="souffleur-bootstrap-validation" version="1.0">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- arg-parsing
- validation-checks
- success-path
- failure-path
- retry-loop
- terminal-failure
</sections>

<section id="arg-parsing">
<core>
# Reference: Bootstrap & Arg Validation

## Arg Parsing

Extract `PID` and `SESSION_ID` from the invocation string `/souffleur PID:$PID SESSION_ID:$SESSION_ID`.

Parse both values as plain strings. PID is a numeric process ID. SESSION_ID is a UUID string identifying the Conductor's Claude Code session.
</core>
</section>

<section id="validation-checks">
<core>
## Validation Checks

Perform all three checks in order. Stop at the first failure.

### 1. PID Check

Confirm the Conductor process is alive:

```bash
kill -0 $PID
```

Exit code 0 = alive. Non-zero = dead or invalid.

### 2. Session ID Check

Verify a sentinel file exists for the session ID:

```bash
ls ~/.claude/projects/*/$SESSION_ID*.jsonl
```

At least one file must match. If no match, the session ID is invalid or the session has not yet written its sentinel file.

### 3. Table Check

Query comms-link for the `souffleur` row:

```sql
SELECT task_id, state FROM orchestration_tasks WHERE task_id = 'souffleur';
```

The row must exist. The Conductor creates it before launching the Souffleur.
</core>
</section>

<section id="success-path">
<core>
## Success Path

When all three checks pass, update the row to `confirmed` and proceed to SETTLING:

```sql
UPDATE orchestration_tasks
SET state = 'confirmed', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';
```
</core>
</section>

<section id="failure-path">
<core>
## Failure Path

When any check fails, update the row to `error` and insert a diagnostic message:

```sql
UPDATE orchestration_tasks
SET state = 'error', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';

INSERT INTO orchestration_messages (task_id, from_session, message, message_type)
VALUES ('souffleur', '$CLAUDE_SESSION_ID',
    'SOUFFLEUR ERROR: Arg validation failed. [failure details]',
    'error');
```

The failure details must specify which check failed and why (e.g., "PID 12345 is not alive", "No sentinel file found for session abc-123", "No souffleur row in orchestration_tasks").
</core>
</section>

<section id="retry-loop">
<core>
## Validation Retry Loop

The Souffleur cannot be relaunched by the Conductor — it must self-recover from validation failures.

1. Set row to `error`, insert diagnostic message with what failed
2. Poll every ~30 seconds for the Conductor's reply:
   ```sql
   SELECT message FROM orchestration_messages
   WHERE task_id = 'souffleur'
     AND message_type = 'instruction'
   ORDER BY timestamp DESC LIMIT 1;
   ```
3. Parse corrected args from the reply
4. Re-validate with the corrected args
5. On success → set `confirmed`, proceed to SETTLING
6. On failure → increment retry counter, set `error` again, insert new diagnostic, wait again
</core>
</section>

<section id="terminal-failure">
<mandatory>
## Terminal Failure

After 3 failed validation attempts, the Souffleur cannot recover. Set the row to `exited`, insert a terminal message, and exit the session:

```sql
UPDATE orchestration_tasks
SET state = 'exited', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';

INSERT INTO orchestration_messages (task_id, from_session, message, message_type)
VALUES ('souffleur', '$CLAUDE_SESSION_ID',
    'SOUFFLEUR TERMINAL: Arg validation failed 3 times. Cannot recover.
     Attempts: [summary of each failure reason]
     Manual relaunch required.',
    'error');
```

Do not retry after 3 failures. Exit cleanly.
</mandatory>
</section>

</skill>
