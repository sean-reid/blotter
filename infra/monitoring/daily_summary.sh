#!/bin/bash
# Daily digest notification
NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)
[ -z "$NTFY_TOPIC" ] && exit 0

EVENTS=$(clickhouse-client -q \
  "SELECT count() FROM blotter.scanner_events WHERE created_at > now() - INTERVAL 24 HOUR" 2>/dev/null || echo "?")
TRANSCRIPTS=$(clickhouse-client -q \
  "SELECT count() FROM blotter.scanner_transcripts WHERE created_at > now() - INTERVAL 24 HOUR" 2>/dev/null || echo "?")
FEEDS=$(clickhouse-client -q \
  "SELECT uniq(feed_id) FROM blotter.scanner_transcripts WHERE created_at > now() - INTERVAL 24 HOUR" 2>/dev/null || echo "?")
DISK=$(df -h /workspace 2>/dev/null | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')

curl -s -d "24h: ${EVENTS} events, ${TRANSCRIPTS} transcripts, ${FEEDS} feeds
Disk: $DISK" \
  -H "Title: Blotter daily digest" -H "Priority: low" -H "Tags: bar_chart" \
  "ntfy.sh/$NTFY_TOPIC" > /dev/null
