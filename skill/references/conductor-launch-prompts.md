<skill name="souffleur-conductor-launch-prompts" version="1.0">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- crash-recovery-prompt
- context-recovery-prompt
</sections>

<section id="overview">
<context>
# Reference: Conductor Launch Prompts

Contains the verbatim launch prompt templates for spawning a new Conductor session. Each prompt targets a specific recovery protocol in the Conductor's SKILL.md. The Souffleur selects the appropriate prompt based on the watcher's exit reason.

These prompts are used by Step 4 of the Conductor Relaunch Sequence (see conductor-relaunch.md).
</context>
</section>

<section id="crash-recovery-prompt">
<core>
## Crash Recovery Prompt

Used when the watcher exits with `CONDUCTOR_DEAD:pid` or `CONDUCTOR_DEAD:heartbeat`.

Substitute `{N}` (relaunch generation), `{EXPORT_PATH}`, and `{OLD_SESSION_ID}` with actual values.

```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Conductor (S{N})" -- \
  env -u CLAUDECODE claude --permission-mode acceptEdits "/conductor --crash-recovery-protocol

Your previous Conductor session crashed or became unresponsive.

**Recovery context:** {EXPORT_PATH}

Read this file first — it contains the conversation transcript from
your predecessor. The orchestration_tasks and orchestration_messages
tables in comms-link contain the current state of all tasks. Query
those to understand where things stand before resuming.

Your predecessor's session ID was: {OLD_SESSION_ID}" &
echo $! > temp/souffleur-conductor.pid
```
</core>

<mandatory>
After launching the Conductor, return to Step 5 (Retry Tracking) in conductor-relaunch.md.
</mandatory>
</section>

<section id="context-recovery-prompt">
<core>
## Context Recovery Prompt

Used when the watcher exits with `CONTEXT_RECOVERY`.

Substitute `{N}` (relaunch generation), `{EXPORT_PATH}`, and `{OLD_SESSION_ID}` with actual values.

```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Conductor (S{N})" -- \
  env -u CLAUDECODE claude --permission-mode acceptEdits "/conductor --context-recovery-protocol

Your predecessor requested a fresh session due to high context usage.
This is a planned handoff, not a crash.

**Recovery context:** {EXPORT_PATH}

Read this file first — it contains the conversation transcript from
your predecessor. The orchestration_tasks and orchestration_messages
tables in comms-link contain the current state of all tasks. Query
those to understand where things stand before resuming.

Your predecessor's session ID was: {OLD_SESSION_ID}" &
echo $! > temp/souffleur-conductor.pid
```
</core>

<mandatory>
After launching the Conductor, return to Step 5 (Retry Tracking) in conductor-relaunch.md.
</mandatory>
</section>

</skill>
