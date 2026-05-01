import asyncio
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

import redis

from blotter.config import GCSConfig, OpenMhzConfig, RedisConfig
from blotter.gcs import GCSClient, LocalStorageClient, get_storage
from blotter.log import get_logger
from blotter.models import ChunkTask
from blotter.queue import enqueue_chunk

log = get_logger(__name__)

TALKGROUP_NAMES: dict[str, dict[int, str]] = {
    "lapdvalley": {},
    "lapdwest": {},
}


def _talkgroup_label(system: str, tg_num: int) -> str:
    name = TALKGROUP_NAMES.get(system, {}).get(tg_num)
    if name:
        return name
    return f"TG {tg_num}"


def _system_display_name(system: str) -> str:
    names = {
        "lapdvalley": "LAPD Valley Bureau",
        "lapdwest": "LAPD West Bureau",
    }
    return names.get(system, system)


def _feed_name(system: str, tg_num: int) -> str:
    display = _system_display_name(system)
    label = _talkgroup_label(system, tg_num)
    return f"{display} - {label}"


def _convert_m4a_to_wav(m4a_path: Path, wav_path: Path) -> bool:
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(m4a_path),
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                str(wav_path),
            ],
            check=True, capture_output=True, timeout=30,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.error("m4a conversion failed", error=str(e))
        return False


class OpenMhzSystemWorker:
    def __init__(
        self,
        system: str,
        config: OpenMhzConfig,
        gcs_client: GCSClient | LocalStorageClient,
        redis_client: redis.Redis,
    ) -> None:
        self.system = system
        self.config = config
        self.gcs = gcs_client
        self.redis = redis_client
        self._stop = Event()
        self._thread: Thread | None = None
        self._chunk_index = 0
        self._last_call_time: float = 0

    def start(self) -> None:
        self._thread = Thread(
            target=self._run, name=f"openmhz-{self.system}", daemon=True,
        )
        self._thread.start()
        log.info("openmhz worker started", system=self.system)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=15)

    def _run(self) -> None:
        consecutive_failures = 0
        while not self._stop.is_set():
            try:
                if self.config.use_socketio:
                    self._run_socketio()
                else:
                    self._run_polling()
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                delay = min(10 * (2 ** min(consecutive_failures - 1, 5)), 300)
                log.warning(
                    "openmhz worker failed, reconnecting",
                    system=self.system,
                    failures=consecutive_failures,
                    retry_in=delay,
                    exc_info=True,
                )
                self._stop.wait(delay)

    def _run_socketio(self) -> None:
        import socketio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        sio = socketio.AsyncClient(
            reconnection=True,
            reconnection_attempts=0,
            reconnection_delay=5,
            reconnection_delay_max=60,
        )

        @sio.on("new message")
        async def on_call(data: dict) -> None:
            try:
                self._process_call(data)
            except Exception:
                log.error("call processing failed", system=self.system, exc_info=True)

        @sio.on("connect")
        async def on_connect() -> None:
            log.info("socketio connected", system=self.system)
            await sio.emit("start", {
                "shortName": self.system,
                "filterCode": "",
                "filterType": "",
                "filterStarred": False,
            })

        @sio.on("disconnect")
        async def on_disconnect() -> None:
            log.warning("socketio disconnected", system=self.system)

        async def main() -> None:
            await sio.connect(self.config.api_url, transports=["websocket"])
            while not self._stop.is_set():
                await asyncio.sleep(1)
            await sio.disconnect()

        try:
            loop.run_until_complete(main())
        finally:
            loop.close()

    def _run_polling(self) -> None:
        import httpx

        last_time = int(time.time() * 1000)
        log.info("polling started", system=self.system)

        while not self._stop.is_set():
            try:
                resp = httpx.get(
                    f"{self.config.api_url}/{self.system}/calls/newer",
                    params={"time": str(last_time)},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; Blotter/1.0)"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    calls = data.get("calls", [])
                    for call in calls:
                        try:
                            self._process_call(call)
                            call_time = call.get("time")
                            if call_time and call_time > last_time:
                                last_time = call_time
                        except Exception:
                            log.error("call processing failed", system=self.system, exc_info=True)
                elif resp.status_code == 403:
                    log.warning("cloudflare blocked, retrying", system=self.system)
                else:
                    log.warning("polling error", system=self.system, status=resp.status_code)
            except Exception:
                log.warning("polling request failed", system=self.system, exc_info=True)

            self._stop.wait(self.config.poll_interval)

    def _process_call(self, call: dict) -> None:
        audio_url = call.get("url", "")
        tg_num = call.get("talkgroupNum", 0)
        call_len = call.get("len", 0)
        call_time = call.get("time")

        if not audio_url or call_len < 1:
            return

        if isinstance(call_time, (int, float)):
            ts = datetime.fromtimestamp(call_time / 1000 if call_time > 1e12 else call_time, tz=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        feed_id = f"{self.system}-{tg_num}"
        feed_name = _feed_name(self.system, tg_num)

        with tempfile.TemporaryDirectory(prefix="blotter_omhz_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            m4a_path = tmpdir_path / "call.m4a"
            wav_path = tmpdir_path / "call.wav"

            import httpx
            try:
                resp = httpx.get(audio_url, timeout=30, follow_redirects=True)
                resp.raise_for_status()
                m4a_path.write_bytes(resp.content)
            except Exception:
                log.warning("audio download failed", system=self.system, url=audio_url[:100])
                return

            if not _convert_m4a_to_wav(m4a_path, wav_path):
                return

            date_str = ts.strftime("%Y-%m-%d")
            ts_str = ts.strftime("%Y%m%d_%H%M%S")
            gcs_path = f"{self.system}/{date_str}/{tg_num}-{ts_str}.wav"

            self.gcs.upload(wav_path, gcs_path)
            signed_url = self.gcs.signed_url(gcs_path)

            duration_ms = int(call_len * 1000)

            task = ChunkTask(
                feed_id=feed_id,
                feed_name=feed_name,
                chunk_path=gcs_path,
                audio_url=signed_url,
                chunk_ts=ts,
                chunk_index=self._chunk_index,
                duration_ms=duration_ms,
                skip_start=False,
            )
            enqueue_chunk(self.redis, task)

            self._chunk_index += 1
            log.info(
                "call captured",
                system=self.system,
                talkgroup=tg_num,
                feed_name=feed_name,
                duration_s=round(call_len, 1),
                chunk=self._chunk_index,
            )


class OpenMhzCaptureManager:
    def __init__(
        self,
        openmhz_config: OpenMhzConfig,
        gcs_config: GCSConfig,
        redis_config: RedisConfig,
    ) -> None:
        self.openmhz_config = openmhz_config
        self.gcs = get_storage(gcs_config)
        self.redis = redis.Redis(
            host=redis_config.host, port=redis_config.port, db=redis_config.db,
            password=redis_config.password or None, decode_responses=True,
        )
        self._workers: list[OpenMhzSystemWorker] = []
        self._stop = Event()

    def start(self) -> None:
        systems = [s.strip() for s in self.openmhz_config.systems.split(",") if s.strip()]
        if not systems:
            log.error("no openmhz systems configured")
            return

        for system in systems:
            worker = OpenMhzSystemWorker(
                system=system,
                config=self.openmhz_config,
                gcs_client=self.gcs,
                redis_client=self.redis,
            )
            worker.start()
            self._workers.append(worker)

        log.info("openmhz capture manager started", systems=len(self._workers))

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
        log.info("stopping openmhz capture manager")
        self._stop.set()
        for w in self._workers:
            w.stop()
        log.info("openmhz capture manager stopped")
