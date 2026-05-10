#!/bin/bash
# Alert if any supervisord process is not RUNNING
NTFY_TOPIC=$(cat /workspace/blotter/.ntfy-secret 2>/dev/null)
CONF="/workspace/blotter/infra/supervisord/supervisord.conf"

STATUS=$(supervisorctl -c "$CONF" status 2>&1)
if echo "$STATUS" | grep -q "refused\|no such file"; then
  [ -n "$NTFY_TOPIC" ] && curl -s -d "supervisord unreachable" \
    -H "Title: Supervisord down" -H "Priority: urgent" -H "Tags: skull" \
    "ntfy.sh/$NTFY_TOPIC" > /dev/null
  exit 1
fi

# pg-restore exits normally after running once
FAILED=$(echo "$STATUS" | grep -v RUNNING | grep -v "pg-restore" | grep -v "^$")
if [ -n "$FAILED" ]; then
  MSG="$FAILED"
  TITLE="Process down"
  PRIO="high"
  # Check if pipeline died from TLS rejection
  if echo "$FAILED" | grep -q "pipeline" && \
     grep -q "TLS fingerprint rejected" /var/log/blotter-pipeline.log 2>/dev/null; then
    MSG="curl_cffi TLS fingerprint rejected 3x. Pipeline stopped to avoid IP ban."
    TITLE="Capture: TLS rejected"
    PRIO="urgent"
  fi
  [ -n "$NTFY_TOPIC" ] && curl -s -d "$MSG" \
    -H "Title: $TITLE" -H "Priority: $PRIO" -H "Tags: warning" \
    "ntfy.sh/$NTFY_TOPIC" > /dev/null
fi
