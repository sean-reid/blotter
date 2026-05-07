#!/bin/bash
# Alert if any supervisord process is not RUNNING
NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)
CONF="/workspace/blotter/infra/supervisord/supervisord.conf"

STATUS=$(supervisorctl -c "$CONF" status 2>/dev/null)
if [ $? -ne 0 ]; then
  [ -n "$NTFY_TOPIC" ] && curl -s -d "supervisord unreachable" \
    -H "Title: Supervisord down" -H "Priority: urgent" -H "Tags: skull" \
    "ntfy.sh/$NTFY_TOPIC" > /dev/null
  exit 1
fi

# pg-restore exits normally after running once
FAILED=$(echo "$STATUS" | grep -v RUNNING | grep -v "pg-restore" | grep -v "^$")
if [ -n "$FAILED" ]; then
  [ -n "$NTFY_TOPIC" ] && curl -s -d "$FAILED" \
    -H "Title: Process down" -H "Priority: high" -H "Tags: warning" \
    "ntfy.sh/$NTFY_TOPIC" > /dev/null
fi
