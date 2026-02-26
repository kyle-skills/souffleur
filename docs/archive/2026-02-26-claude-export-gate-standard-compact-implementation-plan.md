# Souffleur Export-Gated Compact Escalation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a conservative export-output context gate to Souffleur's `claude_export` path and escalate to standard compact when the trimmed export is still too large, while enforcing an external-permission ceiling from config.

**Architecture:** Keep existing recovery trigger and launch contracts. Insert a post-trim estimator gate in `claude_export` provider, add a first-class standard compact provider with `already_killed` entry mode, and add Souffleur-local config + estimator scripts.

**Tech Stack:** Souffleur Tier-3 references/examples, Python helper scripts, shell launch templates, comms-link SQL diagnostics.

---

### Task 1: Add Config Resolver Script and Contract

**Files:**
- Create: `skill/scripts/souffleur-config.py`
- Modify: `skill/SKILL.md`
- Modify: `skill/references/` docs that define defaults and launch behavior

**Step 1: Implement deterministic config resolution**

Support file search:
1. `<project-root>/.orchestra_configs/souffleur`
2. `<project-root-parent>/.orchestra_configs/souffleur`

Nearest file wins.

**Step 2: Parse and validate keys**

Accepted keys:
- `FORCE_COMPACT=<positive-int>`
- `MAX_EXTERNAL_PERMISSION=acceptEdits|bypassPermissions`

Fallback defaults:
- `FORCE_COMPACT=400000`
- `MAX_EXTERNAL_PERMISSION=acceptEdits`

Invalid/missing values:
- emit warning
- fall back to defaults

**Step 3: Output stable JSON contract**

```json
{
  "force_compact_threshold_tokens": 400000,
  "max_external_permission": "acceptEdits",
  "warnings": []
}
```

**Step 4: Wire references**

Document that `MAX_EXTERNAL_PERMISSION` is singular and case-sensitive.

**Step 5: Commit**

```bash
git add skill/scripts/souffleur-config.py skill/SKILL.md skill/references/*.md
git commit -m "docs+scripts: add Souffleur config resolver with compact and permission defaults"
```

### Task 2: Add Export Estimator Script (Post-Trim Gate)

**Files:**
- Create: `skill/scripts/souffleur-estimate-export.py`
- Modify: `skill/references/claude-export-recovery-provider.md`
- Modify: `skill/references/database-queries.md` (diagnostic message templates if needed)

**Step 1: Build estimator over trimmed export artifact**

Input: absolute path to export markdown.

Estimate model:
- conservative `estimated_tokens = floor(chars_in_scope / 3)`

Scope start:
- latest compact marker if found
- else start of file

**Step 2: Return structured output**

Include:
- `estimated_tokens`
- `estimated_tokens_full`
- `start_mode`
- `marker_found`
- `marker_count`
- `warnings`

**Step 3: Conservative failure behavior**

If parsing/marker detection is ambiguous, fallback to full-file scope.
If script cannot produce estimate, return explicit failure so caller can escalate.

**Step 4: Commit**

```bash
git add skill/scripts/souffleur-estimate-export.py skill/references/claude-export-recovery-provider.md skill/references/database-queries.md
git commit -m "docs+scripts: add trimmed-export context estimator for compact gate"
```

### Task 3: Insert Gate Into claude_export Provider

**Files:**
- Modify: `skill/references/claude-export-recovery-provider.md`
- Modify: `skill/SKILL.md`

**Step 1: Keep legacy steps through trim**

Provider still performs:
1. kill old conductor
2. `claude_export`
3. trim policy

**Step 2: Add post-trim estimate gate**

- read threshold from config resolver output
- estimate trimmed export size using script
- route:
  - `estimate <= threshold` -> launch from export path
  - `estimate > threshold` -> discard export artifact and escalate to standard compact

**Step 3: Ensure escalation metadata includes `already_killed=true`**

This must be explicit to avoid duplicate kill attempts.

**Step 4: Commit**

```bash
git add skill/references/claude-export-recovery-provider.md skill/SKILL.md
git commit -m "docs: add post-trim export gate and compact escalation routing"
```

### Task 4: Add Standard Compact Provider (Reusable Third Route)

**Files:**
- Create: `skill/references/standard-compact-recovery-provider.md`
- Modify: `skill/SKILL.md`
- Modify: `skill/references/recovery-wrap-up.md`
- Modify: `skill/references/subagent-prompts.md` (if compact watcher prompt is centralized there)

**Step 1: Define full standard compact sequence**

Base flow:
1. kill old Conductor
2. capture JSONL baseline
3. launch compact watcher
4. launch compact session (`claude --resume <session> "/compact"`)
5. detect `compact_boundary`
6. kill compact session
7. relaunch Conductor
8. hand off to wrap-up

**Step 2: Define escalated entry mode**

If `already_killed=true`, skip only Step 1 and run all remaining steps.

**Step 3: Reuse proven watcher strategy**

Use baseline line count + new line parsing + exact `compact_boundary` detection.

**Step 4: Commit**

```bash
git add skill/references/standard-compact-recovery-provider.md skill/SKILL.md skill/references/recovery-wrap-up.md skill/references/subagent-prompts.md
git commit -m "docs: add standard compact recovery provider with already-killed entry mode"
```

### Task 5: Enforce Permission Ceiling on All External Launches

**Files:**
- Modify: `skill/SKILL.md`
- Modify: provider references that launch external Claude sessions

**Step 1: Implement clamp rule**

Ordering:
- `acceptEdits < bypassPermissions`

Effective launch permission:
- `min(requested_permission, max_external_permission)`

**Step 2: Apply to all launch points**

- export relaunch
- compact session launch
- post-compact Conductor relaunch

**Step 3: Invalid requested permissions**

Warn and normalize to `acceptEdits`.

**Step 4: Commit**

```bash
git add skill/SKILL.md skill/references/*.md
git commit -m "docs: enforce MAX_EXTERNAL_PERMISSION ceiling across recovery launches"
```

### Task 6: Add Failure Policy (Retry Once, Then Fail Closed)

**Files:**
- Modify: `skill/SKILL.md`
- Modify: `skill/references/standard-compact-recovery-provider.md`
- Modify: `skill/references/database-queries.md`

**Step 1: Compact retry policy**

- first compact failure/timeout -> one retry
- second failure/timeout -> fail closed

**Step 2: Fail-closed outputs**

- set Souffleur task state to `error` with heartbeat update
- insert diagnostic message with stage and reason
- stop relaunch for that cycle

**Step 3: Ensure no export fallback after compact exhaustion**

Prevent loopbacks that could launch inconsistent generations.

**Step 4: Commit**

```bash
git add skill/SKILL.md skill/references/standard-compact-recovery-provider.md skill/references/database-queries.md
git commit -m "docs: add compact retry-once then fail-closed recovery policy"
```

### Task 7: Expand Examples and Verify Consistency

**Files:**
- Create/modify examples in `skill/examples/`

Required scenarios:
1. export gate pass (normal relaunch)
2. export gate fail -> compact escalation (`already_killed=true`)
3. compact timeout then retry success
4. compact timeout twice -> fail closed
5. permission cap clamp (`bypassPermissions` requested, `acceptEdits` max)

**Validation commands:**

```bash
rg -n "FORCE_COMPACT|MAX_EXTERNAL_PERMISSION|already_killed|compact_boundary|fail closed|chars / 3|400000" skill/SKILL.md skill/references/*.md skill/examples/*.md
```

Run existing validation script (best effort):

```bash
bash skill/scripts/validate-souffleur-state.sh
```

Record environment-specific failures if DB state is unavailable.

**Step 5: Commit**

```bash
git add skill/examples/*.md skill/SKILL.md skill/references/*.md
git commit -m "docs: add export-gate and standard-compact recovery examples and consistency updates"
```

### Task 8: Final Integration Checkpoint

**Step 1: Global consistency scan**

```bash
rg -n "MAX_EXTERNAL_PERMISSION|FORCE_COMPACT|standard-compact|claude_export|CONTEXT_RECOVERY" skill/SKILL.md skill/references/*.md skill/examples/*.md
```

**Step 2: Confirm no accidental Conductor contract changes**

Ensure references still state:
- Conductor trigger unchanged
- payload envelope unchanged

**Step 3: Final docs commit (if any aggregate edits remain)**

```bash
git add .
git commit -m "docs: finalize Souffleur export-gated compact escalation implementation package"
```
