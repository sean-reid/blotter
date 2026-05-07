#!/bin/bash
# Ping Redis and API, alert if down
NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)
[ -f /workspace/blotter/.env.secrets ] && set -a && source /workspace/blotter/.env.secrets && set +a
REDIS_PASS="${REDIS_PASSWORD:-}"

REDIS_OK=$(redis-cli -a "$REDIS_PASS" --no-auth-warning ping 2>/dev/null | grep -c PONG)
API_OK=$(curl -sf http://localhost:8080/api/health > /dev/null 2>&1 && echo 1 || echo 0)

if [ "$REDIS_OK" -eq 0 ] && [ -n "$NTFY_TOPIC" ]; then
  curl -s -d "Redis not responding to PING" \
    -H "Title: Redis down" -H "Priority: high" -H "Tags: warning" \
    "ntfy.sh/$NTFY_TOPIC" > /dev/null
fi

if [ "$API_OK" -eq 0 ] && [ -n "$NTFY_TOPIC" ]; then
  curl -s -d "API not responding on port 8080" \
    -H "Title: API down" -H "Priority: high" -H "Tags: warning" \
    "ntfy.sh/$NTFY_TOPIC" > /dev/null
fi
