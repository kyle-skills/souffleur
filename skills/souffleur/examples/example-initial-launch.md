<skill name="souffleur-example-initial-launch" version="1.0">

<metadata>
type: example
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- scenario
- arg-validation
- settling
- watching
- summary
</sections>

<section id="scenario">
<context>
# Example: Initial Launch

## Scenario

The Conductor has just started an orchestration plan. It creates the database rows and launches the Souffleur in a kitty window with the invocation `/souffleur PID:45231 SESSION_ID:abc12345-def6-7890-ghij-klmnopqrstuv`.
</context>
</section>

<section id="arg-validation">
<core>
## Step 1: VALIDATING State

The Souffleur parses the invocation string and extracts:
- PID: `45231`
- SESSION_ID: `abc12345-def6-7890-ghij-klmnopqrstuv`

### PID Check
```bash
kill -0 45231  # Exit code 0 — Conductor is alive
```

### Session ID Check
```bash
ls ~/.claude/projects/*/abc12345-def6-7890-ghij-klmnopqrstuv*.jsonl
# Match found — sentinel file exists
```

### Table Check
```sql
SELECT task_id, state FROM orchestration_tasks WHERE task_id = 'souffleur';
-- Returns: souffleur | watching
```

All three checks pass. Update state to `confirmed`:
```sql
UPDATE orchestration_tasks
SET state = 'confirmed', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';
```

Transition: VALIDATING → SETTLING
</core>
</section>

<section id="settling">
<core>
## Step 2: SETTLING State

Launch the monitoring layers:

### Launch Watcher (Background Subagent)
```python
Task("Monitor Conductor liveness", prompt="""
Poll the Conductor's liveness every ~60 seconds using comms-link.

Conductor PID: 45231
Conductor session ID: abc12345-def6-7890-ghij-klmnopqrstuv
Awaiting session ID: false
...
""", subagent_type="general-purpose", model="opus", run_in_background=True)
```

The watcher will wait ~240 seconds before its first check.

### Launch Teammate (Self-Monitor)
```python
Task("Monitor watcher liveness", prompt="""
You are the Souffleur's self-monitor...
...
""", subagent_type="general-purpose", model="opus")
```

The teammate will wait ~360 seconds before its first check.

### Initialize In-Session State
- `conductor_pid` = 45231
- `conductor_session_id` = abc12345-def6-7890-ghij-klmnopqrstuv
- `retry_count` = 0
- `last_task_count` = 2 (souffleur + task-00)
- `awaiting_session_id` = false
- `relaunch_generation` = 1

Transition: SETTLING → WATCHING
</core>
</section>

<section id="watching">
<core>
## Step 3: WATCHING State

The main session is now idle. Context usage is near-zero. The watcher polls every ~60 seconds in the background. The teammate monitors the watcher every ~180 seconds.

The Souffleur waits for one of two events:
1. Watcher exits (background task completes) — route by exit reason
2. Teammate sends a message — watcher is dead, relaunch needed

Normal orchestration proceeds. The Conductor launches Musicians, creates tasks, manages reviews. The Souffleur observes none of this directly — it only knows about the Conductor's PID and heartbeat.
</core>
</section>

<section id="summary">
<context>
## Summary

Initial launch workflow:
1. Parse PID and SESSION_ID from invocation
2. Validate all three checks (PID alive, sentinel file exists, souffleur row exists)
3. Set state to `confirmed`
4. Launch watcher (background, ~240s initial wait)
5. Launch teammate (foreground, ~360s initial wait)
6. Initialize tracked state
7. Enter WATCHING — idle until event

Context usage at WATCHING entry: near-zero. The main session has only parsed args, run three checks, launched two agents, and set a few variables.
</context>
</section>

</skill>
