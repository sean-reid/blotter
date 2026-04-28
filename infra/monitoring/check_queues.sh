#!/bin/bash
# Track Redis queue depths, alert on transcription backlog
NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)
[ -f /workspace/blotter/.env.secrets ] && set -a && source /workspace/blotter/.env.secrets && set +a
REDIS_PASS="${REDIS_PASSWORD:-}"

CAPTURE_DEPTH=$(redis-cli -a "$REDIS_PASS" --no-auth-warning LLEN blotter:capture:chunks 2>/dev/null || echo 0)
TRANSCRIPT_DEPTH=$(redis-cli -a "$REDIS_PASS" --no-auth-warning LLEN blotter:transcribe:done 2>/dev/null || echo 0)

clickhouse-client -q \
  "INSERT INTO blotter.pipeline_metrics (metric, value) VALUES
   ('queue.capture.depth', ${CAPTURE_DEPTH:-0}),
   ('queue.transcript.depth', ${TRANSCRIPT_DEPTH:-0})" 2>/dev/null

if [ "${CAPTURE_DEPTH:-0}" -gt 30 ] && [ -n "$NTFY_TOPIC" ]; then
  curl -s -d "Transcription backlog: ${CAPTURE_DEPTH} chunks queued" \
    -H "Title: Transcription backlog" -H "Priority: high" -H "Tags: hourglass" \
    "ntfy.sh/$NTFY_TOPIC" > /dev/null
fi
