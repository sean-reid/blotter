#!/bin/bash
set -euo pipefail

REPO_DIR=/workspace/blotter
export GOOGLE_APPLICATION_CREDENTIALS=/workspace/blotter-gcs-key.json

# Load secrets (REDIS_PASSWORD, CLICKHOUSE_READONLY_PASSWORD)
SECRETS_FILE=/workspace/blotter/.env.secrets
if [ -f "$SECRETS_FILE" ]; then
  set -a; source "$SECRETS_FILE"; set +a
else
  echo "[WARN] No .env.secrets — Redis auth and CH password rotation disabled"
fi

echo "=== Blotter RunPod Start ==="

# Install system dependencies
apt-get update -qq
apt-get install -y -qq ffmpeg redis-server curl git > /dev/null 2>&1
echo "[OK] System packages"

# Install ClickHouse
if ! command -v clickhouse-server &>/dev/null; then
  curl -sSf https://clickhouse.com/ | sh
  ./clickhouse install 2>&1 | tail -3
  rm -f clickhouse
fi
echo "[OK] ClickHouse"

# Install cloudflared
if ! command -v cloudflared &>/dev/null; then
  curl -sSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
fi
echo "[OK] cloudflared"

# Install uv
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
echo "[OK] uv"

# Install supervisord (pip — available everywhere, no apt version issues)
pip install supervisor -q 2>/dev/null || pip3 install supervisor -q
echo "[OK] supervisord"

# Persistent ClickHouse data on network volume
mkdir -p /workspace/clickhouse-data /workspace/clickhouse-logs
[ -L /var/lib/clickhouse ] || (rm -rf /var/lib/clickhouse && ln -sf /workspace/clickhouse-data /var/lib/clickhouse)
[ -L /var/log/clickhouse-server ] || (rm -rf /var/log/clickhouse-server && ln -sf /workspace/clickhouse-logs /var/log/clickhouse-server)

# Clone/update repo
if [ -d "$REPO_DIR" ]; then
  cd "$REPO_DIR" && git pull 2>/dev/null
else
  git clone https://github.com/sean-reid/blotter.git "$REPO_DIR"
fi
echo "[OK] Repo"

# Install/sync Python backend
cd "$REPO_DIR/backend"
uv sync 2>/dev/null
echo "[OK] Python packages"

# Kill any leftover processes from previous runs
supervisorctl -c "$REPO_DIR/infra/supervisord/supervisord.conf" shutdown 2>/dev/null || true
pkill -f supervisord 2>/dev/null || true
pkill redis-server 2>/dev/null || true
pkill clickhouse-server 2>/dev/null || true
pkill cloudflared 2>/dev/null || true
sleep 1

# Start supervisord (runs in foreground via nodaemon=true, so background it)
supervisord -c "$REPO_DIR/infra/supervisord/supervisord.conf" &
echo "[OK] supervisord started"

# Wait for ClickHouse to be ready before running schema init
echo -n "Waiting for ClickHouse"
for i in $(seq 1 30); do
  if curl -s http://localhost:8123/ping > /dev/null 2>&1; then
    echo " ready!"
    break
  fi
  sleep 1
  echo -n "."
done

# Init schema (idempotent)
clickhouse-client --multiquery < "$REPO_DIR/infra/clickhouse/init.sql" 2>/dev/null

# Rotate readonly password if set in secrets
if [ -n "${CLICKHOUSE_READONLY_PASSWORD:-}" ]; then
  clickhouse-client --query "ALTER USER blotter_readonly IDENTIFIED BY '${CLICKHOUSE_READONLY_PASSWORD}'" 2>/dev/null
  echo "[OK] Schema + password rotated"
else
  echo "[OK] Schema"
fi

# Check tunnel credentials
if [ ! -f "$REPO_DIR/infra/cloudflared/credentials.json" ]; then
  echo "[WARN] No tunnel credentials — copy credentials.json to infra/cloudflared/"
fi

# Install monitoring crontab
chmod +x "$REPO_DIR"/infra/monitoring/*.sh
crontab "$REPO_DIR/infra/monitoring/crontab"
mkdir -p "$REPO_DIR/infra/monitoring/state"
echo "[OK] Monitoring crontab"

echo ""
echo "=== Blotter running at $(date) ==="
echo ""
echo "Management commands:"
echo "  supervisorctl -c $REPO_DIR/infra/supervisord/supervisord.conf status"
echo "  supervisorctl -c $REPO_DIR/infra/supervisord/supervisord.conf restart pipeline"
echo "  supervisorctl -c $REPO_DIR/infra/supervisord/supervisord.conf restart all"
echo "  supervisorctl -c $REPO_DIR/infra/supervisord/supervisord.conf tail -f pipeline"
