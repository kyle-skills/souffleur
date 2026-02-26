<skill name="souffleur-claude-export-recovery-provider" version="1.0">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
provider: claude_export
</metadata>

<sections>
- overview
- inputs-and-defaults
- step-1-kill
- step-2-export
- step-3-size-check
- step-4-launch
- return-contract
- failure-handling
</sections>

<section id="overview">
<context>
# Reference: claude_export Recovery Provider

This provider implements the legacy Souffleur recovery path:

1. Kill old Conductor
2. Export transcript with `claude_export`
3. Size-check/truncate export
4. Relaunch Conductor in recovery-bootstrap mode

This provider is selected by the router when:
- Lethe preflight fails, or
- Lethe launch fails twice before relaunch starts.
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

The provider should resolve defaults before executing any launch commands.
</core>
</section>

<section id="step-1-kill">
<core>
## Step 1 — Kill Old Conductor

Guard with liveness check before sending SIGTERM:

```bash
kill -0 $PID && kill $PID
```

If already dead, `kill -0` fails and the `kill` is skipped.
</core>
</section>

<section id="step-2-export">
<core>
## Step 2 — Export Conversation Log

Export the Conductor transcript:

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
- Over 800,000 chars: preserve top file summary plus newest ~800,000 chars.

Truncation must preserve continuity for the replacement Conductor.
</core>
</section>

<section id="step-4-launch">
<core>
## Step 4 — Launch New Conductor

Use `conductor-launch-prompts.md` template, substituting:
- `{PERMISSION_MODE}` from payload or default
- `{RESUME_PROMPT}` from payload or default
- `{RECOVERY_REASON}` from watcher exit reason
- `{EXPORT_PATH}`, `{OLD_SESSION_ID}`, `{N}`

Capture PID via `echo $! > temp/souffleur-conductor.pid` and load it into in-session state as `new_conductor_pid`.

The session ID is expected to change on fresh relaunch. Wrap-up phase should set `awaiting_session_id=true`.
</core>
</section>

<section id="return-contract">
<core>
## Return Contract

On success, return this logical contract to the router/wrap-up phase:

```text
status: success
provider_used: claude_export
new_conductor_pid: <pid>
new_conductor_session_id: unknown
session_id_mode: rediscover
artifact_path: ~/Documents/claude_exports/<old_session_id>_clean.md
```

`session_id_mode=rediscover` means wrap-up launches watcher with `awaiting_session_id=true`.
</core>
</section>

<section id="failure-handling">
<mandatory>
## Failure Handling

If launch fails (no PID captured):
- set provider status to failure
- include failure reason and stage
- return control to router for policy handling

If this provider was invoked after Lethe preflight/launch failures, there is no additional provider fallback. Router should exit through standard retry/exhaustion policy.
</mandatory>
</section>

</skill>
