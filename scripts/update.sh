#!/bin/bash
# Auto-update flockbot container if a newer image is available.
# Intended to be run by cron every 5 minutes.

set -euo pipefail

COMPOSE_DIR="$HOME/flockbot"
LOG_FILE="$COMPOSE_DIR/update.log"

cd "$COMPOSE_DIR"

# Pull latest image, capture output
PULL_OUTPUT=$(docker compose pull flockbot 2>&1)

# Only restart if a new image was pulled
if echo "$PULL_OUTPUT" | grep -q "Downloaded newer image"; then
    echo "$(date -Iseconds) Updating flockbot..." >> "$LOG_FILE"
    docker compose up -d --remove-orphans flockbot >> "$LOG_FILE" 2>&1
    docker image prune -f >> "$LOG_FILE" 2>&1
    echo "$(date -Iseconds) Update complete." >> "$LOG_FILE"
fi
