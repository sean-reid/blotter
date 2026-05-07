#!/bin/bash
set -a
[ -f /workspace/blotter/backend/.env ] && source /workspace/blotter/backend/.env
[ -f /workspace/blotter/.env.secrets ] && source /workspace/blotter/.env.secrets
set +a
export PATH=/root/.local/bin:$PATH

pkill -9 redis-server 2>/dev/null
pkill -9 cloudflared 2>/dev/null
pkill -9 -f 'blotter stream' 2>/dev/null
pkill -9 -f multiprocessing 2>/dev/null
pkill supervisord 2>/dev/null
sleep 3
supervisord -c /workspace/blotter/infra/supervisord/supervisord.conf
sleep 5
supervisorctl -c /workspace/blotter/infra/supervisord/supervisord.conf status
