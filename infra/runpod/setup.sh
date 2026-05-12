#!/bin/bash
set -euo pipefail

REPO_DIR=/workspace/blotter
export GOOGLE_APPLICATION_CREDENTIALS=/workspace/blotter-gcs-key.json

# Load secrets (REDIS_PASSWORD, POSTGRES_PASSWORD, CLOUDFLARED_TOKEN)
SECRETS_FILE=/workspace/blotter/.env.secrets
if [ -f "$SECRETS_FILE" ]; then
  set -a; source "$SECRETS_FILE"; set +a
else
  echo "[WARN] No .env.secrets found"
fi

echo "=== Blotter RunPod Start ==="

# Install system dependencies
apt-get update -qq
apt-get install -y -qq ffmpeg redis-server curl git gnupg lsb-release > /dev/null 2>&1
if ! dpkg -l postgresql-16 &>/dev/null; then
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg
  echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
  apt-get update -qq
  apt-get install -y -qq postgresql-16 > /dev/null 2>&1
fi
echo "[OK] System packages"

# Install cloudflared
if ! command -v cloudflared &>/dev/null; then
  curl -sSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
fi
echo "[OK] cloudflared"

# Install Ollama
if ! command -v ollama &>/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
ln -sf /workspace/.ollama /root/.ollama 2>/dev/null || true
mkdir -p /root/.cache
ln -sf /workspace/.cache/huggingface /root/.cache/huggingface 2>/dev/null || true
echo "[OK] Ollama"

# Install uv
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
echo "[OK] uv"

# Install supervisord
pip install supervisor -q 2>/dev/null || pip3 install supervisor -q
echo "[OK] supervisord"

# Clone/update repo
if [ -d "$REPO_DIR" ]; then
  cd "$REPO_DIR" && git fetch origin && git checkout production && git reset --hard origin/production
else
  git clone -b production https://github.com/sean-reid/blotter.git "$REPO_DIR"
fi
echo "[OK] Repo"

# Install/sync Python backend
cd "$REPO_DIR/backend"
uv sync 2>/dev/null
uv pip install playwright 2>/dev/null
uv run playwright install chromium --with-deps 2>/dev/null
echo "[OK] Python packages + Playwright"

# Initialize PostgreSQL (schema — pg_restore will overwrite with real data if dump exists)
pg_ctlcluster 16 main start 2>/dev/null || true
sleep 2
su postgres -c "psql -c \"CREATE USER blotter WITH PASSWORD '${POSTGRES_PASSWORD:-blotter}'\"" 2>/dev/null || true
su postgres -c "psql -c \"CREATE DATABASE blotter OWNER blotter\"" 2>/dev/null || true
su postgres -c "psql -d blotter -c \"GRANT ALL ON SCHEMA public TO blotter\"" 2>/dev/null || true
su postgres -c "psql -d blotter -c \"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO blotter\"" 2>/dev/null || true
su postgres -c "psql -d blotter -c \"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO blotter\"" 2>/dev/null || true
PGPASSWORD="${POSTGRES_PASSWORD:-blotter}" psql -h localhost -U blotter -d blotter -f "$REPO_DIR/infra/postgres/init.sql" 2>/dev/null
echo "[OK] PostgreSQL"
pg_ctlcluster 16 main stop 2>/dev/null || true
sleep 1

# Kill any leftover processes from previous runs
supervisorctl -c "$REPO_DIR/infra/supervisord/supervisord.conf" shutdown 2>/dev/null || true
pkill -f supervisord 2>/dev/null || true
pkill redis-server 2>/dev/null || true
pkill cloudflared 2>/dev/null || true
sleep 1

# Start supervisord (runs in foreground via nodaemon=true, so background it)
supervisord -c "$REPO_DIR/infra/supervisord/supervisord.conf" &
echo "[OK] supervisord started"

echo ""
echo "=== Blotter running at $(date) ==="
echo ""
echo "Management commands:"
echo "  supervisorctl -c $REPO_DIR/infra/supervisord/supervisord.conf status"
echo "  supervisorctl -c $REPO_DIR/infra/supervisord/supervisord.conf restart pipeline"
echo "  supervisorctl -c $REPO_DIR/infra/supervisord/supervisord.conf tail -f pipeline"
