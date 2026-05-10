import gc
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

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


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
    http_client: httpx.Client | None = None,
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

        try:
            client = http_client or httpx
            resp = client.get(audio_url, timeout=10, follow_redirects=True)
            resp.raise_for_status()
            m4a_path.write_bytes(resp.content)
            resp.close()
        except Exception:
            log.debug("audio download failed", system=system, tg=tg_num)
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


def _classify_response(text: str) -> str:
    lower = text[:1000].lower()
    if "you have been blocked" in lower or "attention required" in lower:
        return "blocked"
    if "just a moment" in lower or "challenge" in lower or "<html" in lower:
        return "challenge"
    return "unknown"


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
        import ctypes
        from playwright.sync_api import Error as PlaywrightError

        systems = [s.strip() for s in self.config.systems.split(",") if s.strip()]
        if not systems:
            log.error("no openmhz systems configured")
            return

        signal.signal(signal.SIGTERM, lambda *_: self._stop.set())
        signal.signal(signal.SIGINT, lambda *_: self._stop.set())

        try:
            _libc = ctypes.CDLL("libc.so.6", use_errno=True)
            self._malloc_trim = _libc.malloc_trim
        except Exception:
            self._malloc_trim = None

        self._call_count = 0
        self._pending_futures: list = []

        log.info("openmhz capture manager starting", systems=len(systems))
        consecutive_failures = 0
        audio_client = httpx.Client(
            timeout=10,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10, keepalive_expiry=30),
        )
        executor = ThreadPoolExecutor(max_workers=32)

        try:
            while not self._stop.is_set():
                try:
                    self._run_poll_loop(systems, executor, audio_client)
                    consecutive_failures = 0
                except PlaywrightError as e:
                    consecutive_failures += 1
                    delay = min(15 * consecutive_failures, 120)
                    log.warning(
                        "challenge solve failed, retrying",
                        failures=consecutive_failures,
                        retry_in=delay,
                        error=str(e).split("\n")[0],
                    )
                    self._stop.wait(delay)
                except Exception:
                    consecutive_failures += 1
                    delay = min(15 * consecutive_failures, 120)
                    log.warning(
                        "poll loop failed, restarting",
                        failures=consecutive_failures,
                        retry_in=delay,
                        exc_info=True,
                    )
                    self._stop.wait(delay)
                finally:
                    gc.collect()
                    if self._malloc_trim:
                        self._malloc_trim(0)
        finally:
            audio_client.close()
            executor.shutdown(wait=True, cancel_futures=True)

        log.info("openmhz capture manager stopped")

    def _obtain_cookies(self) -> httpx.Cookies:
        """Launch a temporary browser to solve the Cloudflare challenge."""
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth

        stealth = Stealth()
        cookies = httpx.Cookies()

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            try:
                ctx = browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                page = ctx.new_page()
                stealth.apply_stealth_sync(page)
                page.set_default_timeout(15000)

                seed_url = f"{self.config.api_url}/lapdvalley/calls/newer?time=0"
                log.info("solving cloudflare challenge", url=seed_url)
                page.goto(seed_url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)

                for attempt in range(3):
                    title = page.title().lower()
                    body = page.content()[:1000].lower()

                    if "blocked" in body or "attention required" in title:
                        raise RuntimeError("IP is hard-blocked by Cloudflare")

                    if "moment" not in title and "challenge" not in title:
                        for c in ctx.cookies():
                            cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
                        log.info("challenge solved", attempt=attempt, num_cookies=len(cookies))
                        return cookies

                    log.warning("cloudflare challenge active", attempt=attempt, title=page.title())
                    try:
                        cf_iframe = page.frame_locator("iframe[src*='challenge']").first
                        cf_iframe.locator("input[type='checkbox'], .cb-lb").click(timeout=5000)
                        log.info("clicked turnstile checkbox")
                    except Exception:
                        pass

                    page.wait_for_timeout(10000 + attempt * 10000)

                raise RuntimeError("Cloudflare challenge not solved after retries")
            finally:
                browser.close()

    def _submit_call(self, executor, call, system, audio_client, chunk_index):
        call_data = {
            "url": call.get("url", ""),
            "talkgroupNum": call.get("talkgroupNum", 0),
            "len": call.get("len", 0),
            "time": call.get("time"),
        }
        def _wrapped():
            _process_call(call_data, system, self.gcs, self.redis, chunk_index, audio_client)
            self._call_count += 1
            if self._call_count % 50 == 0:
                gc.collect()
                if self._malloc_trim:
                    self._malloc_trim(0)
        fut = executor.submit(_wrapped)
        self._pending_futures.append(fut)
        if len(self._pending_futures) > 100:
            self._pending_futures = [f for f in self._pending_futures if not f.done()]

    def _run_poll_loop(
        self,
        systems: list[str],
        executor: ThreadPoolExecutor,
        audio_client: httpx.Client,
    ) -> None:
        cookies = self._obtain_cookies()

        api_client = httpx.Client(
            timeout=15,
            cookies=cookies,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5, keepalive_expiry=30),
        )

        last_times: dict[str, int] = {s: int(time.time() * 1000) for s in systems}
        chunk_index = 0
        polls_since_solve = 0

        log.info("polling with cookies", systems=len(systems))

        try:
            while not self._stop.is_set():
                for system in systems:
                    if self._stop.is_set():
                        break
                    try:
                        api_url = f"{self.config.api_url}/{system}/calls/newer?time={last_times[system]}"
                        resp = api_client.get(api_url)

                        if resp.status_code != 200:
                            kind = _classify_response(resp.text)
                            if kind in ("blocked", "challenge"):
                                if polls_since_solve == 0:
                                    raise RuntimeError("cookies rejected immediately — TLS fingerprint may be blocked")
                                log.warning("cloudflare challenge, re-solving", system=system)
                                return
                            continue

                        try:
                            data = json.loads(resp.text)
                        except json.JSONDecodeError:
                            kind = _classify_response(resp.text)
                            if kind in ("blocked", "challenge"):
                                if polls_since_solve == 0:
                                    raise RuntimeError("cookies rejected immediately — TLS fingerprint may be blocked")
                                log.warning("cloudflare challenge in response, re-solving", system=system)
                                return
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

                            self._submit_call(executor, call, system, audio_client, chunk_index)
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

                polls_since_solve += 1
                self._stop.wait(self.config.poll_interval)
        finally:
            api_client.close()
