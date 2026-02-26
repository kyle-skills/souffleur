<skill name="souffleur-example-conductor-relaunch" version="1.2">

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
# Example: Conductor Relaunch

## Scenario

The Conductor (PID 45231) has been running for 2 hours. The Souffleur's watcher detects that the Conductor's heartbeat is >240 seconds stale — the Conductor's internal watcher has likely crashed, and the main session is frozen or looping. The watcher exits to notify the Souffleur.

Because this is a crash signal (`CONDUCTOR_DEAD:heartbeat`), the main session routes directly to the `claude_export` provider — crash events bypass the recovery router's Lethe preflight.
</context>
</section>

<section id="watcher-detection">
<core>
## Step 1: Watcher Exits

The watcher's poll cycle detects:
```sql
SELECT last_heartbeat,
  (julianday('now') - julianday(last_heartbeat)) * 86400 AS age_seconds
FROM orchestration_tasks WHERE task_id = 'task-00';
-- Returns: 2026-02-21 14:30:00 | 312.5
```

Heartbeat is 312 seconds stale (>240 threshold). The watcher exits immediately with:
```
CONDUCTOR_DEAD:heartbeat
Task count: 8
```

The Souffleur main session receives the watcher's exit.
</core>
</section>

<section id="relaunch-sequence">
<core>
## Step 2: claude_export Provider Executes

The `claude_export` provider runs kill/export/trim, then applies the post-trim
estimation gate (see `references/claude-export-recovery-provider.md`).

### Step 2.1 — Kill Old Conductor
```bash
kill -0 45231 && kill 45231
# PID is alive (frozen) — SIGTERM sent
```

### Step 2.2 — Export Conversation Log
```bash
claude_export abc12345-def6-7890-ghij-klmnopqrstuv
# Output: ~/Documents/claude_exports/abc12345-def6-7890-ghij-klmnopqrstuv_clean.md
```

### Step 2.3 — Size Check
```bash
wc -c < ~/Documents/claude_exports/abc12345-def6-7890-ghij-klmnopqrstuv_clean.md
# Output: 523000 (under 800k — use as-is)
```

### Step 2.4 — Post-Trim Estimate Gate

Estimator runs on trimmed artifact:

```bash
python3 skill/scripts/souffleur-estimate-export.py ~/Documents/claude_exports/abc12345-def6-7890-ghij-klmnopqrstuv_clean.md
# Output: estimated_tokens=171224, threshold=400000 (gate pass)
```

Because gate passes, provider launches from export path.

### Step 2.5 — Launch New Conductor

The exit reason is `CONDUCTOR_DEAD:heartbeat`, so `{RECOVERY_REASON}` is substituted with the crash reason line.

```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Conductor (S2)" -- \
  env -u CLAUDECODE claude --permission-mode acceptEdits "/conductor --recovery-bootstrap

Your previous Conductor session crashed or became unresponsive.

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

Provider return:
- `status=success`, `provider_used=claude_export`, `new_conductor_pid=52847`, `session_id_mode=rediscover`
</core>
</section>

<section id="monitoring-relaunch">
<core>
## Step 3: Shared Wrap-Up and Monitoring Relaunch

Shared wrap-up applies retry tracking and relaunches monitoring layers (see `references/recovery-wrap-up.md`).

Retry tracking:
- `last_task_count` was 2, watcher reported 8 → new tasks appeared → reset `retry_count` to 0
- Update `last_task_count` = 8
- `session_id_mode=rediscover` → set `awaiting_session_id=true`

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
Terminate the existing teammate (it was monitoring the old watcher's heartbeat pattern).

### Launch New Teammate
New teammate starts with fresh ~360 second initial wait, matching the new watcher's ~240 second initial wait plus buffer.

### Return to Idle
Transition: WATCHING → WATCHING (same state, new Conductor generation)

The new watcher will wait ~240 seconds, then begin polling. If the new Conductor bootstraps and starts heartbeating, the watcher will detect the new session_id and exit with `SESSION_ID_FOUND:{new_id}`. The Souffleur will then update its session ID and launch a normal-mode watcher.
</core>
</section>

<section id="summary">
<context>
## Summary

Conductor crash relaunch workflow (claude_export provider, gate-pass branch):
1. Watcher detects stale heartbeat (>240s), exits with `CONDUCTOR_DEAD:heartbeat`
2. Main session routes directly to `claude_export` provider (crash bypasses router preflight)
3. Provider: kill old Conductor (guard with kill -0)
4. Provider: export conversation log via claude_export
5. Provider: size check (under 800k, no truncation needed)
6. Provider: post-trim estimate gate passes (under threshold)
7. Provider: launch new Conductor with default recovery prompt (`--recovery-bootstrap`)
8. Shared wrap-up: retry tracking — new tasks appeared, counter stays at 0
9. Shared wrap-up: launch new watcher (awaiting mode)
10. Shared wrap-up: kill old teammate, launch new teammate
11. Return to idle

Total main session context consumed: minimal — parsed one exit message, ran a few bash commands, launched two agents. The heavy lifting (conversation export, new Conductor bootstrap) happens outside the Souffleur's context.
</context>
</section>

</skill>
