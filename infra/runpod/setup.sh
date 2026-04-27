#!/bin/bash
set -euo pipefail

REPO_DIR=/workspace/blotter
export GOOGLE_APPLICATION_CREDENTIALS=/workspace/blotter-gcs-key.json

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

# Persistent ClickHouse data on network volume
mkdir -p /workspace/clickhouse-data /workspace/clickhouse-logs
[ -L /var/lib/clickhouse ] || (rm -rf /var/lib/clickhouse && ln -sf /workspace/clickhouse-data /var/lib/clickhouse)
[ -L /var/log/clickhouse-server ] || (rm -rf /var/log/clickhouse-server && ln -sf /workspace/clickhouse-logs /var/log/clickhouse-server)

# Start services
redis-server --daemonize yes
clickhouse-server --daemon 2>/dev/null || true

echo -n "Waiting for ClickHouse"
for i in $(seq 1 30); do
  if curl -s http://localhost:8123/ping > /dev/null 2>&1; then
    echo " ready!"
    break
  fi
  sleep 1
  echo -n "."
done

# Clone/update repo
if [ -d "$REPO_DIR" ]; then
  cd "$REPO_DIR" && git pull 2>/dev/null
else
  git clone https://github.com/sean-reid/blotter.git "$REPO_DIR"
fi
echo "[OK] Repo"

# Init schema (idempotent)
clickhouse-client --multiquery < "$REPO_DIR/infra/clickhouse/init.sql" 2>/dev/null
echo "[OK] Schema"

# Start cloudflared tunnel with auto-restart loop
if [ -f "$REPO_DIR/infra/cloudflared/credentials.json" ]; then
  nohup bash -c 'while true; do cloudflared tunnel --config '"$REPO_DIR"'/infra/cloudflared/config.yml run 2>&1; echo "cloudflared exited, restarting in 5s..."; sleep 5; done' &>/var/log/cloudflared.log &
  echo "[OK] Tunnel"
else
  echo "[WARN] No tunnel credentials — copy credentials.json to infra/cloudflared/"
fi

# Install/sync Python backend
cd "$REPO_DIR/backend"
uv sync 2>/dev/null
echo "[OK] Python packages"

# Start pipeline
nohup uv run blotter stream start &>/var/log/blotter-pipeline.log &
echo "[OK] Pipeline started"

echo ""
echo "=== Blotter running at $(date) ==="
