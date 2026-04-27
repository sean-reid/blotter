import collections
import subprocess
import tempfile
from pathlib import Path

from blotter.config import GCSConfig, StreamConfig, TranscriptionConfig
from blotter.gcs import get_storage
from blotter.log import get_logger
from blotter.models import ChunkTask, TranscriptSegment
from blotter.stages.extract import strip_ads
from blotter.stages.transcribe import Transcriber

log = get_logger(__name__)

SILENCE_THRESHOLD_DB = -35
CONTEXT_WINDOW_CHUNKS = 5


class StreamTranscriber:
    def __init__(
        self,
        transcription_config: TranscriptionConfig,
        stream_config: StreamConfig,
        gcs_config: GCSConfig,
    ) -> None:
        self._transcriber = Transcriber(transcription_config)
        self._stream_config = stream_config
        self._gcs = get_storage(gcs_config)
        self._prev_text: dict[str, str] = {}
        self._text_buffer: dict[str, collections.deque[str]] = {}

    def _get_buffer(self, feed_id: str) -> collections.deque[str]:
        if feed_id not in self._text_buffer:
            self._text_buffer[feed_id] = collections.deque(maxlen=CONTEXT_WINDOW_CHUNKS)
        return self._text_buffer[feed_id]

    def get_context_window(self, feed_id: str) -> str:
        buf = self._get_buffer(feed_id)
        return " ".join(buf)

    def process_chunk(self, task: ChunkTask) -> tuple[list[TranscriptSegment], str, int]:
        with tempfile.TemporaryDirectory(prefix="blotter_") as tmpdir:
            local_path = Path(tmpdir) / "chunk.wav"
            self._gcs.download(task.chunk_path, local_path)

            duration_ms = self._get_duration_ms(local_path)

            audio_path = local_path
            trim_offset = 0.0
            if task.skip_start and self._stream_config.ad_skip_seconds > 0:
                trim_offset = float(self._stream_config.ad_skip_seconds)
                audio_path = self._trim_start(local_path, self._stream_config.ad_skip_seconds)

            if self._is_silent(audio_path):
                log.info("skipping silent chunk", feed_id=task.feed_id, chunk_index=task.chunk_index)
                return [], "", duration_ms

            segments, full_text = self._transcriber.transcribe(audio_path, feed_id=task.feed_id)

            if trim_offset > 0 and segments:
                segments = [
                    TranscriptSegment(start=s.start + trim_offset, end=s.end + trim_offset, text=s.text)
                    for s in segments
                ]

        full_text = strip_ads(full_text)

        full_text = self._deduplicate_boundary(task.feed_id, full_text)
        self._prev_text[task.feed_id] = full_text

        if full_text:
            self._get_buffer(task.feed_id).append(full_text)

        log.info(
            "chunk transcribed",
            feed_id=task.feed_id,
            chunk_index=task.chunk_index,
            segments=len(segments),
            chars=len(full_text),
            duration_ms=duration_ms,
            context_chunks=len(self._get_buffer(task.feed_id)),
        )
        return segments, full_text, duration_ms

    def _get_duration_ms(self, audio_path: Path) -> int:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(audio_path)],
                capture_output=True, text=True, timeout=5,
            )
            return int(float(result.stdout.strip()) * 1000)
        except Exception:
            return 0

    def _is_silent(self, audio_path: Path) -> bool:
        try:
            result = subprocess.run(
                ["ffmpeg", "-i", str(audio_path), "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stderr.splitlines():
                if "mean_volume" in line:
                    db = float(line.split("mean_volume:")[1].strip().split()[0])
                    log.debug("volume check", path=str(audio_path), mean_db=db)
                    return db < SILENCE_THRESHOLD_DB
        except Exception:
            pass
        return False

    def _trim_start(self, audio_path: Path, skip_seconds: int) -> Path:
        trimmed = audio_path.with_name("trimmed.wav")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-ss", str(skip_seconds),
                "-c:a", "pcm_s16le",
                str(trimmed),
            ],
            check=True, capture_output=True,
        )
        return trimmed

    def _deduplicate_boundary(self, feed_id: str, text: str) -> str:
        prev = self._prev_text.get(feed_id)
        if not prev or not text:
            return text

        prev_words = prev.split()
        curr_words = text.split()
        if len(prev_words) < 3 or len(curr_words) < 3:
            return text

        max_overlap = min(20, len(prev_words), len(curr_words))
        best = 0
        for length in range(1, max_overlap + 1):
            if prev_words[-length:] == curr_words[:length]:
                best = length

        if best > 0:
            log.debug("boundary dedup", feed_id=feed_id, overlap_words=best)
            return " ".join(curr_words[best:])
        return text
