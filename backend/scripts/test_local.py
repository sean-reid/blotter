#!/usr/bin/env python3
"""
Test the transcription + extraction pipeline on a local audio file.
No GPU, no database, no Nominatim required.

Usage:
    uv run --python python3.13 scripts/test_local.py data/test/lapd_south_5min.wav
"""
import sys
import time
from pathlib import Path

src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src))

from blotter.stages.extract import extract_locations


def transcribe_cpu(audio_path: Path) -> tuple[list, str]:
    from faster_whisper import WhisperModel

    print(f"Loading model (this takes a minute on first run)...")
    model = WhisperModel(
        "large-v3",
        device="cpu",
        compute_type="int8",
    )

    police_prompt = (
        "Police radio dispatch. 10-4, copy, code 3, code 2, suspect vehicle, "
        "responding unit, en route, on scene, clear, dispatch, copy that, "
        "10-97, 10-98, 10-99, welfare check, traffic stop, DUI, 211, 459, 487, "
        "Los Angeles, Hollywood, Downtown, South Central, Wilshire, Van Nuys, "
        "Sunset Boulevard, Figueroa, Crenshaw, Western, Vermont, Sepulveda, "
        "the 405, the 101, the 110, the 10, the 5, PCH, Mulholland, "
        "LAPD, LASD, Adam, Boy, Lincoln, Mary, division, RD."
    )

    print(f"Transcribing {audio_path.name}...")
    t0 = time.time()

    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        language="en",
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 200,
        },
        initial_prompt=police_prompt,
    )

    segments = []
    texts = []
    for seg in segments_iter:
        segments.append(seg)
        texts.append(seg.text.strip())

    full_text = " ".join(texts)
    elapsed = time.time() - t0

    print(f"Done in {elapsed:.1f}s — {info.duration:.0f}s audio, "
          f"{len(segments)} segments, {len(full_text)} chars\n")

    return segments, full_text


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_local.py <audio_file.wav>")
        sys.exit(1)

    audio_path = Path(sys.argv[1])
    if not audio_path.exists():
        print(f"File not found: {audio_path}")
        sys.exit(1)

    segments, full_text = transcribe_cpu(audio_path)

    print("=" * 60)
    print("TRANSCRIPT")
    print("=" * 60)
    for seg in segments:
        ts = f"[{seg.start:6.1f}s - {seg.end:6.1f}s]"
        print(f"  {ts}  {seg.text.strip()}")

    print()
    print("=" * 60)
    print("FULL TEXT")
    print("=" * 60)
    print(full_text)

    print()
    print("=" * 60)
    print("EXTRACTED LOCATIONS")
    print("=" * 60)
    locations = extract_locations(full_text)
    if not locations:
        print("  (none found)")
    for loc in locations:
        print(f"  [{loc.confidence:.0%}] {loc.normalized}")
        print(f"         raw: {loc.raw_text}")
        print(f"         src: {loc.source}")
        print()


if __name__ == "__main__":
    main()
