# Souffleur

Monitors Conductor liveness and recovers it on failure with provider-routed context recovery. The Souffleur is the external watchdog in the orchestra-themed orchestration system: **Conductor** (coordination) > Musician (implementation) > Subagents (focused work), with the **Souffleur** watching from the wings.

## What It Does

- Validates Conductor PID and session ID at launch
- Monitors Conductor via three-layer architecture (watcher, self-monitor, main session)
- Routes recovery through providers:
  - prefers Lethe compaction + relaunch when available
  - runs `claude_export` recovery with post-trim context gate
  - escalates to standard `/compact` recovery when export route is unavailable or still too large
- Supports degraded heartbeat-only monitoring mode when Lethe relaunch succeeds but PID cannot be resolved
- Tracks consecutive failures and alerts on retry exhaustion
- Enforces external launch permission ceiling via `.orchestra_configs/souffleur` (`MAX_EXTERNAL_PERMISSION`)

## Structure

```
souffleur/
  skill/SKILL.md           # Skill definition (entry point)
  skill/examples/           # Launch, provider routing, discovery, completion workflows
  skill/references/         # Bootstrap, monitoring, providers, wrap-up, prompts, SQL
  skill/scripts/            # State validation
  docs/archive/             # Historical documents
```

## Usage

Launched by the Conductor at orchestration start via:
`/souffleur PID:$PID SESSION_ID:$SESSION_ID`

## Origin

Design doc: [kyle-skills/orchestration](https://github.com/kyle-skills/orchestration) `docs/designs/2026-02-21-souffleur-design.md`
