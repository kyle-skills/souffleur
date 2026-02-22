<skill name="souffleur-conductor-launch-prompts" version="1.1">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- overview
- recovery-bootstrap-prompt
</sections>

<section id="overview">
<context>
# Reference: Conductor Launch Prompt

Contains the verbatim launch prompt template for spawning a new Conductor session after a crash or context recovery. The Souffleur substitutes `{RECOVERY_REASON}` with the appropriate reason line before launching.

This prompt is used by Step 4 of the Conductor Relaunch Sequence (see conductor-relaunch.md).
</context>
</section>

<section id="recovery-bootstrap-prompt">
<core>
## Recovery Bootstrap Prompt

Used for all Conductor relaunches. Substitute `{N}` (relaunch generation), `{EXPORT_PATH}`, `{OLD_SESSION_ID}`, and `{RECOVERY_REASON}` with actual values.

**`{RECOVERY_REASON}` substitution:**

| Exit reason | Substitution |
|---|---|
| `CONDUCTOR_DEAD:pid` or `CONDUCTOR_DEAD:heartbeat` | `Your previous Conductor session crashed or became unresponsive.` |
| `CONTEXT_RECOVERY` | `Your predecessor requested a fresh session due to high context usage. This is a planned handoff, not a crash.` |

```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Conductor (S{N})" -- \
  env -u CLAUDECODE claude --permission-mode acceptEdits "/conductor --recovery-bootstrap

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

<mandatory>
After launching the Conductor, return to Step 5 (Retry Tracking) in conductor-relaunch.md.
</mandatory>
</section>

</skill>
