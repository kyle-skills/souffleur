<skill name="souffleur-conductor-launch-prompts" version="1.3">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- default-resume-prompt
- permission-ceiling
- claude-export-launch-template
- standard-compact-resume-template
</sections>

<section id="overview">
<context>
# Reference: Conductor Launch Prompts

Contains prompt defaults and launch template fields used when Souffleur relaunches
Conductor generations.

- `claude_export` provider uses fresh-session relaunch template.
- `standard-compact` provider uses resumed-session relaunch template.
- Lethe provider may pass prompt and permission values through to Lethe, but Lethe
  remains authoritative for its own internal launch behavior.
</context>
</section>

<section id="default-resume-prompt">
<mandatory>
## Default Resume Prompt

If no `resume_prompt` is provided in `CONTEXT_RECOVERY_PAYLOAD_V1`, use this exact default:

```text
/conductor --recovery-bootstrap

The session history was cleaned, review handoff documents and resume plan implementation.
```

The first line must be `/conductor --recovery-bootstrap` so the resumed Conductor enters Recovery Bootstrap Protocol immediately.
</mandatory>
</section>

<section id="permission-ceiling">
<mandatory>
## Permission Ceiling

All external session launches must enforce:

```text
effective_permission = min(requested_permission, MAX_EXTERNAL_PERMISSION)
```

Ordering:
- `acceptEdits < bypassPermissions`

`MAX_EXTERNAL_PERMISSION` is resolved by `scripts/souffleur-config.py`.
Fallback default: `acceptEdits`.
</mandatory>
</section>

<section id="claude-export-launch-template">
<core>
## claude_export Launch Template

Used by `claude-export-recovery-provider.md`. Substitute placeholders:

- `{N}` — relaunch generation number
- `{EFFECTIVE_PERMISSION}` — permission after max-ceiling clamp
- `{RESUME_PROMPT}` — payload prompt or default prompt
- `{RECOVERY_REASON}` — crash/context-recovery reason line
- `{EXPORT_PATH}` — claude_export output path
- `{OLD_SESSION_ID}` — predecessor Conductor session ID

```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Conductor (S{N})" -- \
  env -u CLAUDECODE claude --permission-mode {EFFECTIVE_PERMISSION} "{RESUME_PROMPT}

{RECOVERY_REASON}

**Recovery context:** {EXPORT_PATH}

Read this file first — it contains the conversation transcript from
your predecessor. The orchestration_tasks and orchestration_messages
tables in comms-link contain the current state of all tasks. Query
those to understand where things stand before resuming.

Your predecessor's session ID was: {OLD_SESSION_ID}" &
echo $! > temp/souffleur-conductor.pid
```
</core>

<guidance>
`{RECOVERY_REASON}` substitution table:
- `CONDUCTOR_DEAD:pid` or `CONDUCTOR_DEAD:heartbeat` -> `Your previous Conductor session crashed or became unresponsive.`
- `CONTEXT_RECOVERY` -> `Your predecessor requested a fresh session due to high context usage. This is a planned handoff, not a crash.`
</guidance>
</section>

<section id="standard-compact-resume-template">
<core>
## Standard Compact Resume Template

Used by `standard-compact-recovery-provider.md` after `/compact` completes.
This relaunch resumes the compacted original session (same session ID).

Substitute placeholders:

- `{N}` — relaunch generation number
- `{SESSION_ID}` — original Conductor session ID (resumed)
- `{EFFECTIVE_PERMISSION}` — permission after max-ceiling clamp
- `{RESUME_PROMPT}` — payload prompt or default prompt
- `{RECOVERY_REASON}` — context line for operator clarity

```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Conductor (S{N})" -- \
  env -u CLAUDECODE claude --resume {SESSION_ID} --permission-mode {EFFECTIVE_PERMISSION} "{RESUME_PROMPT}

{RECOVERY_REASON}

This session was compacted in-place. Use comms-link state to verify in-flight tasks
and continue orchestration." &
echo $! > temp/souffleur-conductor.pid
```
</core>

<mandatory>
After launch, provider control returns to `recovery-wrap-up.md` for retry tracking and monitoring-layer relaunch.
</mandatory>
</section>

</skill>
