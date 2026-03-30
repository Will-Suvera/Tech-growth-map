#!/bin/bash
# Automated refresh for GP Practice Growth Dashboard

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/refresh.log"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG_FILE"
cd "$PROJECT_DIR"
python3 "$SCRIPT_DIR/refresh_data.py" --waitlist >> "$LOG_FILE" 2>&1
python3 "$SCRIPT_DIR/snapshot.py" >> "$LOG_FILE" 2>&1
echo "" >> "$LOG_FILE"

tail -1000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
