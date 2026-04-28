#!/bin/bash
# Hourly per-feed throughput tracking
clickhouse-client -q \
  "INSERT INTO blotter.pipeline_metrics (metric, value, tags)
   SELECT 'transcripts.hourly', count(), map('feed_id', feed_id)
   FROM blotter.scanner_transcripts
   WHERE created_at > now() - INTERVAL 1 HOUR
   GROUP BY feed_id" 2>/dev/null

clickhouse-client -q \
  "INSERT INTO blotter.pipeline_metrics (metric, value, tags)
   SELECT 'events.hourly', count(), map('feed_id', feed_id)
   FROM blotter.scanner_events
   WHERE created_at > now() - INTERVAL 1 HOUR
   GROUP BY feed_id" 2>/dev/null
