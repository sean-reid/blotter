"""Process test audio files through the full pipeline: Whisper -> NLP -> Places -> PostgreSQL."""
import sys
from datetime import datetime, timezone
from pathlib import Path

from blotter.config import (
    GoogleGeocodingConfig, GoogleNLPConfig, PostgresConfig,
    RegionConfig, TranscriptionConfig,
)
from blotter.db import get_conn, insert_events, insert_transcript
from blotter.log import get_logger
from blotter.models import GeocodedEvent, Transcript
from blotter.stages.extract import extract_clauses, strip_ads
from blotter.stages.extract_nlp import extract_entities
from blotter.stages.geocode import Geocoder
from blotter.stages.transcribe import Transcriber

log = get_logger(__name__)

FEED_NAMES = {
    "20296": "LAPD South Bureau",
    "33623": "LAPD West Bureau",
    "26569": "LAPD Valley Bureau",
    "40488": "LAPD Hotshot",
    "25187": "LASD Multi-Dispatch",
    "24051": "Long Beach PD",
}


def process_file(
    wav_path: Path,
    feed_id: str,
    conn, geocoder, transcriber, nlp_config,
):
    feed_name = FEED_NAMES.get(feed_id, feed_id)
    now = datetime.now(timezone.utc)

    print(f"\n{'='*60}")
    print(f"Processing: {wav_path.name} (feed: {feed_name})")

    segments, raw_text = transcriber.transcribe(wav_path)
    full_text = strip_ads(raw_text)
    print(f"Whisper: {len(full_text)} chars ({len(segments)} segments)")

    audio_url = f"/audio-data/test/{wav_path.name}"

    transcript = Transcript(
        feed_id=feed_id,
        feed_name=feed_name,
        archive_ts=now,
        duration_ms=300_000,
        audio_url=audio_url,
        segments=segments,
        full_text=full_text,
    )
    insert_transcript(conn, transcript)

    entities = extract_entities(full_text, nlp_config)
    if not entities:
        entities = extract_clauses(full_text)

    events = []
    for e in entities:
        result = geocoder.geocode(e)
        if result is None:
            continue
        lat, lon, name = result
        events.append(GeocodedEvent(
            feed_id=feed_id,
            archive_ts=now,
            event_ts=now,
            raw_location=e.raw_text,
            normalized=name,
            latitude=lat,
            longitude=lon,
            confidence=0.8,
            context=e.context,
        ))

    insert_events(conn, events)
    print(f"Events: {len(events)}")
    for ev in events:
        print(f"  {ev.normalized} ({ev.latitude:.4f}, {ev.longitude:.4f})")


def main():
    conn = get_conn(PostgresConfig())
    region = RegionConfig()
    geocoder = Geocoder(GoogleGeocodingConfig(), region)
    transcriber = Transcriber(TranscriptionConfig())
    nlp_config = GoogleNLPConfig()

    test_dir = Path("data/test")
    files = sorted(test_dir.glob("*.wav"))

    if not files:
        print("No WAV files found in data/test/")
        sys.exit(1)

    file_feed_map = {
        "lapd_south": "20296",
        "lapd_west": "33623",
        "lapd_valley": "26569",
        "lapd_hotshot": "40488",
        "lasd": "25187",
        "long_beach": "24051",
    }

    for wav in files:
        feed_id = "20296"
        for prefix, fid in file_feed_map.items():
            if prefix in wav.stem:
                feed_id = fid
                break
        process_file(wav, feed_id, conn, geocoder, transcriber, nlp_config)

    print(f"\nDone. Processed {len(files)} files.")


if __name__ == "__main__":
    main()
