#!/bin/bash
# Log cgroup memory stats to persistent storage for post-crash analysis.
# Also alert via ntfy if usage exceeds threshold.
NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)
LOG="/workspace/blotter-memory.log"

# cgroup v1 memory
USAGE=$(cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null)
LIMIT=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null)
RSS=$(grep "^rss " /sys/fs/cgroup/memory/memory.stat 2>/dev/null | awk '{print $2}')
CACHE=$(grep "^cache " /sys/fs/cgroup/memory/memory.stat 2>/dev/null | awk '{print $2}')
INACTIVE_FILE=$(grep "^total_inactive_file " /sys/fs/cgroup/memory/memory.stat 2>/dev/null | awk '{print $2}')

if [ -z "$USAGE" ] || [ -z "$LIMIT" ]; then
  exit 0
fi

WORKING_SET=$(( USAGE - ${INACTIVE_FILE:-0} ))
USAGE_GB=$(awk "BEGIN {printf \"%.2f\", $USAGE/1024/1024/1024}")
LIMIT_GB=$(awk "BEGIN {printf \"%.2f\", $LIMIT/1024/1024/1024}")
RSS_GB=$(awk "BEGIN {printf \"%.2f\", ${RSS:-0}/1024/1024/1024}")
CACHE_GB=$(awk "BEGIN {printf \"%.2f\", ${CACHE:-0}/1024/1024/1024}")
WS_GB=$(awk "BEGIN {printf \"%.2f\", $WORKING_SET/1024/1024/1024}")
PCT=$(awk "BEGIN {printf \"%.0f\", $WORKING_SET*100/$LIMIT}")

# Per-process RSS (top 5)
TOP_PROCS=$(ps -eo rss,pid,comm --no-headers --sort=-rss | head -5 | awk '{printf "%s(pid%s,%dMB) ", $3, $2, $1/1024}')

# Thread counts for pipeline processes
THREAD_INFO=""
for PID in $(ps -eo pid,args --no-headers | grep "blotter stream start\|uvicorn blotter" | grep -v grep | grep -v "^.*uv run" | awk '{print $1}'); do
  TCOUNT=$(ls /proc/$PID/task 2>/dev/null | wc -l)
  TCOMM=$(cat /proc/$PID/comm 2>/dev/null)
  THREAD_INFO="$THREAD_INFO ${TCOMM}(pid${PID},${TCOUNT}t)"
done

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "$TS ws=${WS_GB}/${LIMIT_GB}GiB(${PCT}%) cgroup=${USAGE_GB}GiB rss=${RSS_GB}GiB cache=${CACHE_GB}GiB procs=[${TOP_PROCS}] threads=[${THREAD_INFO}]" >> "$LOG"

# Keep log from growing forever (last 2000 lines)
if [ $(wc -l < "$LOG") -gt 2000 ]; then
  tail -1000 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

# Alert if working set > 85%
if [ "$PCT" -gt 85 ] && [ -n "$NTFY_TOPIC" ]; then
  curl -s -d "Working set at ${PCT}% (${WS_GB}/${LIMIT_GB}GiB). RSS=${RSS_GB}GiB Cache=${CACHE_GB}GiB. Top: ${TOP_PROCS}" \
    -H "Title: High memory pressure" -H "Priority: high" -H "Tags: warning" \
    "ntfy.sh/$NTFY_TOPIC" > /dev/null
fi
