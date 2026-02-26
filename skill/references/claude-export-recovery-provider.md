<skill name="souffleur-claude-export-recovery-provider" version="1.1">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
provider: claude_export
</metadata>

<sections>
- overview
- inputs-and-defaults
- config-and-permission-resolution
- step-1-kill
- step-2-export
- step-3-size-check
- step-4-estimation-gate
- step-5-launch-or-escalate
- return-contract
- failure-handling
</sections>

<section id="overview">
<context>
# Reference: claude_export Recovery Provider

This provider performs export-based recovery with a post-trim context gate.

Flow:
1. Kill old Conductor
2. Export transcript with `claude_export`
3. Size-check/truncate export
4. Estimate effective post-trim context
5. Route:
   - launch Conductor from export when within threshold
   - escalate to `standard_compact` when above threshold

This provider is selected when:
- Lethe preflight fails, or
- Lethe launch fails twice before relaunch starts, or
- crash/death event routing chooses claude_export first.
</context>
</section>

<section id="inputs-and-defaults">
<core>
## Inputs and Defaults

Inputs:
- `conductor_pid`
- `conductor_session_id`
- `relaunch_generation`
- `recovery_reason`
- optional payload fields: `permission_mode`, `resume_prompt`

Defaults:
- `permission_mode` default: `acceptEdits`
- `resume_prompt` default: from `conductor-launch-prompts.md` default section

The provider resolves defaults before launch commands.
</core>
</section>

<section id="config-and-permission-resolution">
<core>
## Config and Permission Resolution

Before launch/gate decisions:

1. Resolve config:

```bash
python3 skill/scripts/souffleur-config.py --project-dir /home/kyle/claude/remindly
```

2. Read:
- `force_compact_threshold_tokens`
- `max_external_permission`

3. Clamp requested permission against max ceiling:

```text
effective_permission = min(requested_permission, max_external_permission)
```

If requested permission is invalid or missing, treat as `acceptEdits`.
</core>
</section>

<section id="step-1-kill">
<core>
## Step 1 — Kill Old Conductor

Guard with liveness check before SIGTERM:

```bash
kill -0 $PID && kill $PID
```

If already dead, `kill -0` fails and `kill` is skipped.
</core>
</section>

<section id="step-2-export">
<core>
## Step 2 — Export Conversation Log

Export transcript:

```bash
claude_export $SESSION_ID
```

Expected output path:
`~/Documents/claude_exports/${SESSION_ID}_clean.md`
</core>
</section>

<section id="step-3-size-check">
<core>
## Step 3 — Size Check and Truncation

Approximate 200k tokens as ~800k characters.

```bash
wc -c < ~/Documents/claude_exports/${SESSION_ID}_clean.md
```

- Under 800,000 chars: use file as-is.
- Over 800,000 chars: preserve top summary section plus newest ~800,000 chars.

This trim is pre-gate normalization only. Gate decision still runs after trim.
</core>
</section>

<section id="step-4-estimation-gate">
<core>
## Step 4 — Post-Trim Estimation Gate

Run Souffleur estimator on the trimmed export artifact:

```bash
python3 skill/scripts/souffleur-estimate-export.py ~/Documents/claude_exports/${SESSION_ID}_clean.md
```

Estimator rules:
- conservative estimate: `chars / 3`
- scope starts at latest compact marker when present
- fallback scope is full file when no marker is found

Compare estimate against threshold:
- threshold source: `FORCE_COMPACT` config override or default `400000`

Routing decision:
- `estimated_tokens <= threshold`: export path may launch
- `estimated_tokens > threshold`: discard export artifact and escalate to standard compact
</core>
</section>

<section id="step-5-launch-or-escalate">
<core>
## Step 5 — Launch or Escalate

### Branch A: Launch from Export (Gate Pass)

Use `conductor-launch-prompts.md` export template with:
- `{EFFECTIVE_PERMISSION}` (clamped)
- `{RESUME_PROMPT}`
- `{RECOVERY_REASON}`
- `{EXPORT_PATH}`
- `{OLD_SESSION_ID}`

Capture PID via `echo $! > temp/souffleur-conductor.pid`.

### Branch B: Escalate to Standard Compact (Gate Fail)

1. Discard export artifact path for this cycle.
2. Return escalation contract to router/provider dispatcher:

```text
status: escalate
provider_used: claude_export
next_provider: standard_compact
already_killed: true
reason: export_gate_threshold_exceeded
```

Escalation skips only compact Step 1 (kill). Compact flow must still do baseline,
watcher, `/compact`, detection, and relaunch.
</core>
</section>

<section id="return-contract">
<core>
## Return Contract

### On export-launch success

```text
status: success
provider_used: claude_export
new_conductor_pid: <pid>
new_conductor_session_id: unknown
session_id_mode: rediscover
artifact_path: ~/Documents/claude_exports/<old_session_id>_clean.md
```

### On gate escalation

```text
status: escalate
provider_used: claude_export
next_provider: standard_compact
already_killed: true
new_conductor_pid: null
session_id_mode: pending
artifact_path: discarded
```
</core>
</section>

<section id="failure-handling">
<mandatory>
## Failure Handling

If `claude_export` command fails, export file missing, or estimator execution fails:
- route to `standard_compact` with `already_killed=true`
- do not attempt a second export in the same cycle

If launch fails after gate pass (no PID captured):
- set provider status to failure
- include stage + reason
- return control to router policy handling

Provider-level fallback order:
1. export path
2. standard compact escalation/fallback
3. compact retry once
4. fail closed (handled by standard compact provider)
</mandatory>
</section>

</skill>
