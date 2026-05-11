#!/bin/bash
# Daily digest notification
NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)
[ -z "$NTFY_TOPIC" ] && exit 0
[ -f /workspace/blotter/.env.secrets ] && set -a && source /workspace/blotter/.env.secrets && set +a

export PGPASSWORD="${POSTGRES_PASSWORD:-}"
PG="psql -h localhost -U blotter -d blotter -tAc"

EVENTS=$($PG "SELECT count(*) FROM scanner_events WHERE created_at > now() - interval '24 hours'" 2>/dev/null || echo "?")
TRANSCRIPTS=$($PG "SELECT count(*) FROM scanner_transcripts WHERE created_at > now() - interval '24 hours'" 2>/dev/null || echo "?")
FEEDS=$($PG "SELECT count(DISTINCT feed_id) FROM scanner_transcripts WHERE created_at > now() - interval '24 hours'" 2>/dev/null || echo "?")
DISK=$(df -h /workspace 2>/dev/null | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')

curl -s -d "24h: ${EVENTS} events, ${TRANSCRIPTS} transcripts, ${FEEDS} feeds
Disk: $DISK" \
  -H "Title: Blotter daily digest" -H "Priority: low" -H "Tags: bar_chart" \
  "ntfy.sh/$NTFY_TOPIC" > /dev/null
