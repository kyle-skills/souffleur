<skill name="souffleur-database-queries" version="1.3">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- bootstrap-queries
- recovery-router-queries
- watcher-queries
- teammate-queries
- terminal-queries
- message-types
</sections>

<section id="overview">
<context>
# Reference: Database Queries

All SQL patterns Souffleur uses against `orchestration_tasks` and
`orchestration_messages` via comms-link.

Rules:
- Every INSERT into `orchestration_messages` must include `message_type`.
- Every state transition must include `last_heartbeat = datetime('now')`.
</context>
</section>

<section id="bootstrap-queries">
<core>
## Bootstrap Queries

### Table Check
```sql
SELECT task_id, state FROM orchestration_tasks WHERE task_id = 'souffleur';
```

### Confirm Validation Success
```sql
UPDATE orchestration_tasks
SET state = 'confirmed', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';
```

### Report Validation Failure
```sql
UPDATE orchestration_tasks
SET state = 'error', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';

INSERT INTO orchestration_messages (task_id, from_session, message, message_type)
VALUES ('souffleur', '$CLAUDE_SESSION_ID',
    'SOUFFLEUR ERROR: Arg validation failed. [failure details]',
    'error');
```

### Poll for Corrected Args
```sql
SELECT message FROM orchestration_messages
WHERE task_id = 'souffleur'
  AND message_type = 'instruction'
ORDER BY timestamp DESC LIMIT 1;
```

### Terminal Validation Failure
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
</core>
</section>

<section id="recovery-router-queries">
<core>
## Recovery Router Queries

### Read Latest Recovery Payload

```sql
SELECT message FROM orchestration_messages
WHERE task_id = 'souffleur'
  AND message_type = 'instruction'
  AND message LIKE 'CONTEXT_RECOVERY_PAYLOAD_V1%'
ORDER BY timestamp DESC LIMIT 1;
```

If no row is returned, use provider defaults.

### Emit Degraded Monitoring Warning (Lethe PID unresolved)

```sql
INSERT INTO orchestration_messages (task_id, from_session, message, message_type)
VALUES ('souffleur', '$CLAUDE_SESSION_ID',
    'SOUFFLEUR WARNING: Lethe recovery succeeded but Conductor PID could not be resolved.
     Switched watcher to heartbeat-only mode for this generation.
     PID liveness checks are temporarily disabled.',
    'warning');
```

### Emit Export Gate Escalation Notice

```sql
INSERT INTO orchestration_messages (task_id, from_session, message, message_type)
VALUES ('souffleur', '$CLAUDE_SESSION_ID',
    'SOUFFLEUR WARNING: Trimmed claude_export output exceeded configured context threshold.
     Discarded export artifact and escalated recovery to standard compact route.',
    'warning');
```

### Fail Closed After Compact Retry Exhaustion

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
</core>
</section>

<section id="watcher-queries">
<core>
## Watcher Queries

### Update Souffleur Heartbeat
```sql
UPDATE orchestration_tasks SET last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';
```

### Check Conductor Heartbeat Staleness
```sql
SELECT last_heartbeat,
  (julianday('now') - julianday(last_heartbeat)) * 86400 AS age_seconds
FROM orchestration_tasks WHERE task_id = 'task-00';
```
Flag if `age_seconds > 240`.

### Task Count Snapshot
```sql
SELECT COUNT(*) FROM orchestration_tasks;
```

### Check Conductor Session ID (only when awaiting)
```sql
SELECT session_id FROM orchestration_tasks WHERE task_id = 'task-00';
```

### Check Conductor Completion / Recovery Trigger
```sql
SELECT state FROM orchestration_tasks WHERE task_id = 'task-00';
```
Exit if `state = 'complete'` or `state = 'context_recovery'`.
</core>

<guidance>
Normal watcher mode checks PID and heartbeat. Heartbeat-only mode skips PID checks and relies on task-00 heartbeat/state signals.
</guidance>
</section>

<section id="teammate-queries">
<core>
## Teammate Queries

### Check Souffleur Heartbeat Age
```sql
SELECT last_heartbeat,
  (julianday('now') - julianday(last_heartbeat)) * 86400 AS age_seconds
FROM orchestration_tasks WHERE task_id = 'souffleur';
```
Send `WATCHER_DEAD` message if `age_seconds > 180`.
</core>
</section>

<section id="terminal-queries">
<core>
## Terminal Queries

### Clean Completion
```sql
UPDATE orchestration_tasks
SET state = 'complete', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';

INSERT INTO orchestration_messages (task_id, from_session, message, message_type)
VALUES ('souffleur', '$CLAUDE_SESSION_ID',
    'SOUFFLEUR COMPLETE: Conductor finished orchestration plan. Watchdog shutting down.',
    'completion');
```

### Retry Exhaustion
```sql
UPDATE orchestration_tasks
SET state = 'error', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';
```
</core>
</section>

<section id="message-types">
<mandatory>
## Message Types

Every INSERT into `orchestration_messages` must include `message_type`.
Souffleur uses these types:

| Type | Direction | Usage |
|---|---|---|
| `error` | Souffleur -> Conductor | Validation failures, fail-closed, terminal messages |
| `instruction` | Conductor -> Souffleur | Corrected args and context-recovery payload |
| `completion` | Souffleur -> Conductor | Clean shutdown notification |
| `warning` | Souffleur -> Conductor | Degraded monitoring or export gate escalation |

Never insert a message with NULL `message_type`.
</mandatory>
</section>

</skill>
