#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/personal/my_agentic_team/campsite-finder-agent"
LOG_DIR="$PROJECT_DIR/data/logs"
LOG_FILE="$LOG_DIR/daily-lock-scan.log"
TASK_BIN="/opt/homebrew/bin/task"
CDP_URL="http://localhost:9222"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') ReserveCalifornia lock scan start ====="

  if ! /usr/bin/curl -fsS "$CDP_URL/json/version" >/dev/null 2>&1; then
    echo "Chrome CDP is not responding on $CDP_URL; starting task chrome..."
    "$TASK_BIN" chrome >> "$LOG_FILE" 2>&1 &
    for _ in {1..30}; do
      if /usr/bin/curl -fsS "$CDP_URL/json/version" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  fi

  if ! /usr/bin/curl -fsS "$CDP_URL/json/version" >/dev/null 2>&1; then
    echo "Chrome CDP did not become ready on $CDP_URL."
    exit 1
  fi

  "$TASK_BIN" locks:reservecalifornia

  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') ReserveCalifornia lock scan complete ====="
  echo
} >> "$LOG_FILE" 2>&1
