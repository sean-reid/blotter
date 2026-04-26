import subprocess
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from blotter.config import BroadcastifyConfig
from blotter.log import get_logger
from blotter.models import ArchiveBlock

log = get_logger(__name__)


class AudioDownloader:
    def __init__(self, config: BroadcastifyConfig, data_dir: str) -> None:
        self.config = config
        self.data_dir = Path(data_dir)
        self.http = httpx.Client(timeout=120)

    def wav_path(self, block: ArchiveBlock) -> Path:
        date_str = block.timestamp.strftime("%Y-%m-%d")
        ts_str = str(int(block.timestamp.timestamp()))
        return self.data_dir / block.feed_id / date_str / f"{ts_str}.wav"

    def mp3_path(self, block: ArchiveBlock) -> Path:
        return self.wav_path(block).with_suffix(".mp3")

    def is_downloaded(self, block: ArchiveBlock) -> bool:
        return self.wav_path(block).exists()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30))
    def download_mp3(self, block: ArchiveBlock) -> Path:
        mp3 = self.mp3_path(block)
        mp3.parent.mkdir(parents=True, exist_ok=True)

        log.info("downloading", feed_id=block.feed_id, url=block.url)
        with self.http.stream("GET", block.url) as resp:
            resp.raise_for_status()
            with open(mp3, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        log.info("downloaded", path=str(mp3), size_mb=round(mp3.stat().st_size / 1_048_576, 2))
        return mp3

    def convert_to_wav(self, mp3_path: Path, wav_path: Path) -> Path:
        log.info("converting to wav", src=str(mp3_path))
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(mp3_path),
                "-af", "loudnorm",
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                str(wav_path),
            ],
            check=True,
            capture_output=True,
        )
        mp3_path.unlink()
        log.info("converted", path=str(wav_path))
        return wav_path

    def download_and_convert(self, block: ArchiveBlock) -> Path:
        if self.is_downloaded(block):
            log.info("already downloaded", feed_id=block.feed_id, ts=str(block.timestamp))
            return self.wav_path(block)

        mp3 = self.download_mp3(block)
        wav = self.wav_path(block)
        return self.convert_to_wav(mp3, wav)

    def close(self) -> None:
        self.http.close()
