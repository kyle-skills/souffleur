# Souffleur: Watching from the Wings

In opera, the souffleur sits in a small booth at the front of the stage, hidden from the audience but visible to the performers. Their job is singular: watch for trouble and intervene before it derails the performance. When a singer loses their place, the souffleur whispers the next line. They don't perform, don't interpret, don't direct — they watch, and when something goes wrong, they get the show back on track.

The `souffleur` skill fills the same role in the orchestration pipeline. It monitors the Conductor's liveness from an external session and recovers it on failure — choosing the lightest viable recovery path, relaunching with preserved context, and resuming monitoring. The Souffleur does not perform implementation work. It watches, recovers, and exits.

## Souffleur vs Conductor Internal Monitoring vs Musician Detection

| | Souffleur | Conductor internal watcher | Musician stale detection |
|---|---|---|---|
| **Runs in** | Dedicated external session | Background subagent within Conductor | Within each Musician session |
| **Watches** | Conductor PID + heartbeat | Task-00 heartbeat refresh | Conductor heartbeat staleness |
| **Detects** | Conductor death, context exhaustion, completion | Own heartbeat refresh failure | Conductor gone >540 seconds |
| **Recovers** | Yes — provider-routed relaunch | No — it is the thing that died | No — Musicians exit gracefully |
| **Outlives Conductor** | Yes, by design | No — dies with Conductor | Independent lifecycle |

## Pipeline Position

The Souffleur operates outside the main pipeline. It does not produce plans, execute tasks, or communicate with Musicians. It watches the Conductor and restores it when it fails.

```
Dramaturg → Arranger → Conductor → Musician
(design)    (plan)     (orchestrate) (implement)
                           ↑
                       Souffleur (external watchdog, recovery on failure)
```

## Usage

Launched by the Conductor at orchestration start:

```
/souffleur PID:$PID SESSION_ID:$SESSION_ID
```

The Conductor creates the `souffleur` row in `orchestration_tasks` before launching. Only one Souffleur session runs at a time — the Souffleur outlives the Conductor by design and persists across Conductor recovery cycles.

## How It Works

### Lifecycle

```
VALIDATING → SETTLING → WATCHING → EXITED
                           ↑↓
                      (recovery cycles)
```

**VALIDATING** — Parse `PID` and `SESSION_ID` from invocation, then run three checks in order: PID liveness (`kill -0`), session sentinel file existence, and `souffleur` row presence in comms-link. On failure, retry up to 3 times with Conductor-provided corrections.

**SETTLING** — Launch the three-layer monitoring stack (watcher, teammate, main session) and wait for initial settling periods before active monitoring begins.

**WATCHING** — Idle between events. Routes watcher exits and teammate messages to recovery providers or clean shutdown. This is the steady state — the Souffleur spends nearly all its time here.

**EXITED** — Terminal. Reached via validation exhaustion, retry exhaustion, or Conductor completion.

### Three-Layer Monitoring

Three layers ensure continuous monitoring with no blind windows:

| Layer | Type | Role | Timing |
|---|---|---|---|
| **Watcher** | Background subagent | Polls Conductor PID + heartbeat, updates Souffleur heartbeat | ~60s cadence after ~240s initial wait |
| **Teammate** | Foreground teammate | Monitors watcher via Souffleur heartbeat staleness | ~180s cadence after ~360s initial wait |
| **Main session** | This session | Routes events, orchestrates recoveries | Event-driven (idle between events) |

The watcher's heartbeat update is both its primary side effect and the teammate's detection mechanism. If the watcher dies silently, the heartbeat goes stale and the teammate detects it within one cycle.

**Watcher modes:**
- **Normal** — PID liveness check + heartbeat staleness + task state. Used when `conductor_pid` is known.
- **Heartbeat-only** — Skips PID check, relies on heartbeat and task state. Used when a relaunch succeeded but PID could not be resolved. Degraded but functional.

### Event Routing

| Event | Trigger | Action |
|---|---|---|
| `CONDUCTOR_DEAD:pid` | PID check failed | Recovery via claude_export, then standard compact if gate fails |
| `CONDUCTOR_DEAD:heartbeat` | Heartbeat >240s stale | Recovery via claude_export, then standard compact if gate fails |
| `CONTEXT_RECOVERY` | task-00 state = `context_recovery` | Recovery router (Lethe preferred, claude_export, standard compact) |
| `SESSION_ID_FOUND:{id}` | New session ID discovered | Update session ID, relaunch watcher in normal mode |
| `CONDUCTOR_COMPLETE` | task-00 state = `complete` | Clean shutdown |
| `WATCHER_DEAD` (teammate) | Souffleur heartbeat stale | Relaunch watcher, kill + relaunch teammate |

## Recovery Router and Providers

When recovery is needed, the router selects a provider based on availability and event type.

### Router Sequence

1. Resolve payload and configuration
2. Run Lethe preflight (soft dependency check)
3. If preflight passes: Lethe provider
4. If preflight fails: claude_export provider
5. If claude_export gate exceeds threshold: standard compact provider

Providers are mutually exclusive per recovery cycle. The `active_recovery_provider` guard prevents double-relaunch — once Lethe starts a new Conductor generation, claude_export cannot execute in the same cycle.

### Provider Summary

| Provider | Strategy | When selected |
|---|---|---|
| **Lethe** (preferred) | Compaction via Lethe teammate, autonomous relaunch | `CONTEXT_RECOVERY` event when Lethe is available |
| **claude_export** (fallback) | Kill, export transcript, trim, estimate context, launch or escalate | Crash/death events, or Lethe preflight failure |
| **standard compact** (escalation) | In-place `/compact` on original session, then `--resume` | claude_export gate threshold exceeded, or export path unavailable |

### Post-Trim Estimation Gate

The claude_export provider includes a context gate before relaunch. After trimming the export artifact, the estimator (`souffleur-estimate-export.py`) calculates `chars / 3` from the latest compact marker (or full file if none). If the estimate exceeds the `FORCE_COMPACT` threshold, the export artifact is discarded and recovery escalates to standard compact.

### Shared Wrap-Up

After any provider completes, shared wrap-up handles retry tracking, session ID mode resolution, and monitoring layer relaunch. Retry count increments when no new tasks appeared between recoveries; it resets when progress is detected. Three consecutive no-progress recoveries trigger exit.

## Configuration

Configuration is resolved via `skill/scripts/souffleur-config.py` from `.orchestra_configs/souffleur`:

| Key | Default | Purpose |
|---|---|---|
| `FORCE_COMPACT` | `400000` | Token threshold for post-trim export gate |
| `MAX_EXTERNAL_PERMISSION` | `acceptEdits` | Permission ceiling for launched sessions |

Launch permissions are clamped: `effective = min(requested, MAX_EXTERNAL_PERMISSION)`.

### Context-Recovery Payload

The Conductor can include recovery instructions via a tagged message:

```
CONTEXT_RECOVERY_PAYLOAD_V1
permission_mode: <value>
resume_prompt: <value>
```

Both fields are optional. Missing or malformed payloads are non-fatal — recovery proceeds with defaults. Default recovery prompt begins with `/conductor --recovery-bootstrap`.

## Guardrails and Invariants

| Invariant | Detail |
|---|---|
| **Ordering** | New watcher launches BEFORE old teammate is killed — at least one monitor always active |
| **No double-relaunch** | `active_recovery_provider` guard prevents two providers from launching in the same cycle |
| **PID safety** | Always `kill -0` before `kill` — never kill blindly |
| **Opus only** | All subagents and teammates use `model="opus"` |
| **Near-zero context** | Main session delegates all polling to subagents — stays idle between events |
| **Watcher continuity** | A watcher must always be running while in WATCHING state |
| **Database protocol** | comms-link MCP for all DB ops, `message_type` on every INSERT, `last_heartbeat` on every state transition |

## Exit Conditions

The Souffleur exits in exactly three scenarios:

| Condition | Trigger | Action |
|---|---|---|
| **Arg validation failure** | 3 retries exhausted | Set state to `exited`, insert terminal message, exit |
| **Retry exhaustion** | 3 consecutive Conductor deaths with no task progress | Set state to `error`, print alert, exit |
| **Conductor completion** | Watcher reports `CONDUCTOR_COMPLETE` | Kill teammate, set state to `complete`, exit cleanly |

No other scenario causes the Souffleur to exit. Watcher deaths and teammate messages result in relaunches, not exits.

## Validation Script

```bash
bash skill/scripts/validate-souffleur-state.sh [PID]
```

Spot-checks database consistency for the Souffleur row. Optional PID argument for targeted Conductor validation.

## Project Structure

```
souffleur/
├── skill/
│   ├── SKILL.md                                    # Skill definition (entry point)
│   ├── references/
│   │   ├── bootstrap-validation.md                 # Arg parsing, validation checks, retry loop
│   │   ├── monitoring-architecture.md              # Three-layer model, watcher modes, timing
│   │   ├── subagent-prompts.md                     # Verbatim watcher and teammate prompts
│   │   ├── lethe-recovery-provider.md              # Lethe preflight, launch, PID resolution
│   │   ├── claude-export-recovery-provider.md      # Export, trim, gate, launch-or-escalate
│   │   ├── standard-compact-recovery-provider.md   # In-place compact, retry, fail-closed
│   │   ├── recovery-wrap-up.md                     # Shared post-provider sequence
│   │   ├── conductor-launch-prompts.md             # Default prompts and launch templates
│   │   ├── conductor-relaunch.md                   # Relaunch mechanics
│   │   └── database-queries.md                     # SQL patterns and message templates
│   ├── examples/
│   │   ├── example-initial-launch.md               # Bootstrap-to-WATCHING walkthrough
│   │   ├── example-context-recovery.md             # Lethe-primary recovery flow
│   │   ├── example-export-gate-escalation.md       # Export threshold escalation
│   │   ├── example-standard-compact-fail-closed.md # Compact retry exhaustion
│   │   ├── example-conductor-relaunch.md           # Relaunch mechanics
│   │   ├── example-session-id-discovery.md         # Session ID rediscovery
│   │   ├── example-clean-completion.md             # Conductor completes plan
│   │   ├── example-lethe-missing-pid-degraded-mode.md  # Heartbeat-only fallback
│   │   ├── example-preflight-failure-fallback.md   # Lethe unavailable
│   │   └── example-lethe-provider-fallback.md      # Lethe launch failure
│   └── scripts/
│       ├── validate-souffleur-state.sh             # Database consistency check
│       ├── souffleur-config.py                     # Config resolution from .orchestra_configs
│       └── souffleur-estimate-export.py            # Post-trim context estimation
└── docs/
    ├── archive/                                    # Historical design documents
    ├── designs/                                    # Design specifications
    └── working/                                    # Active design work
```

## Requirements

- **comms-link MCP** (mandatory — database communication for monitoring and state)
- **Claude Code** with skill/plugin support
- **Lethe skill** (desired — preferred recovery provider; claude_export + standard compact fallback if unavailable)

## Known Limits

- Context estimation uses `chars / 3` heuristic, not exact token counts — errs conservative
- Heartbeat-only mode disables PID liveness checks until a future recovery cycle restores a known PID
- Standard compact failure policy is fail-closed after one retry — no further recovery attempts in that cycle
- Hardcoded project paths in some reference templates require environment-specific adaptation

## Origin

Part of [The Elevated Stage](https://github.com/The-Elevated-Stage) orchestration system. Design doc: `docs/archive/2026-02-21-souffleur-design.md`.
