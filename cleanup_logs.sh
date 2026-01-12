#!/bin/bash
#
# Log cleanup script for SMS Gateway API
# Deletes old log files based on retention settings
#

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR"
LOG_DIR="$PROJECT_DIR/logs"
CONFIG_FILE="$PROJECT_DIR/config.yaml"

# Default retention: 30 days
DEFAULT_RETENTION_DAYS=30

# Load retention from config.yaml
RETENTION_DAYS=$DEFAULT_RETENTION_DAYS
if [ -f "$CONFIG_FILE" ]; then
    # Try to read retention from config.yaml
    CONFIG_RETENTION=$(grep -A 5 "^server:" "$CONFIG_FILE" 2>/dev/null | grep -E "^\s+log_retention_days:\s*[0-9]+" | head -1 | sed 's/.*log_retention_days:\s*\([0-9]*\).*/\1/' || echo "")
    if [ -n "$CONFIG_RETENTION" ] && [ "$CONFIG_RETENTION" -gt 0 ] 2>/dev/null; then
        RETENTION_DAYS=$CONFIG_RETENTION
    fi
fi

# Check if log directory exists
if [ ! -d "$LOG_DIR" ]; then
    exit 0  # No log directory, nothing to do
fi

# Find and delete old log files
DELETED_COUNT=0
if [ -d "$LOG_DIR" ]; then
    # Find all .log files older than RETENTION_DAYS
    while IFS= read -r -d '' file; do
        if [ -f "$file" ]; then
            rm -f "$file"
            DELETED_COUNT=$((DELETED_COUNT + 1))
        fi
    done < <(find "$LOG_DIR" -name "*.log" -type f -mtime +$RETENTION_DAYS -print0 2>/dev/null)
fi

# Log the action (only if something was deleted)
if [ $DELETED_COUNT -gt 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Cleanup: $DELETED_COUNT old log file(s) deleted (Retention: ${RETENTION_DAYS} days)" >> "$LOG_DIR/cleanup.log" 2>/dev/null
fi

exit 0
