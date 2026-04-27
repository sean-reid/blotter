# Blotter

Real-time police scanner map for Los Angeles County. Live audio from Broadcastify is transcribed, locations are extracted and geocoded, and events are plotted on a map — all within minutes of the original dispatch.

**Live at [blotter.fm](https://blotter.fm)**

## Architecture

```
Broadcastify CDN (6 feeds)
    │
    ▼
StreamCaptureWorker ──► GCS (audio chunks)
    │
    ▼
Redis queue ──► TranscriptionWorker (Faster Whisper large-v3 / GPU)
    │
    ▼
Redis queue ──► ProcessingWorker (Google NLP + Places geocoding)
    │
    ▼
ClickHouse ◄── Cloudflare Pages Function ──► Frontend (React + MapLibre)
```

All backend processes run on a single RunPod GPU pod (RTX 3090). The frontend is deployed to Cloudflare Pages with a Workers function that proxies queries to ClickHouse through a Cloudflare Tunnel.

## Stack

| Layer | Technology |
|-------|-----------|
| Audio capture | ffmpeg → 5-min WAV chunks → GCS |
| Transcription | Faster Whisper large-v3 on GPU |
| NLP | Google Cloud Natural Language API |
| Geocoding | Google Places API |
| Database | ClickHouse |
| Frontend | React, MapLibre GL, Tailwind |
| Hosting | Cloudflare Pages + Workers |
| Tunnel | Cloudflare Tunnel (pod → ch.blotter.fm) |
| GPU | RunPod (RTX 3090, spot instance) |

## Project structure

```
backend/
  src/blotter/
    stages/
      capture.py          # ffmpeg stream capture, GCS upload
      stream_transcribe.py # Whisper transcription with boundary overlap
      extract_nlp.py       # Google NLP entity extraction
      extract_codes.py     # Police/10-code tagging
      geocode.py           # Google Places geocoding
      worker.py            # Worker process management
    config.py              # All configuration (env-based)
    db.py                  # ClickHouse client
    gcs.py                 # GCS + local storage abstraction
    queue.py               # Redis queue helpers
    models.py              # Data models
    cli.py                 # CLI entry points

frontend/
  src/
    components/
      Map.tsx              # MapLibre GL map with event markers
      EventPanel.tsx       # Event detail panel
      TranscriptPlayer.tsx # Audio playback with synced transcript
      SearchBox.tsx        # Time range + full-text search
      Tags.tsx             # Police code tag chips
    lib/
      api.ts               # ClickHouse query layer
      types.ts             # TypeScript interfaces
  functions/
    api/query.ts           # Cloudflare Pages Function (CH proxy)

infra/
  clickhouse/init.sql      # Schema
  cloudflared/config.yml   # Tunnel config
  runpod/setup.sh          # Pod bootstrap script
  docker-compose.yml       # Local dev (ClickHouse + Redis)
```

## Local development

```bash
# Backend
cd backend
uv sync
cp .env.example .env  # configure feeds, API keys
uv run blotter stream start

# Frontend
cd frontend
npm install
npm run dev
```

Requires: ffmpeg, Redis, ClickHouse, GPU with CUDA (for Whisper).

## Deployment

The RunPod pod boots from `infra/runpod/setup.sh`, which installs dependencies, starts services, and launches the pipeline. The frontend auto-deploys via GitHub Actions on push to `main` (staging) or `production`.
