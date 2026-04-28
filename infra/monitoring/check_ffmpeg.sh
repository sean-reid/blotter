#!/bin/bash
# Track per-feed ffmpeg liveness
ALIVE=$(pgrep -af ffmpeg 2>/dev/null || true)
ALIVE_COUNT=$(echo "$ALIVE" | grep -c "blotter" 2>/dev/null || echo 0)

clickhouse-client -q \
  "INSERT INTO blotter.pipeline_metrics (metric, value) VALUES
   ('ffmpeg.alive_count', $ALIVE_COUNT)" 2>/dev/null

for FEED in 20296 33623 26569 40488 25187 24051; do
  if echo "$ALIVE" | grep -q "$FEED"; then
    V=1
  else
    V=0
  fi
  clickhouse-client -q \
    "INSERT INTO blotter.pipeline_metrics (metric, value, tags) VALUES
     ('ffmpeg.feed_alive', $V, map('feed_id', '$FEED'))" 2>/dev/null
done
