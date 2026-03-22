<skill name="souffleur-example-lethe-provider-fallback" version="1.0">

<metadata>
type: example
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- scenario
- router-preflight
- lethe-launch-failure
- fallback-to-claude-export
- wrap-up
- summary
</sections>

<section id="scenario">
<context>
# Example: Lethe Provider Fallback to claude_export

## Scenario

Watcher exits with `CONTEXT_RECOVERY` and Souffleur enters recovery router.
Lethe preflight passes, but Lethe teammate launch fails before relaunch starts.

Policy requires one retry. Second launch also fails. Router then falls back to claude_export provider.
</context>
</section>

<section id="router-preflight">
<core>
## Step 1: Router Selects Lethe Initially

Router reads payload and resolves defaults.

Preflight result:
- Lethe available -> select `lethe` provider

No fallback is chosen yet because this is still pre-relaunch.
</core>
</section>

<section id="lethe-launch-failure">
<core>
## Step 2: Lethe Fails Before Relaunch

First attempt returns:

```text
status: failed
relaunch_started: false
failure_stage: pre-relaunch
reason: teammate launch transport error
```

Router retries Lethe once.

Second attempt returns the same class of failure (`relaunch_started=false`).

Retry budget exhausted for Lethe launch. Router selects fallback provider.
</core>
</section>

<section id="fallback-to-claude-export">
<core>
## Step 3: claude_export Provider Executes

Fallback provider runs:

1. `kill -0 45231 && kill 45231`
2. `claude_export abc12345-def6-7890-ghij-klmnopqrstuv`
3. size check and truncation policy
4. post-trim estimate gate (`estimated_tokens <= threshold`)
5. relaunch Conductor with defaults:
   - permission: `acceptEdits` (if payload omitted)
   - prompt: default `/conductor --recovery-bootstrap ...`

New PID captured:

```text
new_conductor_pid: 52847
session_id_mode: rediscover
provider_used: claude_export
status: success
```
</core>
</section>

<section id="wrap-up">
<core>
## Step 4: Shared Wrap-Up

Wrap-up applies retry tracking and relaunches monitoring layers:

- `awaiting_session_id=true` (rediscovery required)
- watcher launched first with new PID
- old teammate terminated
- new teammate launched

Souffleur returns to WATCHING.
</core>
</section>

<section id="summary">
<context>
## Summary

Fallback path is valid only because Lethe failed before relaunch started.

Sequence:
1. Lethe selected by preflight
2. Lethe launch failure
3. one retry
4. second pre-relaunch failure
5. fallback to claude_export provider
6. normal wrap-up and monitoring re-entry

This preserves no-double-relaunch safety because fallback occurs before any Lethe-started Conductor generation exists.
</context>
</section>

</skill>
