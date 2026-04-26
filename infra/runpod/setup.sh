#!/bin/bash
set -euo pipefail

echo "=== Blotter RunPod Setup ==="

# Install system dependencies
apt-get update -qq
apt-get install -y -qq ffmpeg docker.io docker-compose redis-server curl git > /dev/null 2>&1
echo "[OK] System packages installed"

# Start Docker
service docker start || true
echo "[OK] Docker started"

# Start Redis
service redis-server start || true
echo "[OK] Redis started"

# Clone/update repo
if [ -d /workspace/blotter ]; then
  cd /workspace/blotter && git pull
else
  git clone https://github.com/sean-reid/blotter.git /workspace/blotter
fi
cd /workspace/blotter
echo "[OK] Repo ready"

# Start ClickHouse + cloudflared via Docker Compose
cd /workspace/blotter/infra
docker-compose up -d clickhouse cloudflared
echo "[OK] ClickHouse + cloudflared running"

# Wait for ClickHouse
echo -n "Waiting for ClickHouse..."
for i in $(seq 1 30); do
  if curl -s http://localhost:8123/ping > /dev/null 2>&1; then
    echo " ready"
    break
  fi
  sleep 1
  echo -n "."
done

# Install Python dependencies
cd /workspace/blotter/backend
pip install -e ".[gpu]" 2>/dev/null || pip install -e . > /dev/null 2>&1
echo "[OK] Python packages installed"

# Copy GPU env
cp /workspace/blotter/backend/.env.gpu /workspace/blotter/backend/.env.local
echo "[OK] GPU config applied"

echo ""
echo "=== Setup complete ==="
echo "Start the pipeline with:"
echo "  cd /workspace/blotter/backend && uv run blotter stream start"
