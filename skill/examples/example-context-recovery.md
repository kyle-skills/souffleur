<skill name="souffleur-example-context-recovery" version="1.0">

<metadata>
type: example
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- scenario
- watcher-detection
- relaunch-sequence
- monitoring-relaunch
- summary
</sections>

<section id="scenario">
<context>
# Example: Context Recovery (Cooperative Handoff)

## Scenario

The Conductor (PID 45231) has been running for 3 hours and its context usage is high. The Conductor writes final state to comms-link and sets task-00 state to `context_recovery`. The Souffleur's watcher detects this state change and exits to notify the Souffleur.
</context>
</section>

<section id="watcher-detection">
<core>
## Step 1: Watcher Detects Context Recovery

The watcher's poll cycle checks task-00 state:

```sql
SELECT state FROM orchestration_tasks WHERE task_id = 'task-00';
-- Returns: context_recovery
```

The watcher exits immediately with:
```
CONTEXT_RECOVERY
Task count: 14
```

The Souffleur main session receives the watcher's exit.
</core>
</section>

<section id="relaunch-sequence">
<core>
## Step 2: Conductor Relaunch Sequence

The exit reason is `CONTEXT_RECOVERY`, so the relaunch sequence uses the **Context Recovery Prompt** from conductor-launch-prompts.md.

### Step 2.1 — Kill Old Conductor
```bash
kill -0 45231 && kill 45231
# PID is alive (cooperative shutdown) — SIGTERM sent
```

### Step 2.2 — Export Conversation Log
```bash
claude-export abc12345-def6-7890-ghij-klmnopqrstuv
# Output: ~/Documents/claude_exports/abc12345-def6-7890-ghij-klmnopqrstuv_clean.md
```

### Step 2.3 — Size Check
```bash
wc -c < ~/Documents/claude_exports/abc12345-def6-7890-ghij-klmnopqrstuv_clean.md
# Output: 680000 (under 800k — use as-is)
```

### Step 2.4 — Launch New Conductor (Context Recovery Prompt)
```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Conductor (S2)" -- \
  env -u CLAUDECODE claude --permission-mode acceptEdits "/conductor --context-recovery-protocol

Your predecessor requested a fresh session due to high context usage.
This is a planned handoff, not a crash.

**Recovery context:** ~/Documents/claude_exports/abc12345-def6-7890-ghij-klmnopqrstuv_clean.md

Read this file first — it contains the conversation transcript from
your predecessor. The orchestration_tasks and orchestration_messages
tables in comms-link contain the current state of all tasks. Query
those to understand where things stand before resuming.

Your predecessor's session ID was: abc12345-def6-7890-ghij-klmnopqrstuv" &
echo $! > temp/souffleur-conductor.pid
```

New PID captured: 52847

Update in-session state:
- `conductor_pid` = 52847
- `relaunch_generation` = 2

### Step 2.5 — Retry Tracking
- `last_task_count` was 2, watcher reported 14 → new tasks appeared → reset `retry_count` to 0
- Update `last_task_count` = 14
- `awaiting_session_id` = true
</core>
</section>

<section id="monitoring-relaunch">
<core>
## Step 3: Relaunch Monitoring Layers

### Launch New Watcher (awaiting mode)
```python
Task("Monitor Conductor liveness", prompt="""
Poll the Conductor's liveness every ~60 seconds using comms-link.

Conductor PID: 52847
Conductor session ID: abc12345-def6-7890-ghij-klmnopqrstuv
Awaiting session ID: true
...
""", subagent_type="general-purpose", model="opus", run_in_background=True)
```

Note: `Awaiting session ID: true` — this watcher will also watch for a new session_id on task-00.

### Kill Old Teammate
Terminate the existing teammate.

### Launch New Teammate
New teammate starts with fresh ~360 second initial wait.

### Return to Idle
Transition: WATCHING → WATCHING (same state, new Conductor generation)

The new Conductor receives the `--context-recovery-protocol` flag, reads the export, queries the database, follows its Context Recovery Protocol, then returns to Step 5 (Task Execution) to resume the orchestration plan.
</core>
</section>

<section id="summary">
<context>
## Summary

Context recovery workflow:
1. Conductor detects high context usage, sets task-00 to `context_recovery`
2. Watcher detects state change, exits with `CONTEXT_RECOVERY`
3. Souffleur runs relaunch sequence with **Context Recovery Prompt** (not crash prompt)
4. Kill old Conductor, export transcript, size check, launch new Conductor
5. Retry tracking — new tasks appeared, counter stays at 0
6. Launch new watcher (awaiting mode), kill+relaunch teammate
7. Return to idle

The only difference from a crash relaunch is the launch prompt (step 4). The Conductor receives `--context-recovery-protocol` instead of `--crash-recovery-protocol`, and the opening line says "planned handoff" instead of "crashed or became unresponsive." All other steps are identical.
</context>
</section>

</skill>
