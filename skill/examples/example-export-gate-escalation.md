<skill name="souffleur-example-export-gate-escalation" version="1.0">

<metadata>
type: example
parent-skill: souffleur
tier: 3
</metadata>

<sections>
- scenario
- export-gate-fails
- compact-escalation
- wrap-up
- summary
</sections>

<section id="scenario">
<context>
# Example: Export Gate Escalation to Standard Compact

## Scenario

Watcher exits with `CONTEXT_RECOVERY`. Lethe preflight fails, so router selects
`claude_export` provider.

claude_export succeeds, trim completes, but post-trim estimate is above configured
threshold. Souffleur discards export artifact and escalates to standard compact.
</context>
</section>

<section id="export-gate-fails">
<core>
## Step 1: claude_export Gate Decision

Provider executes:
1. kill old Conductor
2. `claude_export` transcript
3. trim policy

Then estimator runs on trimmed artifact:

```bash
python3 skill/scripts/souffleur-estimate-export.py ~/Documents/claude_exports/abc12345-def6-7890-ghij-klmnopqrstuv_clean.md
```

Output (example):

```json
{
  "ok": true,
  "estimated_tokens": 462881,
  "estimated_tokens_full": 681204,
  "start_mode": "last_compact_marker",
  "marker_found": true
}
```

Threshold (from config/default): `400000`

Decision: `462881 > 400000` -> gate fail, export artifact discarded.
</core>
</section>

<section id="compact-escalation">
<core>
## Step 2: Escalate to Standard Compact

Escalation contract:

```text
status: escalate
provider_used: claude_export
next_provider: standard_compact
already_killed: true
reason: export_gate_threshold_exceeded
```

Because `already_killed=true`, standard compact skips only Step 1 (kill), then runs:
- Step 2 baseline capture (`SESSION_ID` JSONL line count)
- Step 3 compact watcher launch
- Step 4 `claude --resume <SESSION_ID> "/compact"`
- Step 5 detect `compact_boundary`, kill compact session
- Step 6 relaunch Conductor with resume template

New PID captured: `52847`
Session mode: `reused`
</core>
</section>

<section id="wrap-up">
<core>
## Step 3: Shared Wrap-Up

Wrap-up applies standard sequence:
- retry/task-progress bookkeeping
- watcher launch first
- teammate rotation
- return to WATCHING

No second export attempt is made in this cycle.
</core>
</section>

<section id="summary">
<context>
## Summary

Export route can succeed operationally but still escalate when post-trim context
is too large.

Flow:
1. claude_export + trim
2. post-trim estimate gate fails
3. discard artifact
4. standard compact escalation (`already_killed=true`)
5. compact + resumed relaunch
6. shared wrap-up and monitoring re-entry
</context>
</section>

</skill>
