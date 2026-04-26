import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

import redis

from blotter.config import GCSConfig, RedisConfig, StreamConfig
from blotter.gcs import GCSClient, LocalStorageClient, get_storage
from blotter.log import get_logger
from blotter.models import ChunkTask
from blotter.queue import enqueue_chunk

log = get_logger(__name__)

BROADCASTIFY_CDN = "https://broadcastify.cdnstream1.com"


def _kill_orphan_ffmpeg(feed_id: str) -> None:
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", f"broadcastify.cdnstream1.com/{feed_id}"],
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    pids = [int(p) for p in out.splitlines() if p.strip()]
    if not pids:
        return
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
    time.sleep(2)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
            log.info("killed orphan ffmpeg", feed_id=feed_id, pid=pid)
        except (OSError, ProcessLookupError):
            pass


class StreamCaptureWorker:
    def __init__(
        self,
        feed_id: str,
        feed_name: str,
        stream_config: StreamConfig,
        gcs_client: GCSClient | LocalStorageClient,
        redis_client: redis.Redis,
    ) -> None:
        self.feed_id = feed_id
        self.feed_name = feed_name
        self.config = stream_config
        self.gcs = gcs_client
        self.redis = redis_client
        self._stop = Event()
        self._thread: Thread | None = None
        self._chunk_index = 0
        self._is_fresh_connect = True
        self._pid_file = Path(self.config.chunk_dir) / f".{self.feed_id}.pid"

    @property
    def stream_url(self) -> str:
        return f"{BROADCASTIFY_CDN}/{self.feed_id}"

    @property
    def output_dir(self) -> Path:
        d = Path(self.config.chunk_dir) / self.feed_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def start(self) -> None:
        self._cleanup_stale_pid()
        self._thread = Thread(target=self._run, name=f"capture-{self.feed_id}", daemon=True)
        self._thread.start()
        log.info("capture worker started", feed_id=self.feed_id, feed_name=self.feed_name)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._pid_file.unlink(missing_ok=True)

    def _write_pid(self, pid: int) -> None:
        self._pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._pid_file.write_text(str(pid))

    def _cleanup_stale_pid(self) -> None:
        if not self._pid_file.exists():
            return
        try:
            old_pid = int(self._pid_file.read_text().strip())
            os.kill(old_pid, signal.SIGTERM)
            log.info("killed stale ffmpeg from pid file", feed_id=self.feed_id, pid=old_pid)
        except (ValueError, OSError, ProcessLookupError):
            pass
        self._pid_file.unlink(missing_ok=True)

    def _run(self) -> None:
        consecutive_failures = 0

        while not self._stop.is_set():
            try:
                self._capture_stream()
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                delay = min(
                    self.config.reconnect_delay * (2 ** min(consecutive_failures - 1, 6)),
                    self.config.reconnect_max_delay,
                )
                log.warning(
                    "capture failed, reconnecting",
                    feed_id=self.feed_id,
                    failures=consecutive_failures,
                    retry_in=delay,
                    exc_info=True,
                )
                self._is_fresh_connect = True
                self._stop.wait(delay)

    def _kill_proc(self, proc: subprocess.Popen) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                proc.kill()
        self._pid_file.unlink(missing_ok=True)

    def _capture_stream(self) -> None:
        _kill_orphan_ffmpeg(self.feed_id)
        output_pattern = str(self.output_dir / "%Y%m%d_%H%M%S.wav")

        cmd = [
            "ffmpeg",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "30",
            "-i", self.stream_url,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            "-f", "segment",
            "-segment_time", str(self.config.segment_time),
            "-reset_timestamps", "1",
            "-strftime", "1",
            output_pattern,
        ]

        log.info("starting ffmpeg", feed_id=self.feed_id, url=self.stream_url)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid)
        self._write_pid(proc.pid)

        watcher = Thread(
            target=self._watch_chunks,
            name=f"watcher-{self.feed_id}",
            daemon=True,
        )
        watcher.start()

        try:
            while not self._stop.is_set():
                retcode = proc.poll()
                if retcode is not None:
                    stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
                    log.warning("ffmpeg exited", feed_id=self.feed_id, code=retcode, stderr=stderr[-500:])
                    raise RuntimeError(f"ffmpeg exited with code {retcode}")
                self._stop.wait(1)
        finally:
            self._kill_proc(proc)

    def _watch_chunks(self) -> None:
        seen: set[str] = set()

        for f in self.output_dir.iterdir():
            if f.suffix == ".wav":
                seen.add(f.name)

        while not self._stop.is_set():
            for f in sorted(self.output_dir.iterdir()):
                if f.suffix != ".wav" or f.name in seen:
                    continue
                if not self._is_file_complete(f):
                    continue

                seen.add(f.name)
                try:
                    self._process_chunk(f)
                except Exception:
                    log.error("chunk processing failed", feed_id=self.feed_id, file=f.name, exc_info=True)

            self._stop.wait(2)

    def _is_file_complete(self, path: Path) -> bool:
        try:
            size1 = path.stat().st_size
            if size1 == 0:
                return False
            time.sleep(5)
            size2 = path.stat().st_size
            return size1 == size2
        except OSError:
            return False

    def _process_chunk(self, local_path: Path) -> None:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        gcs_path = f"{self.feed_id}/{date_str}/{local_path.name}"

        self.gcs.upload(local_path, gcs_path)
        audio_url = self.gcs.public_url(gcs_path)

        duration_ms = self.config.segment_time * 1000

        task = ChunkTask(
            feed_id=self.feed_id,
            feed_name=self.feed_name,
            chunk_path=gcs_path,
            audio_url=audio_url,
            chunk_ts=now,
            chunk_index=self._chunk_index,
            duration_ms=duration_ms,
            skip_start=self._is_fresh_connect,
        )
        enqueue_chunk(self.redis, task)

        self._is_fresh_connect = False
        self._chunk_index += 1

        local_path.unlink(missing_ok=True)
        log.info(
            "chunk captured",
            feed_id=self.feed_id,
            chunk=self._chunk_index,
            gcs=gcs_path,
            skip_start=task.skip_start,
        )


class CaptureManager:
    def __init__(
        self,
        stream_config: StreamConfig,
        gcs_config: GCSConfig,
        redis_config: RedisConfig,
    ) -> None:
        self.stream_config = stream_config
        self.gcs = get_storage(gcs_config)
        self.redis = redis.Redis(
            host=redis_config.host, port=redis_config.port, db=redis_config.db,
            decode_responses=True,
        )
        self._workers: list[StreamCaptureWorker] = []
        self._stop = Event()

    def start(self) -> None:
        feeds = self.stream_config.get_feeds()
        if not feeds:
            log.error("no feeds configured")
            return

        log.info("cleaning up orphan ffmpeg processes", feeds=len(feeds))
        for feed_id in feeds:
            _kill_orphan_ffmpeg(feed_id)
        time.sleep(1)

        for feed_id, feed_name in feeds.items():
            worker = StreamCaptureWorker(
                feed_id=feed_id,
                feed_name=feed_name,
                stream_config=self.stream_config,
                gcs_client=self.gcs,
                redis_client=self.redis,
            )
            worker.start()
            self._workers.append(worker)

        log.info("capture manager started", feeds=len(self._workers))

        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT, lambda *_: self.stop())

        try:
            while not self._stop.is_set():
                self._stop.wait(10)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        log.info("stopping capture manager")
        self._stop.set()
        for w in self._workers:
            w.stop()
        log.info("capture manager stopped")

    def status(self) -> list[dict]:
        return [
            {
                "feed_id": w.feed_id,
                "feed_name": w.feed_name,
                "chunk_index": w._chunk_index,
                "running": w._thread is not None and w._thread.is_alive(),
            }
            for w in self._workers
        ]
