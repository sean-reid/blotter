#!/bin/bash
# Ping Redis and ClickHouse, alert if Redis is down
NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)
[ -f /workspace/blotter/.env.secrets ] && set -a && source /workspace/blotter/.env.secrets && set +a
REDIS_PASS="${REDIS_PASSWORD:-}"

CH_OK=$(curl -sf http://localhost:8123/ping > /dev/null 2>&1 && echo 1 || echo 0)
REDIS_OK=$(redis-cli -a "$REDIS_PASS" --no-auth-warning ping 2>/dev/null | grep -c PONG)

clickhouse-client -q \
  "INSERT INTO blotter.pipeline_metrics (metric, value) VALUES
   ('service.clickhouse_up', $CH_OK),
   ('service.redis_up', $REDIS_OK)" 2>/dev/null

if [ "$REDIS_OK" -eq 0 ] && [ -n "$NTFY_TOPIC" ]; then
  curl -s -d "Redis not responding to PING" \
    -H "Title: Redis down" -H "Priority: high" -H "Tags: warning" \
    "ntfy.sh/$NTFY_TOPIC" > /dev/null
fi
