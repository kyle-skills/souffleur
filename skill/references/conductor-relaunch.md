<skill name="souffleur-conductor-relaunch" version="1.0">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- step-1-kill
- step-2-export
- step-3-size-check
- step-4-launch
- step-5-retry-tracking
- step-6-relaunch-monitoring
</sections>

<section id="overview">
<context>
# Reference: Conductor Relaunch Sequence

Executed when the watcher exits with `CONDUCTOR_DEAD:pid`, `CONDUCTOR_DEAD:heartbeat`, or `CONTEXT_RECOVERY`. Six steps recover the Conductor with conversation context preservation.
</context>
</section>

<section id="step-1-kill">
<core>
## Step 1 — Kill Old Conductor

Guard with a liveness check before sending SIGTERM:

```bash
kill -0 $PID && kill $PID
```

If the PID is already dead (the common case for `CONDUCTOR_DEAD:pid`), `kill -0` fails and the `kill` is skipped. This handles both genuinely dead and zombie/frozen Conductors.
</core>
</section>

<section id="step-2-export">
<core>
## Step 2 — Export Conversation Log

Export the dead Conductor's conversation transcript:

```bash
claude-export $SESSION_ID
```

Output path: `~/Documents/claude_exports/${SESSION_ID}_clean.md`

This shell function extracts the conversation from the JSONL session file into clean markdown, including a "Files Modified" summary at the top.
</core>
</section>

<section id="step-3-size-check">
<core>
## Step 3 — Size Check & Truncation

Approximate 200k tokens as ~800k characters.

Check the file size:
```bash
wc -c < ~/Documents/claude_exports/${SESSION_ID}_clean.md
```

- **Under 800,000 characters:** Use the file as-is.
- **Over 800,000 characters:** Truncate to preserve the "Files Modified" summary at the top of the file plus the most recent ~800,000 characters of conversation. Write the truncated version to the same path (overwrite).

The truncation preserves context continuity — the new Conductor gets the summary of all modified files plus the tail of the conversation showing the most recent work.
</core>
</section>

<section id="step-4-launch">
<core>
## Step 4 — Launch New Conductor

Use the **Recovery Bootstrap Prompt** from `references/conductor-launch-prompts.md`. Substitute `{RECOVERY_REASON}` based on the watcher's exit reason:

- If `CONTEXT_RECOVERY`: use the context handoff reason line
- If `CONDUCTOR_DEAD:pid` or `CONDUCTOR_DEAD:heartbeat`: use the crash reason line

Launch in a new kitty window titled `Conductor (S{N})` where N is the `relaunch_generation`. Capture the new PID via `echo $! > temp/souffleur-conductor.pid`.

The new Conductor's session ID is unknown at launch time. The watcher discovers it via the `awaiting_session_id` flag.

Update in-session state:
- `conductor_pid` ← new PID
- `relaunch_generation` ← increment
</core>

<reference path="references/conductor-launch-prompts.md" load="required">
Recovery Bootstrap Prompt template with {RECOVERY_REASON} substitution table. Includes a mandatory return pointer to Step 5.
</reference>
</section>

<section id="step-5-retry-tracking">
<mandatory>
## Step 5 — Retry Tracking

Track consecutive Conductor deaths with no forward progress:

1. Compare `current_task_count` (from the watcher's last snapshot) against `last_task_count`
2. If new tasks appeared since last Conductor launch: reset `retry_count` to 0, otherwise increment `retry_count`
3. Update `last_task_count` ← `current_task_count`

**If `retry_count` reaches 3:** Do not relaunch. Print alert and exit:

```
SOUFFLEUR: Conductor has crashed 3 consecutive times with no forward progress.
Last export: $EXPORT_PATH
Orchestration requires manual intervention.
```

Set the souffleur row to `error`:
```sql
UPDATE orchestration_tasks
SET state = 'error', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';
```

Exit the session.
</mandatory>
</section>

<section id="step-6-relaunch-monitoring">
<core>
## Step 6 — Relaunch Monitoring Layers

After a successful Conductor launch (retry_count < 3):

1. Launch new watcher subagent with `awaiting_session_id = true` and the new PID
2. Kill old teammate
3. Launch new teammate
4. Return to idle (WATCHING state)

The new watcher's initial wait (~240 seconds) gives the new Conductor time to bootstrap and start heartbeating. The `awaiting_session_id = true` flag tells the watcher to also monitor for the new Conductor's session ID appearing on task-00.
</core>
</section>

</skill>
