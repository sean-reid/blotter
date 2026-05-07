# Blotter

Real-time police scanner map covering 24 US metro areas. Per-call audio from OpenMHz is transcribed, locations are extracted and geocoded, and events are plotted on a map — all within seconds of the original dispatch.

**Live at [blotter.fm](https://blotter.fm)**

<a href="https://www.producthunt.com/products/blotter-3?embed=true&amp;utm_source=badge-featured&amp;utm_medium=badge&amp;utm_campaign=badge-blotter-3" target="_blank" rel="noopener noreferrer"><img alt="Blotter - Police radio, mapped in real time | Product Hunt" width="250" height="54" src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1133945&amp;theme=light&amp;t=1777351714816"></a>

## Architecture

```mermaid
%%{ init: { "theme": "dark", "flowchart": { "rankSpacing": 40, "nodeSpacing": 25 } } }%%
flowchart TB

  FEEDS(["13 OpenMHz Systems<br/>LA, Chicago, Charlotte, Philly,<br/>Seattle, SF, Dallas, Portland, +5"])

  CAPTURE["OpenMHz Poller<br/>Playwright per-system<br/>per-call WAV download"]

  Q1[["Redis queue<br/>capture:chunks"]]

  WHISPER["faster-whisper GPU<br/>large-v3 float16<br/>locale-specific prompts<br/>police/signal code extraction"]

  Q2[["Redis queue<br/>transcribe:done"]]

  EXTRACT["NLP Entity Extraction<br/>+ Google Places Geocoding<br/>per-city region bias<br/>event dedup 10min/500m"]

  subgraph DB["ClickHouse 24.8"]
    direction LR
    T_TX[("scanner_transcripts")]
    T_EV[("scanner_events<br/>ReplacingMergeTree")]
    T_MET[("pipeline_metrics")]
  end

  TUNNEL["cloudflared tunnel<br/>ch.blotter.fm"]
  ACCESS["Cloudflare Access · mTLS"]
  FNQUERY["/api/query · Pages Function<br/>SQL proxy, SELECT whitelist"]
  SPA["React + MapLibre SPA<br/>blotter.fm · Cloudflare Pages"]
  USER(["User · browser / mobile"])

  GCS[("GCS · blotter-audio<br/>signed URLs 24h")]
  GNLP["Google NLP API<br/>entity extraction"]
  GPLACES["Google Places API<br/>findplacefromtext"]

  CRON["Monitoring Cron<br/>heartbeat, procs, disk,<br/>queues, services,<br/>throughput, daily digest"]
  NTFY["ntfy.sh<br/>push alerts"]
  CANARY["cronjob.org 15m<br/>/api/health endpoint"]

  DEPLOY["GitHub Actions<br/>wrangler pages deploy"]

  FEEDS --> CAPTURE
  CAPTURE --> Q1
  Q1 --> WHISPER
  WHISPER --> Q2
  Q2 --> EXTRACT
  WHISPER -->|"INSERT"| T_TX
  EXTRACT -->|"INSERT"| T_EV

  DB --- TUNNEL
  TUNNEL --- ACCESS
  ACCESS --- FNQUERY
  FNQUERY --- SPA
  SPA --- USER

  CAPTURE -->|"upload wav"| GCS
  SPA -.->|"audio playback"| GCS

  EXTRACT --> GNLP
  EXTRACT --> GPLACES

  CRON -->|"metrics"| T_MET
  CRON -->|"alerts"| NTFY
  CANARY -->|"health check"| FNQUERY
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
  class T_TX,T_EV,T_MET,GCS db
  class CAPTURE,WHISPER,EXTRACT stage
  class GNLP,GPLACES google
  class NTFY,CANARY,CRON alert
  class TUNNEL,ACCESS,FNQUERY,SPA serve
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
| Database | ClickHouse (ReplacingMergeTree, 7-day TTL) |
| Queues | Redis (in-memory, two-stage pipeline) |
| Frontend | React 19, MapLibre GL, Tailwind CSS |
| Hosting | Cloudflare Pages + Pages Functions |
| Tunnel | Cloudflare Tunnel + Access (mTLS) |
| Monitoring | Cron scripts, ntfy.sh push alerts, cronjob.org canary |
| GPU | RunPod (RTX 3090) |
| Process management | supervisord (redis, clickhouse, cloudflared, pipeline) |

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
      worker.py             # Process managers (capture, transcribe, process)
    config.py               # Pydantic settings (env-based)
    db.py                   # ClickHouse client
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
      api.ts                # ClickHouse query layer
      parseTimeFilter.ts    # chrono-node time range parsing
      types.ts              # TypeScript interfaces
  functions/api/
    query.ts                # Pages Function: ClickHouse SQL proxy
    health.ts               # Pages Function: canary health check

infra/
  clickhouse/init.sql       # Schema (transcripts, events, metrics)
  cloudflared/config.yml    # Tunnel config (ch.blotter.fm)
  supervisord/
    supervisord.conf        # Process management (4 services)
  monitoring/
    crontab                 # All cron schedules
    heartbeat.sh            # Pipeline heartbeat (events + transcripts)
    check_procs.sh          # supervisord process health
    check_disk.sh           # Disk usage + orphan chunks
    check_queues.sh         # Redis queue depths (alert > 30)
    check_ffmpeg.sh         # Per-feed ffmpeg liveness
    check_services.sh       # Redis/ClickHouse ping
    check_resources.sh      # GPU/CPU/RAM metrics
    check_throughput.sh     # Hourly per-feed transcript/event counts
    daily_summary.sh        # Daily digest at 9am PT
  runpod/setup.sh           # Pod bootstrap script
  caddy/Caddyfile           # Reverse proxy (local dev)
  docker-compose.yml        # Local dev (ClickHouse + Redis + Caddy)
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

Requires: ffmpeg, Redis, ClickHouse, NVIDIA GPU with CUDA (for Whisper), Playwright.

## Deployment

**Backend**: The RunPod pod boots from `infra/runpod/setup.sh`, which installs dependencies, starts supervisord (redis, clickhouse, cloudflared, pipeline), initializes the schema, and installs the monitoring crontab.

**Frontend**: Auto-deploys via GitHub Actions on push to `production` branch. Manual deploy with `npx wrangler pages deploy dist --branch production` from `frontend/`.
