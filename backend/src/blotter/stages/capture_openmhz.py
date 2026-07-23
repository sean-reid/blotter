import gc
import json
import signal
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

import httpx
import redis

from blotter.config import GCSConfig, OpenMhzConfig, RedisConfig
from blotter.gcs import LocalStorageClient, get_storage
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


def _process_call(
    call: dict,
    system: str,
    gcs: LocalStorageClient,
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

    age = (datetime.now(timezone.utc) - ts).total_seconds()
    if age > 300:
        return

    feed_id = f"{system}-{tg_num}"
    feed_name = _feed_name(system, tg_num)

    with tempfile.TemporaryDirectory(prefix="blotter_omhz_") as tmpdir:
        mp3_path = Path(tmpdir) / "call.mp3"

        try:
            client = http_client or httpx
            for attempt in range(5):
                resp = client.get(audio_url, timeout=10, follow_redirects=True)
                if resp.status_code == 429:
                    time.sleep(3 * (2 ** attempt))
                    continue
                resp.raise_for_status()
                break
            else:
                log.debug("audio rate limited", system=system, tg=tg_num)
                return
            mp3_path.write_bytes(resp.content)
            resp.close()
        except Exception:
            log.debug("audio download failed", system=system, tg=tg_num)
            return

        date_str = ts.strftime("%Y-%m-%d")
        ts_str = ts.strftime("%Y%m%d_%H%M%S")
        storage_path = f"{system}/{date_str}/{tg_num}-{ts_str}.mp3"

        gcs.upload(mp3_path, storage_path)
        signed_url = gcs.signed_url(storage_path)

        duration_ms = int(call_len * 1000)

        task = ChunkTask(
            feed_id=feed_id,
            feed_name=feed_name,
            chunk_path=storage_path,
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
        self._last_times: dict[str, int] = {}
        self._chunk_index = 0
        self._call_count = 0
        self._pending_futures: list = []
        self._malloc_trim = None

    def _obtain_cookies(self) -> dict[str, str] | None:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth

        seed_url = f"{self.config.api_url}/lapdvalley/calls/newer?time=0"
        log.info("obtaining cloudflare cookies", url=seed_url)

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
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                page = ctx.new_page()
                Stealth().apply_stealth_sync(page)
                page.set_default_timeout(15000)

                page.goto(seed_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                for attempt in range(3):
                    title = page.title().lower()
                    body = page.content()[:1000].lower()

                    if "blocked" in body or "attention required" in title:
                        log.error("ip hard-blocked by cloudflare", attempt=attempt)
                        return None

                    if "moment" not in title and "challenge" not in title:
                        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
                        log.info("cookies obtained", attempt=attempt, count=len(cookies))
                        return cookies

                    log.warning("challenge active", attempt=attempt, title=page.title())
                    try:
                        cf_iframe = page.frame_locator("iframe[src*='challenge']").first
                        cf_iframe.locator("input[type='checkbox'], .cb-lb").click(timeout=5000)
                        log.info("clicked turnstile checkbox")
                    except Exception:
                        pass
                    page.wait_for_timeout(10000 + attempt * 10000)

                log.error("challenge not solved after retries")
                return None
            finally:
                browser.close()

    def start(self) -> None:
        import ctypes

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

        self._last_times = {s: int(time.time() * 1000) for s in systems}

        proxy_str = self.config.proxies.strip()
        proxies = [p.strip() for p in proxy_str.split(",") if p.strip()] if proxy_str else []
        if proxies:
            log.info("proxy rotation enabled", count=len(proxies))
        proxy_idx = 0
        consecutive_blocks = 0

        log.info("openmhz capture starting", systems=len(systems))
        consecutive_failures = 0
        challenge_retries = 0
        first_proxy = proxies[0] if proxies else None
        http_client = httpx.Client(
            timeout=10,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=10, keepalive_expiry=30),
            proxy=first_proxy,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"},
        )
        executor = ThreadPoolExecutor(max_workers=10)

        try:
            while not self._stop.is_set():
                proxy = proxies[proxy_idx] if proxies else None
                try:
                    consecutive_failures = 0
                    polls_done = self._run_poll_loop(
                        systems, executor, http_client, {}, proxy=proxy,
                    )

                    if polls_done is True:
                        consecutive_blocks += 1
                        if proxies:
                            proxy_idx = (proxy_idx + 1) % len(proxies)
                            log.warning(
                                "ip blocked, rotating proxy",
                                next_proxy=proxy_idx,
                                total_proxies=len(proxies),
                                consecutive_blocks=consecutive_blocks,
                            )
                            if consecutive_blocks >= len(proxies) * 2:
                                log.error("all proxies exhausted, stopping")
                                self._stop.set()
                                break
                            self._stop.wait(30)
                        else:
                            if consecutive_blocks >= 3:
                                log.error(
                                    "ip hard-blocked 3 times with no proxies configured, "
                                    "stopping — set OPENMHZ_PROXIES to enable rotation",
                                )
                                self._stop.set()
                                break
                            delay = 60 * consecutive_blocks
                            log.warning(
                                "tls rejection, backing off",
                                rejections=consecutive_blocks,
                                retry_in=delay,
                            )
                            self._stop.wait(delay)
                    elif polls_done == 0:
                        consecutive_blocks += 1
                        challenge_retries += 1
                        delay = min(30 * challenge_retries, 300)
                        log.warning("challenge on first poll, backing off",
                                    retries=challenge_retries, retry_in=delay)
                        self._stop.wait(delay)
                    else:
                        consecutive_blocks = 0
                        challenge_retries = 0

                except Exception:
                    consecutive_failures += 1
                    delay = min(15 * consecutive_failures, 120)
                    log.warning(
                        "poll loop failed",
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
            http_client.close()
            executor.shutdown(wait=True, cancel_futures=True)

        log.info("openmhz capture stopped")

    def _submit_call(self, executor, call, system, http_client):
        self._pending_futures = [f for f in self._pending_futures if not f.done()]
        if len(self._pending_futures) > 60:
            return

        call_data = {
            "url": call.get("url", ""),
            "talkgroupNum": call.get("talkgroupNum", 0),
            "len": call.get("len", 0),
            "time": call.get("time"),
        }
        idx = self._chunk_index
        self._chunk_index += 1

        def _wrapped():
            _process_call(call_data, system, self.gcs, self.redis, idx, http_client)
            self._call_count += 1
            if self._call_count % 50 == 0:
                gc.collect()
                if self._malloc_trim:
                    self._malloc_trim(0)

        fut = executor.submit(_wrapped)
        self._pending_futures.append(fut)

    def _run_poll_loop(
        self,
        systems: list[str],
        executor: ThreadPoolExecutor,
        http_client: httpx.Client,
        cookies: dict[str, str],
        proxy: str | None = None,
    ) -> bool | int:
        """Poll API using curl_cffi. Returns True if hard-blocked, 0 if challenge on first poll, or polls_since_cookies (>0) on normal cookie refresh."""
        from curl_cffi.requests import Session

        COOKIE_REFRESH_SECONDS = 1800

        session = Session(impersonate="safari", proxy=proxy)
        for name, value in cookies.items():
            session.cookies.set(name, value, domain=".openmhz.com")

        cookie_start = time.monotonic()
        polls_since_cookies = 0
        log.info("polling started", systems=systems, cookie_count=len(cookies),
                 proxy=bool(proxy))

        try:
            while not self._stop.is_set():
                if time.monotonic() - cookie_start > COOKIE_REFRESH_SECONDS:
                    log.info(
                        "refreshing cookies",
                        uptime_min=round((time.monotonic() - cookie_start) / 60),
                    )
                    return polls_since_cookies

                for system in systems:
                    if self._stop.is_set():
                        break
                    try:
                        api_url = (
                            f"{self.config.api_url}/{system}/calls/newer"
                            f"?time={self._last_times[system]}"
                        )
                        resp = session.get(api_url, timeout=10)

                        if resp.status_code == 403:
                            kind = _classify_response(resp.text)
                            if kind == "blocked":
                                log.error("ip hard-blocked by cloudflare", system=system)
                                return True
                            log.debug("403 challenge, skipping system", system=system)
                            continue

                        if resp.status_code != 200:
                            log.warning(
                                "unexpected status",
                                system=system,
                                status=resp.status_code,
                            )
                            continue

                        text = resp.text
                        try:
                            data = json.loads(text)
                        except json.JSONDecodeError:
                            kind = _classify_response(text)
                            if kind in ("blocked", "challenge"):
                                log.warning("cloudflare challenge", kind=kind, system=system)
                                return polls_since_cookies
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

                            self._submit_call(executor, call, system, http_client)

                            call_time = call.get("time")
                            if isinstance(call_time, str):
                                ct = datetime.fromisoformat(call_time.replace("Z", "+00:00"))
                                call_time_ms = int(ct.timestamp() * 1000)
                            elif isinstance(call_time, (int, float)):
                                call_time_ms = (
                                    int(call_time) if call_time > 1e12
                                    else int(call_time * 1000)
                                )
                            else:
                                call_time_ms = self._last_times[system]
                            if call_time_ms > self._last_times[system]:
                                self._last_times[system] = call_time_ms

                        if new_calls:
                            seen_count = self.redis.scard(seen_key)
                            log.info(
                                "poll cycle",
                                system=system,
                                new_calls=new_calls,
                                total_seen=seen_count,
                            )

                    except Exception:
                        log.warning("poll cycle failed", system=system, exc_info=True)

                polls_since_cookies += 1
                self._stop.wait(self.config.poll_interval)

            return polls_since_cookies
        finally:
            session.close()
