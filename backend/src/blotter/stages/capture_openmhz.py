import json
import signal
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

import httpx
import redis

from blotter.config import GCSConfig, OpenMhzConfig, RedisConfig
from blotter.gcs import GCSClient, LocalStorageClient, get_storage
from blotter.log import get_logger
from blotter.models import ChunkTask
from blotter.queue import enqueue_chunk

log = get_logger(__name__)

TALKGROUP_NAMES: dict[str, dict[int, str]] = {}


def _talkgroup_label(system: str, tg_num: int) -> str:
    name = TALKGROUP_NAMES.get(system, {}).get(tg_num)
    if name:
        return name
    return f"TG {tg_num}"


def _system_display_name(system: str) -> str:
    names = {
        "lapdvalley": "LAPD Valley Bureau",
        "lapdwest": "LAPD West Bureau",
        "chi_cpd": "Chicago Police",
        "cltp25": "Charlotte-Mecklenburg Police",
        "philly": "Philadelphia Police",
        "psern1": "Seattle PSERN",
        "sfp25": "San Francisco Police",
        "pgcomd": "Prince George's County",
        "pdx2": "Portland Police",
        "ntirnd1": "Dallas Police",
        "nwhc": "NW Harris County",
        "dane_com": "Dane County",
        "monroecony": "Monroe County",
        "dcfd": "DC Fire & EMS",
        "mnhennco": "Hennepin County",
        "njicsunion": "NJICS Union County",
        "gcrn": "Cleveland Police",
        "mcbsimcast": "Macomb County",
        "sc21102": "St. Clair County",
        "scpd": "Suffolk County PD",
        "snacc": "Las Vegas Metro",
        "apsp25": "Atlanta Police",
        "bacop25": "Baltimore County",
        "indydps": "Indianapolis DPS",
    }
    return names.get(system, system)


def _feed_name(system: str, tg_num: int) -> str:
    display = _system_display_name(system)
    label = _talkgroup_label(system, tg_num)
    return f"{display} - {label}"


def _convert_to_wav(m4a_path: Path, wav_path: Path) -> bool:
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


def _process_call(
    call: dict,
    system: str,
    gcs: GCSClient | LocalStorageClient,
    r: redis.Redis,
    chunk_index: int,
) -> None:
    audio_url = call.get("url", "")
    tg_num = call.get("talkgroupNum", 0)
    call_len = call.get("len", 0)
    call_time = call.get("time")

    if not audio_url or call_len < 1:
        return

    if isinstance(call_time, str):
        try:
            ts = datetime.fromisoformat(call_time.replace("Z", "+00:00"))
        except ValueError:
            ts = datetime.now(timezone.utc)
    elif isinstance(call_time, (int, float)):
        ts = datetime.fromtimestamp(call_time / 1000 if call_time > 1e12 else call_time, tz=timezone.utc)
    else:
        ts = datetime.now(timezone.utc)

    feed_id = f"{system}-{tg_num}"
    feed_name = _feed_name(system, tg_num)

    with tempfile.TemporaryDirectory(prefix="blotter_omhz_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        m4a_path = tmpdir_path / "call.mp3"
        wav_path = tmpdir_path / "call.wav"

        for attempt in range(3):
            try:
                resp = httpx.get(audio_url, timeout=10, follow_redirects=True)
                resp.raise_for_status()
                m4a_path.write_bytes(resp.content)
                break
            except Exception:
                if attempt < 2:
                    time.sleep(1 + attempt)
                else:
                    log.warning("audio download failed", system=system, url=audio_url[:100])
                    return

        if not _convert_to_wav(m4a_path, wav_path):
            return

        date_str = ts.strftime("%Y-%m-%d")
        ts_str = ts.strftime("%Y%m%d_%H%M%S")
        gcs_path = f"{system}/{date_str}/{tg_num}-{ts_str}.wav"

        gcs.upload(wav_path, gcs_path)
        signed_url = gcs.signed_url(gcs_path)

        duration_ms = int(call_len * 1000)

        task = ChunkTask(
            feed_id=feed_id,
            feed_name=feed_name,
            chunk_path=gcs_path,
            audio_url=signed_url,
            chunk_ts=ts,
            chunk_index=chunk_index,
            duration_ms=duration_ms,
            skip_start=False,
        )
        enqueue_chunk(r, task)

        log.info(
            "call captured",
            system=system,
            talkgroup=tg_num,
            feed_name=feed_name,
            duration_s=round(call_len, 1),
        )


class OpenMhzCaptureManager:
    def __init__(
        self,
        openmhz_config: OpenMhzConfig,
        gcs_config: GCSConfig,
        redis_config: RedisConfig,
    ) -> None:
        self.config = openmhz_config
        self.gcs = get_storage(gcs_config)
        self.redis = redis.Redis(
            host=redis_config.host, port=redis_config.port, db=redis_config.db,
            password=redis_config.password or None, decode_responses=True,
        )
        self._stop = Event()

    def start(self) -> None:
        systems = [s.strip() for s in self.config.systems.split(",") if s.strip()]
        if not systems:
            log.error("no openmhz systems configured")
            return

        signal.signal(signal.SIGTERM, lambda *_: self._stop.set())
        signal.signal(signal.SIGINT, lambda *_: self._stop.set())

        log.info("openmhz capture manager starting", systems=len(systems))
        consecutive_failures = 0

        while not self._stop.is_set():
            try:
                self._run_poll_loop(systems)
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                delay = min(10 * (2 ** min(consecutive_failures - 1, 5)), 300)
                log.warning(
                    "browser poll loop failed, restarting",
                    failures=consecutive_failures,
                    retry_in=delay,
                    exc_info=True,
                )
                self._stop.wait(delay)

        log.info("openmhz capture manager stopped")

    def _solve_challenge(self, page) -> None:
        seed_url = f"{self.config.api_url}/lapdvalley/calls/newer?time=0"
        log.info("solving cloudflare challenge")
        page.goto(seed_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(5000)
        title = page.title()
        if "moment" in title.lower() or "challenge" in title.lower():
            log.warning("cloudflare challenge not solved, waiting longer")
            page.wait_for_timeout(15000)

    def _run_poll_loop(self, systems: list[str]) -> None:
        from threading import Thread
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            )
            page = ctx.new_page()
            page.set_default_timeout(15000)

            self._solve_challenge(page)

            last_times: dict[str, int] = {s: int(time.time() * 1000) for s in systems}
            chunk_index = 0
            executor = ThreadPoolExecutor(max_workers=32)
            self._last_poll = time.monotonic()

            def _watchdog() -> None:
                while not self._stop.is_set():
                    time.sleep(15)
                    if time.monotonic() - self._last_poll > 120:
                        log.warning("poll loop stale for 2min, killing browser")
                        try:
                            browser.close()
                        except Exception:
                            pass
                        return

            wd = Thread(target=_watchdog, daemon=True, name="poll-watchdog")
            wd.start()

            log.info("polling started", systems=systems)

            while not self._stop.is_set():
                for system in systems:
                    if self._stop.is_set():
                        break
                    try:
                        api_url = f"{self.config.api_url}/{system}/calls/newer?time={last_times[system]}"
                        result = page.evaluate(
                            """(url) => fetch(url, {
                                credentials: "include",
                                headers: { "Accept": "application/json" }
                            }).then(r => r.text()).catch(e => JSON.stringify({error: e.message}))""",
                            api_url,
                        )
                        self._last_poll = time.monotonic()

                        if not result:
                            continue

                        try:
                            data = json.loads(result)
                        except json.JSONDecodeError:
                            if "challenge" in result.lower() or "<html" in result.lower():
                                log.warning("cloudflare challenge detected, re-solving")
                                self._solve_challenge(page)
                            continue

                        if "error" in data:
                            log.warning("fetch error", system=system, error=data["error"])
                            continue

                        calls = data.get("calls", [])
                        seen_key = f"blotter:openmhz:seen:{system}"
                        new_calls = 0

                        for call in calls:
                            call_id = call.get("_id", "")
                            if not call_id or self.redis.sismember(seen_key, call_id):
                                continue
                            self.redis.sadd(seen_key, call_id)
                            self.redis.expire(seen_key, 86400)
                            new_calls += 1

                            executor.submit(
                                _process_call, call, system, self.gcs, self.redis, chunk_index,
                            )
                            chunk_index += 1

                            call_time = call.get("time")
                            if isinstance(call_time, str):
                                ct = datetime.fromisoformat(call_time.replace("Z", "+00:00"))
                                call_time_ms = int(ct.timestamp() * 1000)
                            elif isinstance(call_time, (int, float)):
                                call_time_ms = int(call_time) if call_time > 1e12 else int(call_time * 1000)
                            else:
                                call_time_ms = last_times[system]
                            if call_time_ms > last_times[system]:
                                last_times[system] = call_time_ms

                        if new_calls:
                            seen_count = self.redis.scard(seen_key)
                            log.info("poll cycle", system=system, new_calls=new_calls, total_seen=seen_count)

                    except Exception:
                        log.warning("poll cycle failed", system=system, exc_info=True)

                self._stop.wait(self.config.poll_interval)

            executor.shutdown(wait=True, cancel_futures=True)
            browser.close()
