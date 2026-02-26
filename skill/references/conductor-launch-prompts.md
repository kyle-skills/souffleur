<skill name="souffleur-conductor-launch-prompts" version="1.2">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- default-resume-prompt
- claude-export-launch-template
</sections>

<section id="overview">
<context>
# Reference: Conductor Launch Prompts

Contains the prompt defaults and launch template fields used when the Souffleur relaunches a Conductor generation. The claude_export provider uses this template directly. The Lethe provider may pass a prompt through to Lethe for resumed-session launch handling.
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

<section id="claude-export-launch-template">
<core>
## claude_export Launch Template

Used by `claude-export-recovery-provider.md`. Substitute placeholders:

- `{N}` — relaunch generation number
- `{PERMISSION_MODE}` — `permission_mode` from payload or default `acceptEdits`
- `{RESUME_PROMPT}` — payload prompt or default prompt
- `{RECOVERY_REASON}` — crash/context-recovery reason line
- `{EXPORT_PATH}` — claude_export output path
- `{OLD_SESSION_ID}` — predecessor Conductor session ID

```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Conductor (S{N})" -- \
  env -u CLAUDECODE claude --permission-mode {PERMISSION_MODE} "{RESUME_PROMPT}

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

<mandatory>
After launch, provider control returns to `recovery-wrap-up.md` for retry tracking and monitoring-layer relaunch.
</mandatory>
</section>

</skill>
