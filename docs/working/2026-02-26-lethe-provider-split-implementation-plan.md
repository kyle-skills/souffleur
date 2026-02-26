# Souffleur Lethe Provider Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add provider-split context recovery in Souffleur so `context_recovery` routes to Lethe when available and falls back to claude_export when unavailable, without risking dual-Conductor relaunch.

**Architecture:** Introduce a recovery router in `SKILL.md` and split recovery into two provider references (`lethe` and `claude_export`) plus one shared wrap-up reference. Keep PID/session ownership in Souffleur, add tagged payload parsing for optional permission/prompt defaults, and add explicit degraded heartbeat-only behavior when Lethe relaunch succeeds without a recoverable PID.

**Tech Stack:** Claude skill docs (Tier 3 references), shell command templates, comms-link SQL query patterns, Souffleur examples.

---

### Task 1: Add Router and Provider Model in `SKILL.md`

**Files:**
- Modify: `skill/SKILL.md`
- Test: `skill/SKILL.md` (content assertions via `rg`)

**Step 1: Add provider routing section and references**

Insert a new section in `SKILL.md` describing:
- `CONTEXT_RECOVERY` -> router
- preflight check for Lethe
- provider selection (`lethe` or `claude_export`)
- shared wrap-up handoff

Use this anchor text:

```md
Recovery providers are mutually exclusive per event cycle.
Once Lethe has started a relaunch generation, do not execute claude_export for the same cycle.
```

**Step 2: Update protocol wording in relaunch-related sections**

Replace direct six-step relaunch language with provider model language and references:
- `references/lethe-recovery-provider.md`
- `references/claude-export-recovery-provider.md`
- `references/recovery-wrap-up.md`

**Step 3: Run focused assertions**

Run:
```bash
rg -n "lethe-recovery-provider|claude-export-recovery-provider|recovery-wrap-up|mutually exclusive" skill/SKILL.md
```
Expected: all terms found at least once.

**Step 4: Sanity-check no removed invariants**

Run:
```bash
rg -n "New watcher launches BEFORE old teammate is killed|awaiting_session_id|message_type" skill/SKILL.md
```
Expected: invariant lines still present.

**Step 5: Commit**

```bash
git add skill/SKILL.md
git commit -m "docs: add recovery router and provider model to Souffleur skill"
```

### Task 2: Split Existing Relaunch into `claude-export` Provider Reference

**Files:**
- Create: `skill/references/claude-export-recovery-provider.md`
- Modify: `skill/references/conductor-relaunch.md` (deprecate or redirect)
- Modify: `skill/references/conductor-launch-prompts.md` (default prompt contract)

**Step 1: Create `claude-export` provider reference**

Add full provider protocol with:
- kill old conductor (`kill -0` guard)
- `claude_export $SESSION_ID`
- size check/truncation
- relaunch with permission default `acceptEdits`
- payload default prompt fallback
- return contract (`status`, `new_conductor_pid`, `provider_used=claude_export`)

**Step 2: Add shared default resume prompt**

Include the exact default prompt in the provider reference:

```text
/conductor --recovery-bootstrap

The session history was cleaned, review handoff documents and resume plan implementation.
```

**Step 3: Convert old relaunch reference to redirect/legacy marker**

In `conductor-relaunch.md`, replace monolithic procedure body with:
- short note: legacy split completed
- pointers to the two provider references + shared wrap-up

**Step 4: Validate split references**

Run:
```bash
rg -n "claude-export-recovery-provider|/conductor --recovery-bootstrap|acceptEdits|provider_used" skill/references/*.md
```
Expected: hits in new provider file and prompt reference.

**Step 5: Commit**

```bash
git add skill/references/claude-export-recovery-provider.md skill/references/conductor-relaunch.md skill/references/conductor-launch-prompts.md
git commit -m "docs: split claude_export recovery provider from legacy relaunch reference"
```

### Task 3: Add Lethe Provider Reference with Preflight and Retry Rules

**Files:**
- Create: `skill/references/lethe-recovery-provider.md`
- Modify: `skill/references/database-queries.md` (payload read pattern + warning message write)

**Step 1: Write Lethe preflight procedure**

Document strict preflight soft-dependency check and router behavior:
- preflight pass -> lethe provider
- preflight fail -> router fallback to claude_export

Include explicit "preflight is selection-time only" guidance.

**Step 2: Add Lethe launch policy and retry gate**

Document:
- one retry if Lethe launch fails before relaunch starts
- second launch failure -> router fallback to claude_export

**Step 3: Add post-relaunch missing PID policy**

Document exact sequence:
1. one PID discovery attempt
2. if unresolved -> heartbeat-only mode + warning
3. never fallback to claude_export after Lethe relaunch generation started

Use this exact policy sentence:

```md
No double-relaunch: after Lethe has started a new Conductor generation, Souffleur must not execute claude_export recovery for the same event cycle.
```

**Step 4: Add database patterns for payload and warnings**

In `database-queries.md`, add:
- read latest `task_id='souffleur'` + `message_type='instruction'` payload
- insert warning message template for degraded heartbeat-only mode

**Step 5: Commit**

```bash
git add skill/references/lethe-recovery-provider.md skill/references/database-queries.md
git commit -m "docs: add Lethe recovery provider with retry and degraded PID policy"
```

### Task 4: Add Shared Wrap-Up Reference and Monitoring Degraded Mode

**Files:**
- Create: `skill/references/recovery-wrap-up.md`
- Modify: `skill/references/monitoring-architecture.md`
- Modify: `skill/references/subagent-prompts.md`

**Step 1: Create shared wrap-up reference**

Add only shared post-provider steps:
- retry/task-progress bookkeeping
- `awaiting_session_id` handling
- watcher/teammate relaunch sequence
- WATCHING re-entry

**Step 2: Add heartbeat-only degraded mode to monitoring architecture**

Document when PID is unavailable after Lethe path:
- watcher runs heartbeat-only checks
- PID liveness check skipped
- warning/visibility requirements

**Step 3: Add watcher prompt variant**

In `subagent-prompts.md`, add second watcher template:
- normal mode (PID + heartbeat)
- degraded mode (heartbeat-only)

**Step 4: Validate monitoring invariants remain explicit**

Run:
```bash
rg -n "launches BEFORE old teammate is killed|heartbeat-only|degraded" skill/references/monitoring-architecture.md skill/references/subagent-prompts.md skill/references/recovery-wrap-up.md
```
Expected: all three topics present.

**Step 5: Commit**

```bash
git add skill/references/recovery-wrap-up.md skill/references/monitoring-architecture.md skill/references/subagent-prompts.md
git commit -m "docs: add shared recovery wrap-up and degraded heartbeat-only monitoring mode"
```

### Task 5: Add Payload Contract and Defaults Across Skill References

**Files:**
- Modify: `skill/SKILL.md`
- Modify: `skill/references/database-queries.md`
- Modify: `skill/references/conductor-launch-prompts.md`

**Step 1: Add `CONTEXT_RECOVERY_PAYLOAD_V1` format**

Add tagged plaintext contract example:

```text
CONTEXT_RECOVERY_PAYLOAD_V1
permission_mode: acceptEdits
resume_prompt: /conductor --recovery-bootstrap

The session history was cleaned, review handoff documents and resume plan implementation.
```

**Step 2: Add parse defaults and field behavior**

Document:
- unknown fields ignored
- missing permission -> provider defaults
- missing prompt -> shared default prompt

**Step 3: Confirm permission responsibilities are scoped**

Add note:
- Souffleur passes permission field
- Lethe precedence/override constraints are owned by Lethe

**Step 4: Validate payload/default strings**

Run:
```bash
rg -n "CONTEXT_RECOVERY_PAYLOAD_V1|permission_mode|resume_prompt|The session history was cleaned|--recovery-bootstrap" skill/SKILL.md skill/references/*.md
```
Expected: all required strings found.

**Step 5: Commit**

```bash
git add skill/SKILL.md skill/references/database-queries.md skill/references/conductor-launch-prompts.md
git commit -m "docs: define context-recovery payload contract and shared defaults"
```

### Task 6: Update Examples for New Provider Paths

**Files:**
- Modify: `skill/examples/example-context-recovery.md`
- Create: `skill/examples/example-lethe-provider-fallback.md`
- Create: `skill/examples/example-lethe-missing-pid-degraded-mode.md`

**Step 1: Refactor context recovery example**

Update existing example to show router decision and Lethe-primary successful path.

**Step 2: Add preflight/launch fallback example**

Create example demonstrating:
- preflight fail OR Lethe launch fails twice
- router selects claude_export provider

**Step 3: Add missing PID degraded example**

Create example demonstrating:
- Lethe relaunch succeeded
- PID missing
- one discovery attempt fails
- watcher enters heartbeat-only mode with warning

**Step 4: Validate scenario coverage**

Run:
```bash
rg -n "preflight|fallback|heartbeat-only|No double-relaunch|CONTEXT_RECOVERY_PAYLOAD_V1" skill/examples/*.md
```
Expected: all scenario terms appear across examples.

**Step 5: Commit**

```bash
git add skill/examples/example-context-recovery.md skill/examples/example-lethe-provider-fallback.md skill/examples/example-lethe-missing-pid-degraded-mode.md
git commit -m "docs: add provider-split context recovery examples for Lethe and fallback cases"
```

### Task 7: Final Verification and Integration Commit

**Files:**
- Modify: `README.md` (only if provider split behavior summary is needed)
- Modify: `docs/working/2026-02-26-lethe-provider-split-design.md` (only if final notes must be synced)

**Step 1: Run global Souffleur consistency checks**

Run:
```bash
rg -n "CONTEXT_RECOVERY|lethe|claude_export|recovery-wrap-up|heartbeat-only|awaiting_session_id" skill/SKILL.md skill/references/*.md skill/examples/*.md
```
Expected: terms present where intended; no contradictions.

**Step 2: Ensure no forbidden fallback behavior text remains**

Run:
```bash
rg -n "fallback to claude_export" skill/references/lethe-recovery-provider.md
```
Expected: text only in pre-relaunch failure context, not post-relaunch missing-PID context.

**Step 3: Run validation script (best-effort in active environment)**

Run:
```bash
bash skill/scripts/validate-souffleur-state.sh
```
Expected: script executes; if environment-specific failures occur, record them in commit notes.

**Step 4: Review git diff and finalize**

Run:
```bash
git status --short
git diff --stat
```
Expected: only intended Souffleur files changed.

**Step 5: Commit integration batch**

```bash
git add README.md skill/SKILL.md skill/references/*.md skill/examples/*.md skill/scripts/validate-souffleur-state.sh
git commit -m "feat: add Lethe-first provider split recovery flow to Souffleur docs"
```

