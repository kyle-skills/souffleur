# Souffleur README Deep Dive

**Date:** 2026-02-27  
**Scope:** Audit `souffleur/README.md`, compare it against current Souffleur runtime behavior (`skill/SKILL.md` + references/scripts), and define a README refresh blueprint aligned with the depth/style used by `musician/README.md` and `dramaturg/README.md`.

## Direct Answers

1. **Souffleur already has a README** at `souffleur/README.md`.
2. **Is it current?** Partially. It reflects major 2026-02-26 routing changes, but it is still too thin for current runtime complexity and is not aligned with Musician/Dramaturg README depth.

## What I Reviewed

- `souffleur/README.md`
- `souffleur/skill/SKILL.md`
- `souffleur/skill/references/bootstrap-validation.md`
- `souffleur/skill/references/monitoring-architecture.md`
- `souffleur/skill/references/lethe-recovery-provider.md`
- `souffleur/skill/references/claude-export-recovery-provider.md`
- `souffleur/skill/references/standard-compact-recovery-provider.md`
- `souffleur/skill/references/recovery-wrap-up.md`
- `souffleur/skill/references/conductor-launch-prompts.md`
- `souffleur/skill/references/database-queries.md`
- `souffleur/skill/scripts/souffleur-config.py`
- `souffleur/skill/scripts/souffleur-estimate-export.py`
- `souffleur/skill/scripts/validate-souffleur-state.sh`
- `souffleur/docs/archive/2026-02-26-lethe-provider-split-design.md`
- `souffleur/docs/archive/2026-02-26-claude-export-gate-standard-compact-design.md`
- Comparison targets:
- `musician/README.md`
- `dramaturg/README.md`

## Executive Findings

1. **README is fresh but under-specified.**
- It has recent updates (including provider split and export-gate escalation), but only 37 lines, versus 171 (Dramaturg) and 235 (Musician).

2. **README does not describe Souffleur's actual runtime contract.**
- The current skill behavior spans a 342-line `SKILL.md` plus provider-specific references and scripts, but the README only covers high-level bullets.

3. **README structure is not aligned with Musician/Dramaturg style.**
- Missing architecture/lifecycle sections, guardrails, provider contracts, requirements/limits, and validation guidance.

4. **A rewrite is better than incremental edits.**
- Souffleur behavior is now rich enough that patching the current README likely produces fragmented docs.

## Evidence Snapshot

- Line counts:
- `souffleur/README.md`: 37
- `souffleur/skill/SKILL.md`: 342
- `musician/README.md`: 235
- `dramaturg/README.md`: 171

- Git evidence (Souffleur repo):
- README has recent commits on 2026-02-26 (`f0c4dce`, `1c29762`, `de6cbd3`, `a524f45`).
- `skill/SKILL.md` also changed repeatedly on 2026-02-26 and includes provider routing + gate behavior.
- Conclusion: this is not an "old untouched README" problem; it is a "scope/depth mismatch" problem.

## Drift Analysis: README vs Runtime

### 1) Structural Drift (vs Musician/Dramaturg README Shape)

Current Souffleur README has only:

- What It Does
- Structure
- Usage
- Origin

Missing sections that now appear as standard in Musician/Dramaturg docs:

- Positioning/comparison table
- How it works / lifecycle
- Guardrails and invariants
- Contracts (inputs/outputs/events)
- Requirements / operational assumptions
- Known limits / failure modes
- Validation scripts

### 2) Behavioral Drift (Missing Critical Runtime Details)

The README currently omits or underspecifies:

1. **Three-layer monitoring timings and behavior**
- Watcher: ~240s initial wait, ~60s cadence.
- Teammate: ~360s initial wait, ~180s cadence.
- Ordering invariant: launch new watcher before killing old teammate.

2. **Watcher modes and degraded operation**
- `normal` vs `heartbeat-only`.
- Heartbeat-only mode after Lethe-success + unresolved PID.

3. **Event routing semantics**
- Crash/death exits route `claude_export` first.
- `CONTEXT_RECOVERY` routes through provider router (Lethe preferred).
- `SESSION_ID_FOUND:{id}` and `CONDUCTOR_COMPLETE` handling.

4. **Provider router and exclusivity rules**
- Lethe preflight as soft dependency selector.
- `active_recovery_provider` no-double-relaunch guard.
- Mutual exclusivity per cycle.

5. **Context-recovery payload contract**
- Tagged message header: `CONTEXT_RECOVERY_PAYLOAD_V1`.
- Optional fields: `permission_mode`, `resume_prompt`.
- Non-fatal malformed payload behavior.

6. **Config and permission model**
- `.orchestra_configs/souffleur` keys:
- `FORCE_COMPACT` (default 400000)
- `MAX_EXTERNAL_PERMISSION` (default `acceptEdits`)
- Launch-permission clamp (`min(requested, max_allowed)`).

7. **claude_export post-trim gate behavior**
- Estimate `chars / 3` from latest compact marker (or full file if none).
- Escalate to standard compact when threshold exceeded.

8. **standard compact provider retry/fail-closed policy**
- One retry then fail closed.

9. **Retry exhaustion semantics**
- `retry_count` increments when no task-progress between recoveries.
- Exit/error at 3 consecutive no-progress recoveries.

10. **Exit conditions are exactly three**
- Arg validation failure (3 retries).
- Retry exhaustion (3 no-progress deaths).
- Conductor completion.

11. **Database/messaging invariants**
- Use comms-link MCP for DB operations in-session.
- Include `message_type` on every `orchestration_messages` insert.
- Include `last_heartbeat = datetime('now')` on state transitions.

### 3) Documentation Consistency Risks to Resolve During Rewrite

1. **Hardcoded project path in operational examples**
- Several references/scripts use `/home/kyle/claude/remindly` in command templates.
- README should avoid implying this is universal; treat as environment-specific example path or normalize placeholders.

2. **State terminology is split across conceptual vs DB states**
- Lifecycle docs use `VALIDATING/SETTLING/WATCHING/EXITED`.
- SQL examples show persisted states like `confirmed/error/complete/exited`.
- README should explicitly separate conceptual runtime phases from persisted DB state values.

3. **Origin reference currently points outside this repo**
- Current README origin points at an external repository path.
- Souffleur has local archived design docs under `souffleur/docs/archive/`; README should prefer local references.

## Recommended README vNext Outline (Aligned with Musician/Dramaturg)

1. **Title + Role Narrative**
- Souffleur as external watchdog; how it complements Conductor internal monitoring and Musician stale-heartbeat detection.

2. **Souffleur vs Conductor Internal Monitoring vs Musician Detection**
- Comparison table clarifying ownership boundaries.

3. **How to Invoke**
- `/souffleur PID:$PID SESSION_ID:$SESSION_ID`.
- Clarify it is Conductor-launched in normal operation.

4. **How It Works**
- Three-layer monitoring model + timing constants.
- Event loop and state machine.

5. **Recovery Router and Providers**
- Lethe preflight preference.
- claude_export route and post-trim gate.
- Standard compact escalation and fail-closed policy.

6. **Payload and Configuration Contract**
- `CONTEXT_RECOVERY_PAYLOAD_V1` format.
- `FORCE_COMPACT` and `MAX_EXTERNAL_PERMISSION`.
- Permission clamp policy.

7. **Guardrails and Invariants**
- Ordering invariant.
- No double-relaunch.
- Watcher continuity.
- Opus-only subagent/teammate rule.

8. **Exit and Failure Policy**
- 3 terminal exit conditions.
- Retry-count semantics.
- Degraded heartbeat-only mode warning requirements.

9. **Database and Message Contract**
- Required `message_type` usage.
- Heartbeat update contract.
- Key warning/error/completion message types.

10. **Validation Script**
- `skill/scripts/validate-souffleur-state.sh` purpose and usage.

11. **Project Structure**
- Include `skill/references`, `skill/examples`, `skill/scripts`, and full `docs/{working,designs,archive}` shape.

12. **Known Limits / Planned Improvements**
- Conservative context estimation heuristic.
- Reliance on external tools (lethe availability, `claude_export`, kitty).

13. **Origin**
- Prefer local archived design docs, then optional external reference.

## Section-to-Source Mapping (for Rewrite Safety)

- Monitoring architecture: `skill/references/monitoring-architecture.md`
- Router/provider contracts: `skill/SKILL.md`, `skill/references/*-recovery-provider.md`, `skill/references/recovery-wrap-up.md`
- Payload + prompts: `skill/references/conductor-launch-prompts.md`, `skill/references/database-queries.md`
- Config + estimator details: `skill/scripts/souffleur-config.py`, `skill/scripts/souffleur-estimate-export.py`
- Validation behavior: `skill/scripts/validate-souffleur-state.sh`
- Historical rationale: `docs/archive/2026-02-26-*.md`, `docs/archive/2026-02-21-souffleur-design.md`

## Definition of Done for README Refresh

- [ ] README reflects current provider router behavior (Lethe -> claude_export -> standard compact).
- [ ] README documents post-trim export gate and escalation criteria.
- [ ] README includes three-layer monitoring timings and mode semantics.
- [ ] README includes payload/config contracts and permission ceiling behavior.
- [ ] README includes strict invariants (ordering, no double-relaunch, message_type).
- [ ] README structure matches current repository layout (including `docs/working` and `docs/designs`).
- [ ] README uses local source-of-truth references for origin/history.
- [ ] No contradictions with `skill/SKILL.md` and reference files.

## Bottom Line

Souffleur's README is not obsolete, but it is currently a concise summary where the project now needs an operator-grade contract document. A full rewrite to Musician/Dramaturg depth is justified and should be done in one pass against current skill references.
