#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/Users/bfoster/Documents/my_agentic_team/campsite-finder-agent"
LOG_DIR="$PROJECT_DIR/data/logs"
LOG_FILE="$LOG_DIR/hourly-scan.log"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') campsite scan start ====="
  /opt/homebrew/bin/uv run python app.py \
    --once \
    --save-data \
    --use-saved-data \
    --request-delay-seconds 5 \
    --max-retries 8
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') campsite scan complete ====="
  echo
} >> "$LOG_FILE" 2>&1
