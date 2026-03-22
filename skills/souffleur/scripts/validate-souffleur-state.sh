#!/bin/bash
# validate-souffleur-state.sh
#
# Validates database consistency for the Souffleur watchdog.
# Run by the Souffleur at any time, or by the Conductor to spot-check.
#
# Usage: bash validate-souffleur-state.sh [conductor_pid]
#   conductor_pid — Optional; check PID liveness if provided
#
# Note: Uses sqlite3 directly (not comms-link) because this script runs
# outside Claude Code sessions where MCP tools are unavailable.
#
# Exit codes: 0 = healthy, 1 = issues found

set -euo pipefail

# --- Arguments ---
CONDUCTOR_PID="${1:-}"

# --- Config ---
PROJECT_DIR="${PROJECT_DIR:-/home/kyle/claude/remindly}"
DB_PATH="${DB_PATH:-$PROJECT_DIR/comms.db}"

# Valid states for the souffleur row
VALID_STATES="watching confirmed working error complete exited"

# Valid states for the conductor (task-00) row
VALID_CONDUCTOR_STATES="pending confirmed working complete error context_recovery exited"

ISSUES=0

# --- Helper: query DB ---
db_query() {
  sqlite3 -separator '|' "$DB_PATH" "$1" 2>/dev/null
}

# --- Check: DB exists ---
if [[ ! -f "$DB_PATH" ]]; then
  echo "=== Souffleur State Validation ==="
  echo "ERROR: Database not found at $DB_PATH"
  echo "=== RESULT: DB MISSING ==="
  exit 1
fi

echo "=== Souffleur State Validation ==="

# --- Check 1: Souffleur row exists ---
ROW=$(db_query "SELECT task_id, state, last_heartbeat FROM orchestration_tasks WHERE task_id='souffleur';")

if [[ -z "$ROW" ]]; then
  echo "ERROR: No souffleur row in orchestration_tasks"
  echo "=== RESULT: ROW NOT FOUND ==="
  exit 1
fi

# Parse fields
IFS='|' read -r S_ID S_STATE S_HEARTBEAT <<< "$ROW"

echo "State:      $S_STATE"

# --- Check 2: State validity ---
STATE_VALID=false
for s in $VALID_STATES; do
  if [[ "$S_STATE" == "$s" ]]; then
    STATE_VALID=true
    break
  fi
done
if [[ "$STATE_VALID" == "false" ]]; then
  echo "State:      WARNING — '$S_STATE' is not a recognized souffleur state"
  ISSUES=$((ISSUES + 1))
fi

# --- Check 3: Souffleur heartbeat freshness ---
if [[ -n "$S_HEARTBEAT" && "$S_HEARTBEAT" != "null" ]]; then
  AGE_SECONDS=$(db_query "SELECT CAST((julianday('now') - julianday('$S_HEARTBEAT')) * 86400 AS INTEGER);")
  AGE_SECONDS="${AGE_SECONDS:-0}"

  if [[ $AGE_SECONDS -lt 180 ]]; then
    HB_STATUS="OK"
  elif [[ $AGE_SECONDS -lt 240 ]]; then
    HB_STATUS="STALE"
    ISSUES=$((ISSUES + 1))
  else
    HB_STATUS="ALARM"
    ISSUES=$((ISSUES + 1))
  fi
  echo "Heartbeat:  $S_HEARTBEAT (${AGE_SECONDS}s ago) [$HB_STATUS]"
else
  echo "Heartbeat:  <never set>"
  if [[ "$S_STATE" == "confirmed" || "$S_STATE" == "working" ]]; then
    ISSUES=$((ISSUES + 1))
  fi
fi

# --- Check 4: Conductor (task-00) row exists ---
C_ROW=$(db_query "SELECT task_id, state, last_heartbeat FROM orchestration_tasks WHERE task_id='task-00';")

if [[ -z "$C_ROW" ]]; then
  echo "Conductor:  WARNING — no task-00 row found"
  ISSUES=$((ISSUES + 1))
else
  IFS='|' read -r C_ID C_STATE C_HEARTBEAT <<< "$C_ROW"
  echo "Conductor:  state=$C_STATE"

  # --- Check 5a: Conductor state validity ---
  C_STATE_VALID=false
  for s in $VALID_CONDUCTOR_STATES; do
    if [[ "$C_STATE" == "$s" ]]; then
      C_STATE_VALID=true
      break
    fi
  done
  if [[ "$C_STATE_VALID" == "false" ]]; then
    echo "Conductor:  WARNING — '$C_STATE' is not a recognized conductor state"
    ISSUES=$((ISSUES + 1))
  fi
  if [[ "$C_STATE" == "context_recovery" ]]; then
    echo "Conductor:  NOTE — context_recovery state active (relaunch expected)"
  fi

  # --- Check 5b: Conductor heartbeat freshness ---
  if [[ -n "$C_HEARTBEAT" && "$C_HEARTBEAT" != "null" ]]; then
    C_AGE=$(db_query "SELECT CAST((julianday('now') - julianday('$C_HEARTBEAT')) * 86400 AS INTEGER);")
    C_AGE="${C_AGE:-0}"

    if [[ $C_AGE -lt 240 ]]; then
      C_HB_STATUS="OK"
    elif [[ $C_AGE -lt 540 ]]; then
      C_HB_STATUS="STALE"
      ISSUES=$((ISSUES + 1))
    else
      C_HB_STATUS="ALARM"
      ISSUES=$((ISSUES + 1))
    fi
    echo "Cond HB:    $C_HEARTBEAT (${C_AGE}s ago) [$C_HB_STATUS]"
  else
    echo "Cond HB:    <never set>"
    if [[ "$C_STATE" == "working" ]]; then
      ISSUES=$((ISSUES + 1))
    fi
  fi
fi

# --- Check 6: Conductor PID liveness (optional) ---
if [[ -n "$CONDUCTOR_PID" ]]; then
  if kill -0 "$CONDUCTOR_PID" 2>/dev/null; then
    echo "Cond PID:   $CONDUCTOR_PID [ALIVE]"
  else
    echo "Cond PID:   $CONDUCTOR_PID [DEAD]"
    ISSUES=$((ISSUES + 1))
  fi
else
  echo "Cond PID:   (not provided)"
fi

# --- Check 7: Recent messages ---
MSG_COUNT=$(db_query "SELECT COUNT(*) FROM orchestration_messages WHERE task_id='souffleur';")
echo "Messages:   ${MSG_COUNT:-0} total for souffleur"

RECENT=$(db_query "SELECT message_type, substr(message, 1, 80) FROM orchestration_messages WHERE task_id='souffleur' ORDER BY timestamp DESC LIMIT 1;")
if [[ -n "$RECENT" ]]; then
  echo "Latest:     $RECENT"
fi

# --- Result ---
if [[ $ISSUES -eq 0 ]]; then
  echo "=== RESULT: HEALTHY ==="
  exit 0
else
  echo "=== RESULT: ISSUES FOUND ($ISSUES) ==="
  exit 1
fi
