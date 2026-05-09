#!/bin/bash
# Single monitoring loop managed by supervisord.
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

  # Every 5 min: heartbeat, disk, queues, memory
  if [ $((TICK % 5)) -eq 0 ]; then
    bash "$DIR/heartbeat.sh" 2>/dev/null
    bash "$DIR/check_disk.sh" 2>/dev/null
    bash "$DIR/check_queues.sh" 2>/dev/null
    bash "$DIR/check_memory.sh" 2>/dev/null
  fi

  # Daily at ~16:00 UTC (9am PT)
  HOUR=$(date -u +%H)
  MIN=$(date -u +%M)
  if [ "$HOUR" = "16" ] && [ "$MIN" = "00" ]; then
    bash "$DIR/daily_summary.sh" 2>/dev/null
  fi

  sleep 60
done
