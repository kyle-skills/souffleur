<skill name="souffleur-example-preflight-failure-fallback" version="1.0">

<metadata>
type: example
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- scenario
- router-preflight-failure
- claude-export-provider-run
- wrap-up
- summary
</sections>

<section id="scenario">
<context>
# Example: Lethe Preflight Failure → claude_export Fallback

## Scenario

Watcher exits with `CONTEXT_RECOVERY`. Souffleur enters the recovery router.

Lethe preflight fails because the skill is not available in the current session. The router selects the `claude_export` provider directly — no Lethe launch is attempted.

This is the simplest fallback path and differs from the launch-failure fallback (see `example-lethe-provider-fallback.md`) where preflight passes but the Lethe teammate cannot start.
</context>
</section>

<section id="router-preflight-failure">
<core>
## Step 1: Router Runs Preflight

Router reads latest payload — no `CONTEXT_RECOVERY_PAYLOAD_V1` message found, so defaults apply.

Preflight check:
- Lethe skill not found in available skills list → preflight fail

Router sets `active_recovery_provider = claude_export` and executes the fallback provider.
</core>
</section>

<section id="claude-export-provider-run">
<core>
## Step 2: claude_export Provider Executes

Provider runs kill/export/trim and post-trim estimation gate (see `references/claude-export-recovery-provider.md`):

1. `kill -0 45231 && kill 45231`
2. `claude_export abc12345-def6-7890-ghij-klmnopqrstuv`
3. size check (under 800k — use as-is)
4. estimate gate pass (`estimated_tokens <= threshold`)
5. relaunch Conductor with defaults:
   - permission: `acceptEdits` (default, no payload)
   - prompt: default `/conductor --recovery-bootstrap ...`

Provider return:

```text
status: success
provider_used: claude_export
new_conductor_pid: 52847
session_id_mode: rediscover
```
</core>
</section>

<section id="wrap-up">
<core>
## Step 3: Shared Wrap-Up

Wrap-up applies retry tracking and relaunches monitoring layers (see `references/recovery-wrap-up.md`):

- `session_id_mode=rediscover` → set `awaiting_session_id=true`
- watcher launched in normal mode (PID 52847 is known)
- old teammate terminated
- new teammate launched
- `active_recovery_provider` cleared

Souffleur returns to WATCHING.
</core>
</section>

<section id="summary">
<context>
## Summary

Preflight-failure fallback path:
1. Watcher exits with `CONTEXT_RECOVERY`
2. Recovery router runs Lethe preflight
3. Preflight fails (Lethe unavailable)
4. Router selects claude_export provider directly — no Lethe launch attempted
5. claude_export provider runs kill/export/trim/gate/relaunch
6. Shared wrap-up relaunches monitoring layers
7. Souffleur returns to WATCHING

This is the fastest fallback path because it skips Lethe entirely at selection time.
</context>
</section>

</skill>
