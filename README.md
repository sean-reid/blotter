# Blotter

Real-time police scanner map covering 21 US metro areas. Per-call audio from OpenMHz is transcribed, locations are extracted and geocoded, and events are plotted on a map — all within seconds of the original dispatch.

**Live at [blotter.fm](https://blotter.fm)**

<a href="https://www.producthunt.com/products/blotter-3?embed=true&amp;utm_source=badge-featured&amp;utm_medium=badge&amp;utm_campaign=badge-blotter-3" target="_blank" rel="noopener noreferrer"><img alt="Blotter - Police radio, mapped in real time | Product Hunt" width="250" height="54" src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1133945&amp;theme=light&amp;t=1777351714816"></a>

## Architecture

```mermaid
%%{ init: { "theme": "dark", "flowchart": { "rankSpacing": 40, "nodeSpacing": 25 } } }%%
flowchart TB

  FEEDS(["24 OpenMHz Systems<br/>LA, Chicago, Charlotte, Philly,<br/>Seattle, SF, Dallas, Portland, +16"])

  CAPTURE["OpenMHz Poller<br/>Playwright per-system<br/>per-call WAV download"]

  Q1[["Redis queue<br/>capture:chunks"]]

  WHISPER["faster-whisper GPU<br/>large-v3 float16<br/>locale-specific prompts<br/>police/signal code extraction"]

  Q2[["Redis queue<br/>transcribe:done"]]

  EXTRACT["NLP Entity Extraction<br/>+ Google Places Geocoding<br/>per-city region bias<br/>event dedup 10min/500m"]

  OLLAMA["Ollama · Qwen 2.5 7B<br/>one-sentence event summaries"]

  subgraph DB["PostgreSQL 16"]
    direction LR
    T_TX[("scanner_transcripts")]
    T_EV[("scanner_events")]
  end

  API["Starlette API<br/>api.blotter.fm:8080"]
  TUNNEL["cloudflared tunnel<br/>api.blotter.fm"]
  SPA["React + MapLibre SPA<br/>blotter.fm · Cloudflare Pages"]
  USER(["User · browser / mobile"])

  GCS[("GCS · blotter-audio<br/>signed URLs 24h")]
  GNLP["Google NLP API<br/>entity extraction"]
  GPLACES["Google Places API<br/>findplacefromtext"]

  MON["Monitoring Loop<br/>heartbeat, procs, disk,<br/>queues, services,<br/>daily digest"]
  NTFY["ntfy.sh<br/>push alerts"]
  CANARY["cronjob.org 15m<br/>/api/canary endpoint"]

  DEPLOY["GitHub Actions<br/>wrangler pages deploy"]

  FEEDS --> CAPTURE
  CAPTURE --> Q1
  Q1 --> WHISPER
  WHISPER --> Q2
  Q2 --> EXTRACT
  EXTRACT --> OLLAMA
  WHISPER -->|"INSERT"| T_TX
  EXTRACT -->|"INSERT"| T_EV
  OLLAMA -->|"summary"| T_EV

  DB --- API
  API --- TUNNEL
  TUNNEL --- SPA
  SPA --- USER

  CAPTURE -->|"upload wav"| GCS
  SPA -.->|"audio playback"| GCS

  EXTRACT --> GNLP
  EXTRACT --> GPLACES

  MON -->|"alerts"| NTFY
  CANARY -->|"health check"| API
  CANARY -.->|"alert if down"| NTFY

  DEPLOY -->|"deploy"| SPA

  classDef queue fill:#92400e,stroke:#f59e0b,color:#fff
  classDef db fill:#1e3a5f,stroke:#60a5fa,color:#fff
  classDef stage fill:#14532d,stroke:#4ade80,color:#fff
  classDef google fill:#312e81,stroke:#818cf8,color:#fff
  classDef alert fill:#7f1d1d,stroke:#f87171,color:#fff
  classDef serve fill:#1a3344,stroke:#f97316,color:#fff
  classDef user fill:#475569,stroke:#94a3b8,color:#fff

  class Q1,Q2 queue
  class T_TX,T_EV,GCS db
  class CAPTURE,WHISPER,EXTRACT,OLLAMA stage
  class GNLP,GPLACES google
  class NTFY,CANARY,MON alert
  class TUNNEL,API,SPA serve
  class USER,FEEDS user
  class DEPLOY serve
```

## Stack

| Layer | Technology |
|-------|-----------|
| Audio capture | OpenMHz API via Playwright, per-call WAV, Google Cloud Storage |
| Transcription | faster-whisper large-v3 on CUDA GPU, locale-specific prompts |
| NLP | Google Cloud Natural Language API |
| Geocoding | Google Places API with per-city region biasing |
| Summarization | Ollama (Qwen 2.5 7B on GPU) |
| Database | PostgreSQL 16 (pg_trgm full-text, 7-day TTL) |
| Queues | Redis (in-memory, two-stage pipeline) |
| API | Starlette + uvicorn (REST, CORS) |
| Frontend | React 19, MapLibre GL, Tailwind CSS |
| Hosting | Cloudflare Pages (SPA) |
| Tunnel | Cloudflare Tunnel (token-based, api.blotter.fm) |
| Monitoring | supervisord monitoring loop, ntfy.sh push alerts, cronjob.org canary |
| GPU | RunPod (A5000 24GB VRAM) |
| Process management | supervisord (redis, postgres, ollama, cloudflared, api, pipeline, monitoring) |

## Project structure

```
backend/
  src/blotter/
    stages/
      capture_openmhz.py    # OpenMHz per-call capture via Playwright
      stream_transcribe.py  # Whisper transcription with locale prompts
      extract.py            # Location clause extraction
      extract_nlp.py        # Google NLP entity extraction
      extract_codes.py      # Police/10-code/signal code tagging
      geocode.py            # Google Places geocoding with per-city bias
      summarize.py          # Ollama event summarization
      worker.py             # Process managers (capture, transcribe, process)
    config.py               # Pydantic settings (env-based)
    db.py                   # PostgreSQL client (psycopg)
    api.py                  # Starlette REST API
    gcs.py                  # GCS + local storage abstraction
    queue.py                # Redis queue helpers
    models.py               # Data models
    cli.py                  # Typer CLI entry points

frontend/
  src/
    components/
      Map.tsx               # MapLibre GL map, clustering, hit areas
      EventPanel.tsx        # Event detail with swipe-to-dismiss
      TranscriptPanel.tsx   # Transcript viewer with swipe-to-dismiss
      TranscriptPlayer.tsx  # Audio playback with synced segments
      TranscriptList.tsx    # Searchable transcript list
      SearchBox.tsx         # Natural language time range + search
      Tags.tsx              # Police code tag chips
      AboutModal.tsx        # About / support info
    lib/
      api.ts                # REST API client
      parseTimeFilter.ts    # chrono-node time range parsing
      types.ts              # TypeScript interfaces

infra/
  postgres/
    init.sql                # Schema (transcripts, events, embeddings)
    pg_dump.sh              # Hourly dump to network volume
    pg_restore.sh           # Restore from dump on startup
  supervisord/
    supervisord.conf        # Process management (9 services)
  monitoring/
    monitoring_loop.sh      # Tick-based monitoring loop
    heartbeat.sh            # Pipeline heartbeat (events + transcripts)
    check_procs.sh          # supervisord process health
    check_disk.sh           # Disk usage + orphan chunks
    check_queues.sh         # Redis queue depths (alert > 30)
    check_services.sh       # Redis/API ping
    daily_summary.sh        # Daily digest at 9am PT
  runpod/setup.sh           # Pod bootstrap script
  caddy/Caddyfile           # Reverse proxy (local dev)
  docker-compose.yml        # Local dev (PostgreSQL + Redis + Caddy)
```

## Local development

```bash
# Start infrastructure
cd infra
docker compose up -d

# Backend
cd backend
uv sync
cp .env.example .env  # configure feeds, API keys
uv run blotter stream start --openmhz

# Frontend
cd frontend
npm install
npm run dev
```

Requires: ffmpeg, Redis, PostgreSQL, NVIDIA GPU with CUDA (for Whisper + Ollama), Playwright.

## Deployment

**Backend**: The RunPod pod boots from `infra/runpod/setup.sh`, which installs dependencies, initializes PostgreSQL, starts supervisord (redis, postgres, ollama, cloudflared, api, pipeline, monitoring), and restores data from the network volume backup.

**Frontend**: Auto-deploys via GitHub Actions on push to `production` branch. Manual deploy with `npx wrangler pages deploy dist --branch production` from `frontend/`.
