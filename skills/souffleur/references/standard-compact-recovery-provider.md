<skill name="souffleur-standard-compact-recovery-provider" version="1.0">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
provider: standard_compact
</metadata>

<sections>
- overview
- inputs-and-entry-mode
- step-1-kill
- step-2-baseline
- step-3-launch-watcher
- step-4-launch-compact-session
- step-5-detect-complete
- step-6-relaunch-conductor
- return-contract
- failure-handling
</sections>

<section id="overview">
<context>
# Reference: Standard Compact Recovery Provider

This provider compacts the Conductor session in-place using `/compact`, then relaunches
Conductor with `--resume`.

Primary use cases:
- `claude_export` gate escalation (trimmed export still too large)
- fallback when other recovery routes are unavailable

This path preserves session continuity and avoids launching a context-saturated session.
</context>
</section>

<section id="inputs-and-entry-mode">
<core>
## Inputs and Entry Mode

Inputs:
- `conductor_pid`
- `conductor_session_id`
- `relaunch_generation`
- `recovery_reason`
- `effective_permission` (after `MAX_EXTERNAL_PERMISSION` clamp)
- `resume_prompt` (payload or default)
- `already_killed` (`true|false`)

Entry modes:
- `already_killed=false`: execute full sequence (Step 1-6)
- `already_killed=true`: skip only Step 1 and execute Step 2-6

`already_killed=true` is used when escalating from the `claude_export` provider,
which has already terminated the old Conductor process.
</core>
</section>

<section id="step-1-kill">
<core>
## Step 1 — Kill Old Conductor

Run only if `already_killed=false`.

```bash
kill -0 $PID && kill $PID
```

If already dead, `kill -0` fails and the `kill` is skipped.
</core>
</section>

<section id="step-2-baseline">
<core>
## Step 2 — Capture JSONL Baseline

Resolve Conductor JSONL path and baseline line count before starting compact watcher.

```bash
SENTINEL=$(ls -1 ~/.claude/projects/*/${SESSION_ID}.jsonl 2>/dev/null | head -n 1)
BASELINE_LINES=$(wc -l < "$SENTINEL")
```

Watcher must start from this baseline to avoid missing a fast compact completion.
</core>

<mandatory>
If JSONL path cannot be resolved, treat as compact-provider failure and follow retry/fail-closed policy.
</mandatory>
</section>

<section id="step-3-launch-watcher">
<core>
## Step 3 — Launch Compact Watcher

Launch a background watcher that polls JSONL lines after baseline and detects:

```json
{"type":"system","subtype":"compact_boundary"}
```

Detection rules:
- parse only lines with index `> BASELINE_LINES`
- parse each line as JSON
- skip malformed lines
- exit immediately on first compact-boundary detection
- timeout after 300s
</core>

<guidance>
Reuse the proven Conductor compact detection strategy: baseline-first watcher startup,
not mtime stabilization heuristics.
</guidance>
</section>

<section id="step-4-launch-compact-session">
<core>
## Step 4 — Launch Compact Session

Launch compact in resumed session:

```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Compact: Conductor (S{N})" -- \
  env -u CLAUDECODE claude --resume $SESSION_ID --permission-mode {EFFECTIVE_PERMISSION} "/compact" &
echo $! > temp/souffleur-conductor.pid
```

`/compact` is a built-in Claude Code command.
</core>

<mandatory>
Compact watcher must be launched before this step.
</mandatory>
</section>

<section id="step-5-detect-complete">
<core>
## Step 5 — Detect Completion and Kill Compact Session

On compact-boundary detection:

```bash
PID=$(cat temp/souffleur-conductor.pid 2>/dev/null)
kill -0 "$PID" 2>/dev/null && kill "$PID"
```

Then continue to relaunch step.
</core>

<guidance>
The compact session usually stays idle after `/compact`; explicit kill keeps lifecycle deterministic.
</guidance>
</section>

<section id="step-6-relaunch-conductor">
<core>
## Step 6 — Relaunch Conductor (Resumed)

Use `conductor-launch-prompts.md` standard compact template.

Key properties:
- uses `--resume {SESSION_ID}`
- applies permission ceiling via `{EFFECTIVE_PERMISSION}`
- prompt starts with `/conductor --recovery-bootstrap`

Capture relaunch PID with `echo $! > temp/souffleur-conductor.pid`.
</core>
</section>

<section id="return-contract">
<core>
## Return Contract

On success, return:

```text
status: success
provider_used: standard_compact
new_conductor_pid: <pid>
new_conductor_session_id: <same as input session id>
session_id_mode: reused
watcher_mode: normal
```
</core>
</section>

<section id="failure-handling">
<mandatory>
## Failure Handling

Compact provider retry policy for one recovery cycle:

1. First failure (timeout or step error): retry compact once.
2. Second failure: fail closed.

Fail-closed actions:

```sql
UPDATE orchestration_tasks
SET state = 'error', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';

INSERT INTO orchestration_messages (task_id, from_session, message, message_type)
VALUES ('souffleur', '$CLAUDE_SESSION_ID',
    'SOUFFLEUR ERROR: Standard compact recovery failed after 2 attempts.
     Cycle failed closed to prevent unsafe relaunch.
     Check compact watcher logs and JSONL accessibility.',
    'error');
```

Do not fallback back to `claude_export` after compact retry exhaustion in the same cycle.
</mandatory>
</section>

</skill>
