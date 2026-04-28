#!/bin/bash
# Alert on disk usage >90% and orphan audio chunks
NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)

for MOUNT in / /workspace /tmp; do
  PCT=$(df "$MOUNT" 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%')
  [ -z "$PCT" ] && continue
  clickhouse-client -q \
    "INSERT INTO blotter.pipeline_metrics (metric, value, tags) VALUES
     ('disk.usage_pct', $PCT, map('mount', '$MOUNT'))" 2>/dev/null
  if [ "$PCT" -gt 90 ] && [ -n "$NTFY_TOPIC" ]; then
    curl -s -d "Disk at ${PCT}% on $MOUNT" \
      -H "Title: Disk full" -H "Priority: high" -H "Tags: floppy_disk" \
      "ntfy.sh/$NTFY_TOPIC" > /dev/null
  fi
done

ORPHANS=$(find /tmp/blotter -name "*.wav" -mmin +30 2>/dev/null | wc -l | tr -d ' ')
if [ "${ORPHANS:-0}" -gt 20 ] && [ -n "$NTFY_TOPIC" ]; then
  curl -s -d "$ORPHANS orphan WAV chunks >30min old. GCS upload may be failing." \
    -H "Title: Chunk cleanup stalled" -H "Priority: default" -H "Tags: warning" \
    "ntfy.sh/$NTFY_TOPIC" > /dev/null
fi
