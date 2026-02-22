<skill name="souffleur-database-queries" version="1.0">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- bootstrap-queries
- watcher-queries
- teammate-queries
- terminal-queries
- message-types
</sections>

<section id="overview">
<context>
# Reference: Database Queries

All SQL patterns the Souffleur uses against `orchestration_tasks` and `orchestration_messages` via comms-link. Every INSERT into `orchestration_messages` must include `message_type`. Every state transition must include `last_heartbeat = datetime('now')`.
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

### Terminal Failure
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

### Check Conductor Completion
```sql
SELECT state FROM orchestration_tasks WHERE task_id = 'task-00';
```
Exit if `state = 'complete'`.
</core>

<guidance>
PID liveness is checked via bash (`kill -0 $PID`), not SQL. The watcher combines all checks in a single poll cycle, updating the Souffleur heartbeat first (step 1) so the teammate sees freshness even if later checks take time.
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

Every INSERT into `orchestration_messages` must include `message_type`. The Souffleur uses these types:

| Type | Direction | Usage |
|---|---|---|
| `error` | Souffleur → Conductor | Validation failures, terminal messages |
| `instruction` | Conductor → Souffleur | Corrected args (read-only by Souffleur) |
| `completion` | Souffleur → Conductor | Clean shutdown notification |

Never insert a message with NULL `message_type`.
</mandatory>
</section>

</skill>
