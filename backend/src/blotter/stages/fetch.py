import time
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from blotter.config import BroadcastifyConfig
from blotter.log import get_logger
from blotter.models import ArchiveBlock

log = get_logger(__name__)


class BroadcastifyClient:
    def __init__(self, config: BroadcastifyConfig) -> None:
        self.config = config
        self.http = httpx.Client(timeout=30)
        self._last_request_time = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        min_interval = 1.0 / self.config.rate_limit_rps
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.monotonic()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30))
    def _get(self, params: dict[str, str]) -> dict:
        self._throttle()
        params["apiKey"] = self.config.api_key
        params["username"] = self.config.username
        resp = self.http.get(self.config.base_url, params=params)
        resp.raise_for_status()
        return resp.json()

    def get_feed_info(self, feed_id: str) -> dict:
        log.info("fetching feed info", feed_id=feed_id)
        return self._get({"a": "feed", "feedId": feed_id})

    def get_archives(
        self,
        feed_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[ArchiveBlock]:
        params: dict[str, str] = {"a": "archives", "feedId": feed_id}
        if start:
            params["start"] = str(int(start.timestamp()))
        if end:
            params["end"] = str(int(end.timestamp()))

        log.info("fetching archives", feed_id=feed_id, start=start, end=end)
        data = self._get(params)

        feed_info = data.get("feed", {})
        feed_name = feed_info.get("descr", feed_id)
        archives = data.get("archives", [])

        blocks = []
        for arc in archives:
            blocks.append(ArchiveBlock(
                feed_id=feed_id,
                feed_name=feed_name,
                timestamp=datetime.fromtimestamp(arc["ts"], tz=timezone.utc),
                duration_ms=arc.get("duration", 1800) * 1000,
                url=arc["url"],
            ))

        log.info("found archives", feed_id=feed_id, count=len(blocks))
        return blocks

    def close(self) -> None:
        self.http.close()
