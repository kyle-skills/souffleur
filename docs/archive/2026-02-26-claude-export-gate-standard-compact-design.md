# Souffleur Export-Gated Compact Escalation Design

**Date:** 2026-02-26
**Status:** Approved for planning
**Scope:** `skills_staged/souffleur/skill/`

<sections>
- problem-and-goals
- decisions-locked
- non-goals
- recovery-routing-model
- claude-export-gate-sequence
- estimation-model
- standard-compact-provider
- failure-policy
- configuration-model
- permission-ceiling-policy
- contracts-and-messages
- implementation-scope
- verification-plan
</sections>

<section id="problem-and-goals">
<core>
## Problem and Goals

Souffleur currently supports provider-routed recovery, but the `claude_export` path
still assumes that a trimmed export is safe enough to relaunch. That assumption can
be wrong when prior compactions have accumulated and effective working context remains
too large.

Goal:
- Add a conservative post-trim context gate before export-based relaunch.
- If the trimmed export is still too large, escalate to standard `/compact` flow
  instead of launching a nearly-full Conductor generation.
- Preserve existing Conductor messaging contracts and recovery trigger behavior.
- Keep Souffleur independent from Lethe runtime dependencies.
</core>
</section>

<section id="decisions-locked">
<mandatory>
## Decisions Locked with User

- Souffleur vendors its own scripts; no strict dependency on Lethe.
- Estimation trigger default is `400000` tokens.
- Estimation is conservative: `chars / 3`.
- Estimation is run on the **trimmed claude_export output**.
- Scope for estimation starts at the latest compact marker if present;
  otherwise start of file.
- If gate fails (`estimated_tokens > threshold`), discard export artifact and
  escalate to standard compact.
- Standard compact escalation skips only Step 1 (kill), because Conductor is
  already killed by export flow.
- Standard compact still performs baseline capture + watcher + detection + relaunch.
- Compact failure gets one retry; second failure fails closed.
- Config file path: `.orchestra_configs/souffleur`.
- Config keys:
  - `FORCE_COMPACT=<int>` (threshold override)
  - `MAX_EXTERNAL_PERMISSION=acceptEdits|bypassPermissions`
- Invalid/missing config values must warn and fall back to defaults.
- Permission default and max fallback: `acceptEdits`.
- No Conductor docs/protocol changes are required for this feature set.
</mandatory>
</section>

<section id="non-goals">
<context>
## Non-Goals

- No changes to Conductor -> Souffleur signaling (`context_recovery` trigger and
  payload envelope stay unchanged).
- No Lethe behavior changes in this stream.
- No change to clean-completion or crash-triggered recovery semantics outside the
  `claude_export` gate + standard compact escalation path.
</context>
</section>

<section id="recovery-routing-model">
<core>
## Recovery Routing Model

This design modifies only the `claude_export` recovery branch and adds a third,
standard compact provider route for escalation/fallback.

For `CONTEXT_RECOVERY` event cycles:

1. Lethe provider selection remains unchanged (out of scope here).
2. If `claude_export` provider runs:
   - execute export and trim
   - run post-trim estimate gate
   - if under threshold: relaunch via export prompt path
   - if over threshold: discard export artifact and escalate to standard compact

For non-context-recovery death events (`CONDUCTOR_DEAD:*`):
- existing behavior remains unless explicitly routed through the same export gate
  policy in implementation.
</core>
</section>

<section id="claude-export-gate-sequence">
<core>
## claude_export Gate Sequence

Updated `claude_export` provider sequence:

1. Kill old Conductor (guarded `kill -0`).
2. Run `claude_export $SESSION_ID` -> produce clean markdown artifact.
3. Apply existing trim policy to artifact (summary head + newest tail).
4. Run Souffleur estimator script against the **trimmed artifact**.
5. Resolve threshold (`FORCE_COMPACT` or default `400000`).
6. Compare estimate:
   - `<= threshold` -> continue normal export relaunch.
   - `> threshold` -> delete/discard artifact and escalate to standard compact.

Escalation metadata must include:
- `already_killed=true`
- original `conductor_session_id`
- recovery reason + generation context
</core>
</section>

<section id="estimation-model">
<core>
## Estimation Model

Souffleur adds a local analyzer script for export artifacts, conceptually similar
in spirit to Lethe's estimator but scoped to Souffleur's gate needs.

Proposed script:
- `skill/scripts/souffleur-estimate-export.py`

Input:
- absolute path to trimmed export artifact

Output JSON (stable contract):

```json
{
  "ok": true,
  "estimated_tokens": 312456,
  "estimated_tokens_full": 487221,
  "start_mode": "last_compact_marker",
  "marker_found": true,
  "marker_count": 2,
  "warnings": []
}
```

Token math:
- `estimated_tokens = floor(chars_in_scope / 3)`

Scope selection rule:
- Find latest compact marker in the trimmed export artifact.
- If found: estimate only content after that marker.
- If not found: estimate from start of artifact.

Marker strategy:
- Detection should support known compact evidence emitted in export text
  (e.g., compact command/confirmation patterns) with strict fallback to
  full-content estimation when ambiguous.

Safety behavior:
- Parse issues produce warning output and fallback to full-content estimation,
  not silent pass-through.
- Estimator failure in gate context should conservatively route to compact
  escalation (never optimistic-launch on unknown size).
</core>

<guidance>
Compact marker presence acts only as the scope start point. It does not alter
threshold values or routing policy.
</guidance>
</section>

<section id="standard-compact-provider">
<core>
## Standard Compact Provider

New provider reference (or equivalent section) codifies standard compact as a
first-class route, reusable for:
- export-gate escalation
- future fallback when other providers are unavailable

Base sequence:
1. Step 1: kill old Conductor
2. Step 2: capture JSONL baseline state
3. Step 3: launch compact watcher
4. Step 4: launch compact session (`claude --resume <session> "/compact"`)
5. Step 5: detect `compact_boundary`, kill compact session
6. Step 6: relaunch Conductor with standard Souffleur recovery launch pattern
7. Step 7: wrap-up / monitoring re-entry

Escalated entry (`already_killed=true`):
- Skip only Step 1.
- Execute Steps 2-7 unchanged.

Detection strategy:
- Reuse proven JSONL monitoring approach from Conductor compact protocol:
  baseline line count + parse new lines + detect `{"type":"system","subtype":"compact_boundary"}`.
</core>
</section>

<section id="failure-policy">
<mandatory>
## Failure Policy

### Export Gate Failure Modes

- Estimator parse warning -> fallback to full-scope estimate.
- Estimator hard failure -> route to compact escalation (conservative).

### Standard Compact Failure Modes

For a given recovery cycle:
1. First compact failure/timeout -> retry compact once.
2. Second compact failure/timeout -> fail closed.

Fail-closed actions:
- set Souffleur state to `error` with `last_heartbeat=now`
- insert diagnostic `orchestration_messages` entry including stage + reason
- stop further relaunch attempts in that cycle

No secondary fallback to export relaunch after compact retry exhaustion.
</mandatory>
</section>

<section id="configuration-model">
<core>
## Configuration Model

Souffleur adds a local config resolver script with deterministic lookup and
strict normalization.

Proposed script:
- `skill/scripts/souffleur-config.py`

Config file path candidates (searched in order):
1. `<project-root>/.orchestra_configs/souffleur`
2. `<project-root-parent>/.orchestra_configs/souffleur`

Nearest match wins. If none found, defaults apply.

Accepted keys:
- `FORCE_COMPACT=<positive-int>`
- `MAX_EXTERNAL_PERMISSION=acceptEdits|bypassPermissions`

Defaults:
- `FORCE_COMPACT=400000`
- `MAX_EXTERNAL_PERMISSION=acceptEdits`

Invalid key values:
- emit warning
- ignore invalid value
- use fallback default

Resolver output contract:

```json
{
  "force_compact_threshold_tokens": 400000,
  "max_external_permission": "acceptEdits",
  "warnings": ["...optional parse/validation warnings..."]
}
```
</core>
</section>

<section id="permission-ceiling-policy">
<mandatory>
## Permission Ceiling Policy

Souffleur must never launch external Claude sessions above configured maximum.

Permission ordering:
- `acceptEdits` < `bypassPermissions`

Effective launch permission:
- `effective = min(requested_permission, max_external_permission)`

Where requested permission can come from:
- payload (`permission_mode`) if present
- provider default otherwise

Enforcement applies to:
- export relaunch path
- compact session launch
- post-compact Conductor relaunch

If requested value is unknown/invalid:
- warn
- treat as `acceptEdits`
</mandatory>
</section>

<section id="contracts-and-messages">
<core>
## Contracts and Messages

No changes to Conductor->Souffleur trigger shape are required.

Maintained contracts:
- `task-00.state='context_recovery'` as kill/recovery trigger
- optional payload message header `CONTEXT_RECOVERY_PAYLOAD_V1`

New internal provider signals (Souffleur-local):
- `export_gate=pass|escalate`
- `compact_entry_mode=normal|already_killed`
- `compact_retry_attempt=1|2`

Operational diagnostics should include:
- resolved threshold
- estimator scope mode (`last_compact_marker` vs `full_file`)
- permission max + effective permission
- failure stage when fail-closed
</core>
</section>

<section id="implementation-scope">
<core>
## Implementation Scope

Primary Souffleur files expected:

- `skill/SKILL.md`
  - add export gate decision and standard compact provider route
  - add config and permission-ceiling rules
- `skill/references/claude-export-recovery-provider.md`
  - gate insertion after trim, escalation contract
- `skill/references/database-queries.md`
  - diagnostic SQL patterns for new warning/error outputs
- `skill/references/recovery-wrap-up.md`
  - ensure compatibility with compact-entry metadata
- `skill/references/` (new)
  - `standard-compact-recovery-provider.md`
  - `souffleur-config-resolution.md` (optional split)
  - `export-estimation-gate.md` (optional split)
- `skill/scripts/` (new)
  - `souffleur-config.py`
  - `souffleur-estimate-export.py`
- `skill/examples/` updates/new examples
  - gate pass
  - gate escalation (already_killed compact entry)
  - compact retry then fail-closed
  - permission cap clamp examples

Conductor scope:
- none for this feature set.
</core>
</section>

<section id="verification-plan">
<core>
## Verification Plan

### Unit/Script Validation

1. Config resolver tests:
- no file -> defaults
- project file valid -> project values
- project invalid + parent valid -> project invalid key falls back, parent not used for same key unless full-file precedence intentionally supports merge (implementation choice must be explicit)
- invalid `FORCE_COMPACT` -> warning + default
- invalid `MAX_EXTERNAL_PERMISSION` -> warning + `acceptEdits`

2. Estimator tests:
- no compact marker -> full-file scope
- one marker -> post-marker scope
- multiple markers -> post-last-marker scope
- malformed content -> warning + conservative fallback behavior
- conservative math uses `chars / 3`

### Flow Verification

3. Export-gate pass scenario:
- trim -> estimate <= threshold -> export relaunch

4. Export-gate escalation scenario:
- trim -> estimate > threshold -> artifact discarded -> compact provider enters with `already_killed=true`
- verify Step 1 skipped, Steps 2-7 executed

5. Compact retry/fail-closed scenario:
- compact timeout x2 -> state `error`, diagnostic inserted, no additional relaunch

6. Permission ceiling scenarios:
- requested `bypassPermissions`, max `acceptEdits` -> launch uses `acceptEdits`
- requested `acceptEdits`, max `bypassPermissions` -> launch uses `acceptEdits`

### Documentation Consistency

7. Verify all examples and references align on:
- threshold defaults
- config key names (`MAX_EXTERNAL_PERMISSION`, singular)
- escalation semantics (skip only Step 1)
- no implied Conductor changes
</core>
</section>
