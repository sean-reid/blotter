#!/bin/bash
# Single monitoring loop replacing crontab. Managed by supervisord.
# Runs checks at their original cron intervals using a tick counter.
# Tick = 60s. 2min checks run every 2 ticks, 5min every 5, etc.
set -a
[ -f /workspace/blotter/.env.secrets ] && source /workspace/blotter/.env.secrets
set +a

DIR="/workspace/blotter/infra/monitoring"
TICK=0

while true; do
  TICK=$((TICK + 1))

  # Every 2 min: process health, service pings
  if [ $((TICK % 2)) -eq 0 ]; then
    bash "$DIR/check_procs.sh" 2>/dev/null
    bash "$DIR/check_services.sh" 2>/dev/null
  fi

  # Every 5 min: heartbeat, disk, queues, resources + memory alert
  if [ $((TICK % 5)) -eq 0 ]; then
    bash "$DIR/heartbeat.sh" 2>/dev/null
    bash "$DIR/check_disk.sh" 2>/dev/null
    bash "$DIR/check_queues.sh" 2>/dev/null
    bash "$DIR/check_resources.sh" 2>/dev/null

    # Memory alert (not in original crontab)
    NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)
    TOTAL_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
    AVAIL_KB=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
    PCT_USED=$((( TOTAL_KB - AVAIL_KB ) * 100 / TOTAL_KB))
    AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
    TOTAL_GB=$((TOTAL_KB / 1024 / 1024))
    if [ "$PCT_USED" -gt 80 ] && [ -n "$NTFY_TOPIC" ]; then
      TOP=$(ps -eo rss,comm --no-headers | sort -nrk 1 | head -5 | awk '{printf "%s(%dMB) ", $2, $1/1024}')
      curl -s -d "Memory at ${PCT_USED}% (${AVAIL_GB}GB/${TOTAL_GB}GB free). Top: ${TOP}" \
        -H "Title: High memory usage" -H "Priority: high" -H "Tags: warning" \
        "ntfy.sh/$NTFY_TOPIC" > /dev/null
    fi
  fi

  # Every hour
  if [ $((TICK % 60)) -eq 0 ]; then
    bash "$DIR/check_throughput.sh" 2>/dev/null
  fi

  # Daily at ~16:00 UTC (9am PT) — check once per minute window
  HOUR=$(date -u +%H)
  MIN=$(date -u +%M)
  if [ "$HOUR" = "16" ] && [ "$MIN" = "00" ]; then
    bash "$DIR/daily_summary.sh" 2>/dev/null
  fi

  sleep 60
done
