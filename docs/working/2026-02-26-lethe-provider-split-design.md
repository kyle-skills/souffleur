# Souffleur Lethe Provider Split Design

**Date:** 2026-02-26
**Status:** Approved for planning
**Scope:** `skills_staged/souffleur/skill/`

<sections>
- problem-and-goals
- decisions-locked
- current-state-verification
- provider-split-architecture
- provider-contracts
- payload-contract
- defaults-and-prompt-policy
- failure-and-degradation-policy
- monitoring-wrap-up
- implementation-scope
- verification-plan
</sections>

<section id="problem-and-goals">
<core>
## Problem and Goals

Souffleur currently handles Conductor context recovery through a single path:
`kill -> claude_export -> relaunch`.

The workflow now needs a provider split so Souffleur can prefer Lethe compaction when available while preserving the existing claude_export path as fallback.

Primary goals:
- Keep the existing `context_recovery` trigger contract intact.
- Route recovery through a provider abstraction (`lethe` or `claude_export`).
- Prevent dual-Conductor launch hazards.
- Preserve Souffleur's monitoring invariants and retry semantics.
- Add explicit defaults for permission and resume prompt.
</core>

<guidance>
Non-goal: redesigning Conductor's trigger mechanism. This design keeps `task-00.state = context_recovery` as the entry trigger and only extends payload/content behavior.
</guidance>
</section>

<section id="decisions-locked">
<mandatory>
## Decisions Locked with User

- Use provider split architecture (Option 2), not inline branching.
- Keep trigger as `task-00.state = context_recovery`.
- Conductor supplies new optional payload fields: permission + resume prompt.
- Souffleur continues owning PID/session_id lifecycle.
- Lethe availability check is strict preflight (soft dependency check).
- Payload format is tagged plaintext (not JSON).
- Shared default prompt must start with `--recovery-bootstrap` intent.
- If Lethe path runs and PID is missing: do one PID discovery attempt, then degrade to heartbeat-only mode with warning (no claude_export fallback at that point).
- If Lethe launch fails before relaunch: retry Lethe once, then fallback to claude_export provider.
- Lethe permission override policy is a Lethe concern, not Souffleur concern.
</mandatory>
</section>

<section id="current-state-verification">
<core>
## Current-State Verification

Souffleur already sources and maintains Conductor identity:

- Initial PID/session_id come from invocation parsing:
  `/souffleur PID:$PID SESSION_ID:$SESSION_ID`.
- Relaunch PID is captured from launch command (`$!`).
- New session_id is discovered post-relaunch via watcher exit:
  `SESSION_ID_FOUND:{id}` when `awaiting_session_id=true`.

Result: Conductor does **not** need to send PID/session_id in compact payload.
</core>
</section>

<section id="provider-split-architecture">
<core>
## Provider Split Architecture

Add a router and split recovery logic into three references:

1. `lethe-recovery-provider.md`
2. `claude-export-recovery-provider.md`
3. `recovery-wrap-up.md` (shared minimal post-provider sequence)

Routing flow:

1. Watcher emits `CONTEXT_RECOVERY`.
2. Souffleur enters recovery router.
3. Router runs Lethe preflight.
4. If preflight passes: execute Lethe provider.
5. If preflight fails: execute claude_export provider.
6. Provider returns outcome + relaunch metadata.
7. Souffleur executes shared wrap-up reference and returns to WATCHING.

Provider independence rule:
- `claude_export` is an alternative route selected at router time.
- It is not a prerequisite step for Lethe.
</core>
</section>

<section id="provider-contracts">
<core>
## Provider Contracts

### Common Provider Input

- `conductor_pid` (Souffleur state)
- `conductor_session_id` (Souffleur state)
- `relaunch_generation`
- `retry_count`, `last_task_count`, `current_task_count`
- optional payload fields from Conductor (`permission_mode`, `resume_prompt`)

### Lethe Provider Responsibilities

- Execute handoff to Lethe teammate in autonomous mode.
- Pass Souffleur-held session/PID context plus payload fields.
- Wait for teammate completion message.
- Obtain `new_conductor_pid` from Lethe completion if available.
- If `new_conductor_pid` missing: trigger PID recovery path (see failure policy).
- Return provider result to wrap-up.

### Claude-Export Provider Responsibilities

- Execute existing path: kill old conductor -> `claude_export` -> size policy -> relaunch.
- Capture relaunch PID from launch command.
- Return provider result to wrap-up.
</core>
</section>

<section id="payload-contract">
<core>
## Conductor -> Souffleur Payload Contract

Payload is written to `orchestration_messages` using:
- `task_id = 'souffleur'`
- `message_type = 'instruction'`

Tagged plaintext format:

```text
CONTEXT_RECOVERY_PAYLOAD_V1
permission_mode: acceptEdits
resume_prompt: /conductor --recovery-bootstrap

The session history was cleaned, review handoff documents and resume plan implementation.
```

Parsing rules:
- Must start with `CONTEXT_RECOVERY_PAYLOAD_V1`.
- `permission_mode` optional.
- `resume_prompt` optional.
- Unknown fields ignored.
- Missing fields resolve through defaults policy.
</core>
</section>

<section id="defaults-and-prompt-policy">
<mandatory>
## Defaults and Prompt Policy

Shared default resume prompt (applies when payload omits prompt):

```text
/conductor --recovery-bootstrap

The session history was cleaned, review handoff documents and resume plan implementation.
```

Permission defaults:
- `claude_export` provider default: `acceptEdits`.
- Lethe provider default behavior remains owned by Lethe's own resolution policy.
</mandatory>

<context>
This closes a current gap where claude_export relaunch lacked explicit default prompt/permission handling.
</context>
</section>

<section id="failure-and-degradation-policy">
<mandatory>
## Failure and Degradation Policy

### Router-Level

- Lethe preflight fail -> claude_export provider.
- Lethe preflight pass -> Lethe provider.

### Lethe Launch Failure (before relaunch starts)

- Retry Lethe once.
- If second attempt fails, fallback to claude_export provider.

### Lethe Completed but PID Missing

- Do one PID discovery attempt by session/process scan.
- If PID found: continue normal monitoring.
- If PID not found:
  - Do **not** execute claude_export provider.
  - Switch watcher behavior to heartbeat-only mode.
  - Emit warning entry to session history/database documenting degraded monitoring mode.

### No Double-Relaunch Rule

Once Lethe has already relaunched a Conductor generation, Souffleur must not run claude_export recovery for the same event cycle.
</mandatory>
</section>

<section id="monitoring-wrap-up">
<core>
## Shared Monitoring Wrap-Up Reference

`recovery-wrap-up.md` should include only shared steps:

1. Apply retry/task-progress logic.
2. Set `awaiting_session_id` semantics for next watcher generation.
3. Relaunch monitoring layers preserving invariant:
   - launch new watcher first
   - then rotate teammate
4. Return to WATCHING state.

Provider-specific relaunch mechanics remain outside wrap-up.
</core>
</section>

<section id="implementation-scope">
<core>
## Implementation Scope

Souffleur files expected to change:
- `skill/SKILL.md` (router + provider model + defaults)
- `skill/references/conductor-relaunch.md` (split/refactor)
- `skill/references/monitoring-architecture.md` (degraded heartbeat-only mode docs)
- `skill/references/subagent-prompts.md` (if watcher needs heartbeat-only variant)
- new `skill/references/lethe-recovery-provider.md`
- new `skill/references/claude-export-recovery-provider.md`
- new `skill/references/recovery-wrap-up.md`
- examples for Lethe success/fallback/degraded PID case

Cross-skill work (separate stream):
- Conductor writes `CONTEXT_RECOVERY_PAYLOAD_V1` message.
- Lethe returns `new_conductor_pid` in completion contract and enforces permission precedence policy.
</core>
</section>

<section id="verification-plan">
<core>
## Verification Plan

Required before completion:

1. Update/extend Souffleur examples to cover:
- preflight fail -> claude_export provider
- lethe launch fail twice -> claude_export provider
- lethe success with PID
- lethe success without PID -> heartbeat-only degraded monitoring

2. Run Souffleur validation tooling and relevant repo tests.

3. Static checks:
- router selects one provider per event cycle
- no post-Lethe fallback to claude_export after relaunch started
- default prompt includes `/conductor --recovery-bootstrap`
- message_type usage preserved for all inserts

4. Confirm monitoring ordering invariant still holds:
- new watcher launches before old teammate is killed.
</core>
</section>
