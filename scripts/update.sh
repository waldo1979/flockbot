#!/bin/bash
# Auto-update flockbot container if a newer image is available.
# Intended to be run by cron every 5 minutes.

set -euo pipefail

COMPOSE_DIR="$HOME/flockbot"
LOG_FILE="$COMPOSE_DIR/update.log"

cd "$COMPOSE_DIR"

# Resolve the image name from the compose file
IMAGE=$(docker compose config --images 2>/dev/null | head -1)
if [ -z "$IMAGE" ]; then
    echo "$(date -Iseconds) ERROR: Could not resolve image name" >> "$LOG_FILE"
    exit 1
fi

# Record current image ID before pulling
OLD_ID=$(docker image inspect "$IMAGE" --format '{{.Id}}' 2>/dev/null || echo "none")

# Pull latest image
docker compose pull -q flockbot 2>/dev/null

# Compare image IDs — if different, a new image was pulled
NEW_ID=$(docker image inspect "$IMAGE" --format '{{.Id}}' 2>/dev/null || echo "none")

if [ "$OLD_ID" != "$NEW_ID" ]; then
    echo "$(date -Iseconds) Updating flockbot..." >> "$LOG_FILE"
    docker compose up -d --remove-orphans flockbot >> "$LOG_FILE" 2>&1
    docker image prune -f >> "$LOG_FILE" 2>&1
    echo "$(date -Iseconds) Update complete." >> "$LOG_FILE"
fi
