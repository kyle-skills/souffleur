# Souffleur

Monitors Conductor liveness and relaunches it on failure with conversation context recovery. The Souffleur is the external watchdog in the orchestra-themed orchestration system: **Conductor** (coordination) > Musician (implementation) > Subagents (focused work), with the **Souffleur** watching from the wings.

## What It Does

- Validates Conductor PID and session ID at launch
- Monitors Conductor via three-layer architecture (watcher, self-monitor, main session)
- Relaunches Conductor on death with exported conversation context
- Tracks consecutive failures and alerts on retry exhaustion

## Structure

```
souffleur/
  skill/SKILL.md           # Skill definition (entry point)
  skill/examples/           # Launch, relaunch, discovery, completion workflows
  skill/references/         # Bootstrap, monitoring, relaunch, prompts, SQL
  skill/scripts/            # State validation
  docs/archive/             # Historical documents
```

## Usage

Launched by the Conductor at orchestration start via:
`/souffleur PID:$PID SESSION_ID:$SESSION_ID`

## Origin

Design doc: [kyle-skills/orchestration](https://github.com/kyle-skills/orchestration) `docs/designs/2026-02-21-souffleur-design.md`
