<skill name="souffleur-lethe-recovery-provider" version="1.0">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
provider: lethe
</metadata>

<sections>
- overview
- preflight
- payload-resolution
- launch-protocol
- completion-contract
- pid-resolution
- retry-and-fallback
- return-contract
</sections>

<section id="overview">
<context>
# Reference: Lethe Recovery Provider

This provider delegates compaction and relaunch to a Lethe teammate.

High-level flow:
1. Preflight availability check
2. Resolve payload/defaults
3. Launch Lethe teammate (autonomous)
4. Wait for completion contract
5. Resolve PID (direct or discovery)
6. Return provider result to wrap-up
</context>

<mandatory>
No double-relaunch: after Lethe has started a new Conductor generation, Souffleur must not execute claude_export recovery for the same event cycle.
</mandatory>
</section>

<section id="preflight">
<core>
## Preflight (Strict Soft-Dependency Check)

Preflight determines provider selection only. It does not start relaunch.

Suggested checks:
1. Confirm `lethe` skill is present in available skills list for the session.
2. Confirm Lethe invocation path is usable for the target session context.

Outcomes:
- Preflight pass -> route to Lethe provider.
- Preflight fail -> router selects claude_export provider.

Preflight failure is non-fatal by design.
</core>
</section>

<section id="payload-resolution">
<core>
## Payload Resolution

Read latest Souffleur instruction payload with header `CONTEXT_RECOVERY_PAYLOAD_V1`.

Relevant fields:
- `permission_mode` (optional)
- `resume_prompt` (optional)

Defaults:
- If `resume_prompt` missing, use shared default prompt from `conductor-launch-prompts.md`.
- `permission_mode` may be forwarded to Lethe, but Lethe is authoritative for final permission resolution behavior.
</core>
</section>

<section id="launch-protocol">
<core>
## Launch Protocol (Autonomous Teammate)

Launch a teammate (model `opus`) dedicated to Lethe compaction and relaunch.

Inputs passed to teammate:
- `conductor_session_id`
- `conductor_pid`
- `resume_prompt` (resolved)
- `permission_mode` (if present)
- explicit requirement to report completion contract back to Souffleur

The teammate runs Lethe autonomously and returns once terminal state is reached.

Souffleur remains event-driven and does not run compaction steps directly.
</core>
</section>

<section id="completion-contract">
<core>
## Completion Contract from Lethe Teammate

Expected completion message format (logical fields):

```text
LETHE_RECOVERY_COMPLETE
status: success|failed
relaunch_started: true|false
new_conductor_pid: <pid or empty>
resumed_session_id: <session-id>
notes: <summary>
```

Minimum required fields:
- `status`
- `relaunch_started`
- `resumed_session_id`

`new_conductor_pid` is preferred but may be absent.
</core>
</section>

<section id="pid-resolution">
<core>
## PID Resolution

If completion includes `new_conductor_pid`, use it.

If PID is missing and `status=success` with `relaunch_started=true`:
1. Attempt one PID discovery scan by resumed session ID.
2. If exactly one candidate is found, set `conductor_pid`.
3. If unresolved:
   - set watcher mode to heartbeat-only
   - insert warning message documenting degraded monitoring
   - continue through wrap-up

Example discovery pattern:

```bash
ps -eo pid,args | rg "claude.*(--resume|--session-id)[[:space:]]+$SESSION_ID"
```

Do not loop discovery attempts.
</core>
</section>

<section id="retry-and-fallback">
<mandatory>
## Retry and Fallback Rules

If Lethe launch fails before relaunch starts (`relaunch_started=false`):
- retry Lethe once
- if second attempt fails, route to claude_export provider

If Lethe reports success and relaunch started:
- never fallback to claude_export for this cycle
- resolve PID directly or degrade to heartbeat-only mode
</mandatory>
</section>

<section id="return-contract">
<core>
## Return Contract

On success with PID:

```text
status: success
provider_used: lethe
new_conductor_pid: <pid>
new_conductor_session_id: <resumed_session_id>
session_id_mode: reused
watcher_mode: normal
```

On success without PID after one discovery attempt:

```text
status: success
provider_used: lethe
new_conductor_pid: null
new_conductor_session_id: <resumed_session_id>
session_id_mode: reused
watcher_mode: heartbeat-only
warning_emitted: true
```

On failure before relaunch start:

```text
status: failed
provider_used: lethe
relaunch_started: false
failure_stage: pre-relaunch
```
</core>
</section>

</skill>
