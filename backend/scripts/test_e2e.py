#!/usr/bin/env python3
"""
End-to-end test: audio file → transcribe → extract → geocode → ClickHouse.

Requires: ClickHouse running on localhost:8123 (via docker compose).
Nominatim is optional — falls back to approximate coordinates if unavailable.

Usage:
    uv run --python python3.13 scripts/test_e2e.py data/test/lapd_south_5min.wav
"""
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src))

from blotter.config import ClickHouseConfig, NominatimConfig
from blotter.db import get_client, insert_events, insert_transcript
from blotter.models import GeocodedEvent, Transcript
from blotter.stages.extract import extract_locations
from blotter.stages.geocode import Geocoder

FEED_ID = "20296"
FEED_NAME = "LAPD - South Bureau"

LA_CENTER_LAT = 34.05
LA_CENTER_LON = -118.25


def transcribe_cpu(audio_path: Path) -> tuple[list, str, float]:
    from faster_whisper import WhisperModel

    print("Loading whisper model (first run downloads ~3GB)...")
    model = WhisperModel("large-v3", device="cpu", compute_type="int8")

    police_prompt = (
        "Police radio dispatch. 10-4, copy, code 3, code 2, suspect vehicle, "
        "responding unit, en route, on scene, clear, dispatch, copy that, "
        "Los Angeles, Hollywood, Downtown, South Central, Wilshire, Van Nuys, "
        "Sunset Boulevard, Figueroa, Crenshaw, Western, Vermont, Sepulveda, "
        "the 405, the 101, the 110, the 10, the 5, LAPD, LASD."
    )

    print(f"Transcribing {audio_path.name} (CPU — this will be slow)...")
    t0 = time.time()

    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        language="en",
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 200},
        initial_prompt=police_prompt,
    )

    segments = []
    texts = []
    for seg in segments_iter:
        segments.append(seg)
        texts.append(seg.text.strip())

    full_text = " ".join(texts)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.0f}s — {info.duration:.0f}s audio, {len(segments)} segments\n")
    return segments, full_text, info.duration


def try_geocode(locations, nominatim_available: bool):
    geocoder = None
    if nominatim_available:
        try:
            config = NominatimConfig()
            geocoder = Geocoder(config)
        except Exception:
            pass

    events = []
    now = datetime.now(timezone.utc)

    for loc in locations:
        lat, lon = None, None

        if geocoder:
            result = geocoder.geocode(loc)
            if result:
                lat, lon = result

        if lat is None:
            lat = LA_CENTER_LAT + random.uniform(-0.08, 0.08)
            lon = LA_CENTER_LON + random.uniform(-0.12, 0.12)

        events.append(GeocodedEvent(
            feed_id=FEED_ID,
            archive_ts=now,
            event_ts=now,
            raw_location=loc.raw_text,
            normalized=loc.normalized,
            latitude=lat,
            longitude=lon,
            confidence=loc.confidence,
        ))

    return events


def check_nominatim() -> bool:
    import httpx
    try:
        r = httpx.get("http://localhost:8080/status", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_e2e.py <audio_file.wav>")
        sys.exit(1)

    audio_path = Path(sys.argv[1])
    if not audio_path.exists():
        print(f"File not found: {audio_path}")
        sys.exit(1)

    # 1. Check ClickHouse
    print("Connecting to ClickHouse...")
    try:
        ch_config = ClickHouseConfig()
        client = get_client(ch_config)
        client.query("SELECT 1")
        print("  Connected.\n")
    except Exception as e:
        print(f"  ClickHouse not available: {e}")
        print("  Start it with: cd infra && docker compose up -d clickhouse caddy")
        sys.exit(1)

    # 2. Check Nominatim
    nominatim_up = check_nominatim()
    if nominatim_up:
        print("Nominatim available — will geocode for real.\n")
    else:
        print("Nominatim not available — using approximate LA coordinates.\n")

    # 3. Transcribe
    segments, full_text, duration = transcribe_cpu(audio_path)

    print("=" * 60)
    print("TRANSCRIPT")
    print("=" * 60)
    for seg in segments:
        print(f"  [{seg.start:6.1f}s] {seg.text.strip()}")
    print()

    # 4. Extract locations
    print("Extracting locations...")
    locations = extract_locations(full_text)
    print(f"  Found {len(locations)} locations.\n")

    for loc in locations:
        print(f"  [{loc.confidence:.0%}] {loc.normalized}  ({loc.source})")
    print()

    # 5. Geocode
    print("Geocoding...")
    events = try_geocode(locations, nominatim_up)
    print(f"  {len(events)} events geocoded.\n")

    # 6. Insert into ClickHouse
    now = datetime.now(timezone.utc)
    transcript = Transcript(
        feed_id=FEED_ID,
        feed_name=FEED_NAME,
        archive_ts=now,
        duration_ms=int(duration * 1000),
        audio_url="",
        segments=[],
        full_text=full_text,
    )

    print("Inserting into ClickHouse...")
    insert_transcript(client, transcript)
    insert_events(client, events)
    print(f"  Inserted 1 transcript + {len(events)} events.\n")

    # 7. Verify
    result = client.query("SELECT count() FROM blotter.scanner_events")
    total = result.first_row[0]
    print(f"Total events in database: {total}")
    print()
    print("Frontend should now show data at http://localhost:5173")
    print("(Make sure Caddy is running: cd infra && docker compose up -d caddy)")


if __name__ == "__main__":
    main()
