#!/bin/bash
# Alert if the pipeline stops producing transcripts or events
NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)
STATE_DIR="/workspace/blotter/infra/monitoring/state"
mkdir -p "$STATE_DIR"
[ -f /workspace/blotter/.env.secrets ] && set -a && source /workspace/blotter/.env.secrets && set +a

export PGPASSWORD="${POSTGRES_PASSWORD:-}"
PG="psql -U blotter -d blotter -tAc"

TRANSCRIPT_COUNT=$($PG "SELECT count(*) FROM scanner_transcripts WHERE created_at > now() - interval '15 minutes'" 2>/dev/null || echo -1)
EVENT_COUNT=$($PG "SELECT count(*) FROM scanner_events WHERE created_at > now() - interval '15 minutes'" 2>/dev/null || echo -1)

if [ "${TRANSCRIPT_COUNT}" -eq 0 ]; then
  PREV=$(cat "$STATE_DIR/transcript_zero" 2>/dev/null || echo 0)
  echo $((PREV + 1)) > "$STATE_DIR/transcript_zero"
  if [ "$PREV" -ge 1 ] && [ -n "$NTFY_TOPIC" ]; then
    curl -s -d "0 transcripts in last 15 min (2 consecutive checks)" \
      -H "Title: Pipeline down" -H "Priority: urgent" -H "Tags: rotating_light" \
      "ntfy.sh/$NTFY_TOPIC" > /dev/null
  fi
else
  echo 0 > "$STATE_DIR/transcript_zero"
fi

if [ "${EVENT_COUNT}" -eq 0 ] && [ "${TRANSCRIPT_COUNT}" -gt 0 ]; then
  PREV=$(cat "$STATE_DIR/event_zero" 2>/dev/null || echo 0)
  echo $((PREV + 1)) > "$STATE_DIR/event_zero"
  if [ "$PREV" -ge 2 ] && [ -n "$NTFY_TOPIC" ]; then
    curl -s -d "Transcripts flowing but 0 events in 15 min. NLP/geocoder may be broken." \
      -H "Title: Processing stalled" -H "Priority: high" -H "Tags: warning" \
      "ntfy.sh/$NTFY_TOPIC" > /dev/null
  fi
else
  echo 0 > "$STATE_DIR/event_zero"
fi
