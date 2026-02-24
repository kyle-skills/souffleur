# Souffleur — Conductor Watchdog Skill Design

**Date:** 2026-02-21
**Status:** Design approved
**Skill location:** `skills_staged/souffleur/`

---

## Overview

The Souffleur is an external watchdog skill that monitors the Conductor's liveness and relaunches it on failure with conversation context recovery. Named after the opera house prompter — the quiet figure who watches the performance from a booth and intervenes when something goes wrong.

The Conductor currently has internal monitoring (a background watcher that refreshes `task-00`'s heartbeat), and Musicians detect Conductor death via a 540-second staleness threshold. But nothing *external* relaunches the Conductor when it dies. The Souffleur fills this gap.

**Key properties:**
- Runs in its own kitty window, launched by the Conductor at orchestration start
- Lightweight — main session stays near-zero context by delegating all polling to subagents
- Self-healing — three monitoring layers ensure no blind windows
- Recovers Conductor context via `claude-export` and passes it to the replacement session

---

## Section 1: Identity & Invocation

**Invocation:** `/souffleur PID:$PID SESSION_ID:$SESSION_ID`

Launched by the Conductor at the start of an orchestration plan. Runs in its own kitty window as a full Claude Code session.

**Conductor launches Souffleur:**
```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Souffleur" -- \
  env -u CLAUDECODE claude --permission-mode acceptEdits \
  "/souffleur PID:$$ SESSION_ID:$CLAUDE_SESSION_ID" &
```

No PID file needed — the Conductor doesn't manage the Souffleur's lifecycle. The Souffleur outlives the Conductor by design.

**Table setup (Conductor's responsibility, before launching Souffleur):**
```sql
INSERT INTO orchestration_tasks (task_id, state, last_heartbeat)
VALUES ('souffleur', 'watching', datetime('now'));

INSERT INTO orchestration_tasks (task_id, state, last_heartbeat)
VALUES ('task-00', 'working', datetime('now'));
```

The `souffleur` row is created before `task-00`. This ensures the row exists when the Souffleur validates its args.

---

## Section 2: Bootstrap & Arg Validation

On launch, the Souffleur validates before settling:

1. **Parse args** — extract `PID` and `SESSION_ID` from the invocation string
2. **PID check** — `kill -0 $PID` confirms the Conductor process is alive
3. **Session ID check** — verify sentinel file exists: `~/.claude/projects/*/$SESSION_ID*.jsonl`
4. **Table check** — query comms-link for `souffleur` row existence

**On success:** Update row to `confirmed`
```sql
UPDATE orchestration_tasks
SET state = 'confirmed', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';
```

**On failure:** Update row to `error`, insert diagnostic message, wait for corrected args
```sql
UPDATE orchestration_tasks
SET state = 'error', last_heartbeat = datetime('now')
WHERE task_id = 'souffleur';

INSERT INTO orchestration_messages (task_id, from_session, message, message_type)
VALUES ('souffleur', '$CLAUDE_SESSION_ID',
    'SOUFFLEUR ERROR: Arg validation failed. [failure details]',
    'error');
```

### Validation Retry Loop

The Souffleur can't be relaunched by the Conductor — it must self-recover:

1. Set row to `error`, insert diagnostic message with what failed
2. Poll every ~30 seconds for Conductor's reply (`task_id = 'souffleur'` and `message_type = 'instruction'`)
3. Parse corrected args from the reply
4. Re-validate
5. On success → set `confirmed`, proceed to SETTLING
6. On failure → increment retry, set `error` again, insert new diagnostic, wait again

**After 3 failed attempts:** Set row to `exited`, insert terminal message, exit session.
```
SOUFFLEUR TERMINAL: Arg validation failed 3 times. Cannot recover.
Attempts: [summary of each failure reason]
Manual relaunch required.
```

---

## Section 3: Three-Layer Monitoring Architecture

Three layers ensure continuous monitoring with no blind windows.

### Layer 1 — Watcher (Background Subagent)

The primary monitoring loop. Polls the Conductor's liveness and maintains the Souffleur's own heartbeat as a side effect.

**Behavior:**
- **Initial wait:** ~240 seconds before first check (gives Conductor time to heartbeat after launch)
- **Poll cadence:** ~60 seconds
- **Each cycle:**
  1. Update Souffleur heartbeat: `UPDATE orchestration_tasks SET last_heartbeat = datetime('now') WHERE task_id = 'souffleur'`
  2. PID liveness check: `kill -0 $PID`
  3. Heartbeat staleness check: query `task-00` heartbeat, flag if >240 seconds stale
  4. Task count snapshot: count rows in `orchestration_tasks` (for retry reset tracking)
- **EXIT immediately** on detection. Report which trigger fired.

**Exit reasons:**

| Exit reason | Trigger |
|---|---|
| `CONDUCTOR_DEAD:pid` | PID dead |
| `CONDUCTOR_DEAD:heartbeat` | Heartbeat >240s stale |
| `SESSION_ID_FOUND:{id}` | New session ID on task-00 (only when `awaiting_session_id = true`) |
| `CONDUCTOR_COMPLETE` | task-00 state = `complete` |

**`awaiting_session_id` flag:** Only set to `true` when the Souffleur launches a watcher after a Conductor relaunch. On initial skill load and watcher re-launches for the same Conductor, the flag is `false`. This prevents infinite exit loops — the flag is `true` for exactly one watcher generation after each Conductor relaunch.

### Layer 2 — Teammate (Self-Monitor)

Watches the watcher. Ensures the background subagent hasn't crashed silently by monitoring the Souffleur heartbeat that the watcher maintains.

**Behavior:**
- **Initial wait:** ~360 seconds before first check (watcher needs its own initial wait + first poll)
- **Poll cadence:** ~180 seconds (3x slower than watcher)
- **Each cycle:** Query `souffleur` heartbeat. If >180 seconds stale (single missed watcher cycle), send message to Souffleur main session.
- **Never exits on its own.** Keeps nagging every 180 seconds until the heartbeat refreshes.
- **Only killed** by the Souffleur main session after a new watcher has been confirmed launched.

### Layer 3 — Souffleur Main Session

Orchestrates the other two layers. Sits idle between events.

**Two event types:**

| Event | Source | Meaning | Response |
|---|---|---|---|
| Watcher exits | Background subagent | See exit reason table | Route by reason |
| Teammate message | Teammate | Watcher is dead | Relaunch watcher, kill+relaunch teammate |

**Ordering invariant:** New watcher launches BEFORE old teammate is killed. At least one thing is always watching.

---

## Section 4: Conductor Relaunch Sequence

When the watcher exits with `CONDUCTOR_DEAD`:

### Step 1 — Kill Old Conductor
```bash
kill -0 $PID && kill $PID  # Only kill if still alive (zombie/frozen case)
```

### Step 2 — Export Conversation Log
```bash
claude-export $SESSION_ID
```
Output: `~/Documents/claude_exports/${SESSION_ID}_clean.md`

### Step 3 — Size Check & Truncation

Approximate 200k tokens as ~800k characters.

- **Under 800k chars:** Use as-is
- **Over 800k chars:** Truncate to preserve the "Files Modified" summary at the top + the most recent ~800k chars of conversation. Write the truncated version to the same path (overwrite).

### Step 4 — Launch New Conductor

```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Conductor (S{N})" -- \
  env -u CLAUDECODE claude --permission-mode acceptEdits "/conductor

Your previous Conductor session crashed or became unresponsive.

**Recovery context:** $EXPORT_PATH

Read this file first — it contains the conversation transcript from
your predecessor. The orchestration_tasks and orchestration_messages
tables in comms-link contain the current state of all tasks. Query
those to understand where things stand before resuming.

Your predecessor's session ID was: $OLD_SESSION_ID" &
echo $! > temp/souffleur-conductor.pid
```

Capture the new PID. The new session ID is unknown at launch — the watcher discovers it via the `awaiting_session_id` flag.

### Step 5 — Retry Tracking

- Increment retry counter
- Compare current task count (from watcher's last snapshot) against count at last Conductor launch
- If new tasks appeared since last launch: reset retry counter to 0
- **If retry counter hits 3:** Do not relaunch. Print alert and exit.

```
SOUFFLEUR: Conductor has crashed 3 consecutive times with no forward progress.
Last export: $EXPORT_PATH
Orchestration requires manual intervention.
```

### Step 6 — Relaunch Monitoring Layers

1. Launch new watcher subagent (`awaiting_session_id = true`, with new PID)
2. Kill old teammate
3. Launch new teammate
4. Return to idle

The new watcher's initial wait (~240s) gives the new Conductor time to bootstrap and start heartbeating.

---

## Section 5: Subagent & Teammate Prompts

### Watcher Subagent Prompt

```
Poll the Conductor's liveness every ~60 seconds using comms-link.

Conductor PID: {PID}
Conductor session ID: {SESSION_ID}
Awaiting session ID: {true|false}

**Initial wait:** Sleep ~240 seconds before your first check.

**Each poll cycle:**
1. Update Souffleur heartbeat:
   UPDATE orchestration_tasks SET last_heartbeat = datetime('now')
   WHERE task_id = 'souffleur'
2. PID check: kill -0 {PID}
3. Heartbeat check: query task-00 last_heartbeat, calculate staleness
4. Task count: SELECT COUNT(*) FROM orchestration_tasks
5. (Only if awaiting_session_id = true) Check task-00 session_id

**EXIT immediately and report reason when:**
- PID is dead → report: "CONDUCTOR_DEAD:pid"
- Heartbeat >240 seconds stale → report: "CONDUCTOR_DEAD:heartbeat"
- task-00 state = complete → report: "CONDUCTOR_COMPLETE"
- (Only if awaiting_session_id = true) task-00 session_id changed
  → report: "SESSION_ID_FOUND:{new_session_id}"

Do NOT exit for any other reason. Do NOT loop after detecting a
trigger. EXIT immediately so the Souffleur is notified.

Report the current task count in your exit message for retry tracking.
```

### Teammate (Self-Monitor) Prompt

```
You are the Souffleur's self-monitor. Your job is to ensure the
background watcher is alive by checking the Souffleur's heartbeat.

**Initial wait:** Sleep ~360 seconds before your first check.

**Each cycle (~180 seconds):**
1. Query souffleur heartbeat:
   SELECT last_heartbeat,
     (julianday('now') - julianday(last_heartbeat)) * 86400 AS age_seconds
   FROM orchestration_tasks WHERE task_id = 'souffleur'
2. If age_seconds > 180: send message —
   "WATCHER_DEAD: Souffleur heartbeat is {age_seconds}s stale.
    Watcher has likely crashed. Relaunch needed."

**Rules:**
- NEVER exit. Keep checking and messaging until you are shut down.
- If heartbeat recovers (new watcher launched), resume silent monitoring.
- If heartbeat stays stale, keep sending every ~180 seconds.
```

### Conductor Relaunch Prompt

```bash
kitty --directory /home/kyle/claude/remindly \
  --title "Conductor (S{N})" -- \
  env -u CLAUDECODE claude --permission-mode acceptEdits "/conductor

Your previous Conductor session crashed or became unresponsive.

**Recovery context:** {EXPORT_PATH}

Read this file first — it contains the conversation transcript from
your predecessor. The orchestration_tasks and orchestration_messages
tables in comms-link contain the current state of all tasks. Query
those to understand where things stand before resuming.

Your predecessor's session ID was: {OLD_SESSION_ID}" &
echo $! > temp/souffleur-conductor.pid
```

---

## Section 6: Event Loop & Lifecycle

### State Machine

```
VALIDATING → SETTLING → WATCHING → EXITED
                           ↑↓
                      (relaunch cycles)
```

| State | Description | Transitions to |
|---|---|---|
| **VALIDATING** | Parsing and validating args | SETTLING (success) or VALIDATING (retry with corrected args) or EXITED (3 failures) |
| **SETTLING** | Launching watcher + teammate, initial wait period | WATCHING |
| **WATCHING** | Idle. Waiting for watcher exit or teammate message. | WATCHING (after relaunch cycle) or EXITED (retry exhaustion or completion) |
| **EXITED** | Terminal. | — |

### Main Event Loop (WATCHING state)

```
┌─────────────────────────────────────────────┐
│              IDLE (waiting)                  │
└──────┬──────────────────┬───────────────────┘
       │                  │
  Watcher exits      Teammate messages
       │                  │
       ▼                  ▼
  Parse exit reason   WATCHER_DEAD
       │                  │
       ├─ CONDUCTOR_DEAD  ├── Launch new watcher
       │  → Relaunch seq  │   (same mode)
       │    (Section 4)   ├── Kill old teammate
       │  → New watcher   ├── Launch new teammate
       │    (awaiting)    │
       │  → Kill+relaunch │
       │    teammate      │
       │                  │
       ├─ SESSION_ID      │
       │  FOUND           │
       │  → Update ID     │
       │  → New watcher   │
       │    (normal)      │
       │                  │
       ├─ CONDUCTOR       │
       │  COMPLETE        │
       │  → Clean shutdown│
       │                  │
       ▼                  ▼
┌─────────────────────────────────────────────┐
│              IDLE (waiting)                  │
└─────────────────────────────────────────────┘
```

### Tracked State (in-session)

Minimal state held between cycles:

- `conductor_pid` — current Conductor PID (updated on relaunch)
- `conductor_session_id` — current Conductor session ID (updated on discovery)
- `retry_count` — consecutive Conductor deaths with no progress (reset on new tasks)
- `last_task_count` — task count at last Conductor launch (for retry reset comparison)
- `awaiting_session_id` — boolean, true after Conductor relaunch until discovered
- `relaunch_generation` — counter (S2, S3, etc.) for Conductor kitty window titles

### Exit Conditions

The Souffleur exits in exactly three scenarios:

1. **Arg validation failure (3 retries exhausted)** — sets `exited` on its row, inserts terminal message, exits
2. **Retry exhaustion** — 3 consecutive Conductor deaths with no forward progress. Prints alert, sets `error` on its row, exits.
3. **Conductor completes the plan** — watcher exits with `CONDUCTOR_COMPLETE`. Souffleur kills watcher and teammate, sets its row to `complete`, exits cleanly.

---

## Section 7: Error Recovery & Edge Cases

### Conductor dies during Souffleur bootstrap

The watcher hasn't launched yet, so no detection. But arg validation includes `kill -0 $PID` — if the Conductor is already dead, the PID check fails and enters the validation retry loop. If it dies after validation but before the watcher launches, the watcher's initial wait (~240s) covers this — by first check, the heartbeat is already stale.

### Souffleur's own context exhaustion

Unlikely given how little the main session does, but if it happens: the watcher and teammate are independent subagents — they keep running. The teammate will nag about a stale Souffleur heartbeat (since the main session can't respond). Without a Souffleur to relaunch anything, the system degrades to the Musicians' own 540-second staleness detection as the final safety net.

### Multiple watcher exits queued

If the watcher exits while the Souffleur is mid-relaunch from a teammate message, events are handled sequentially. The relaunch sequence is idempotent — killing an already-dead PID is a no-op, exporting the same session twice produces the same file, launching a new Conductor is always safe.

### comms-link unavailable

If the database is locked or unreachable, both watcher and teammate fail their queries. The watcher can't update the Souffleur heartbeat, so the teammate flags it. The Souffleur relaunches the watcher, which also fails. This loops until the database recovers. Bounded by the fact that each cycle is cheap and SQLite WAL locks are transient.

### Worst-case overlap scenario

Souffleur receives a `WATCHER_DEAD` message while mid-relaunch for a dead Conductor:
1. Conductor relaunch completes
2. New watcher launches (awaiting mode)
3. Old teammate killed, new teammate launches
4. Souffleur handles the queued `WATCHER_DEAD` message
5. Sees the watcher is already running (heartbeat is fresh) — no action needed

The natural handling is correct: the Souffleur checks current state before acting, and if a watcher is already running, the message is stale.
