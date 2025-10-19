from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

try:
    # Prefer redis-py asyncio client if available
    from redis import asyncio as aioredis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    aioredis = None  # type: ignore

from .config import settings
from .domain import canonical_domain
from .ingest_queue import IngestQueue


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


@dataclass
class FeedItem:
    url: str
    source: str


class SeenCache:
    """URL-level de-duplication cache.

    Uses Redis SETNX with TTL when available. Falls back to in-memory set.
    """

    def __init__(self, ttl_seconds: int = 14 * 24 * 3600) -> None:
        self.ttl = ttl_seconds
        self._mem: set[str] = set()
        self._redis = None
        if aioredis is not None:
            try:
                self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            except Exception:
                self._redis = None

    async def mark_if_new(self, url: str) -> bool:
        key = f"phishradar:seen:url:{_sha1(url)}"
        if self._redis is not None:
            try:
                added = await self._redis.set(key, "1", nx=True, ex=self.ttl)  # type: ignore[attr-defined]
                return bool(added)
            except Exception:
                pass
        # Fallback to process-local memory cache
        if key in self._mem:
            return False
        self._mem.add(key)
        return True


class FeedPoller:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._queue = IngestQueue()
        self._seen = SeenCache(ttl_seconds=settings.feed_seen_ttl_seconds)
        self._logger = logging.getLogger(__name__)

    async def _fetch_openphish(self, client: httpx.AsyncClient) -> list[FeedItem]:
        url = settings.openphish_feed_url
        try:
            r = await client.get(url, headers={"User-Agent": "phishradar/1 feed"})
            r.raise_for_status()
            out: list[FeedItem] = []
            for line in r.text.splitlines():
                line = line.strip()
                if not line:
                    continue
                out.append(FeedItem(url=line, source="openphish"))
            return out
        except Exception as e:
            self._logger.warning(f"OpenPhish fetch failed: {e}")
            return []

    async def _fetch_sinkingyachts(self, client: httpx.AsyncClient) -> list[FeedItem]:
        base = settings.sinkingyachts_feed_url
        try:
            r = await client.get(
                base, params={"per_page": min(settings.feed_batch_limit, 500)}, headers={"User-Agent": "phishradar/1 feed"}
            )
            r.raise_for_status()
            data: list[dict[str, Any]] = r.json()  # type: ignore[assignment]
            out: list[FeedItem] = []
            for it in data:
                u = it.get("url")
                if not u:
                    continue
                out.append(FeedItem(url=str(u), source="sinkingyachts"))
            return out
        except Exception as e:
            self._logger.warning(f"SinkingYachts fetch failed: {e}")
            return []

    async def _poll_once(self) -> int:
        new_count = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            src1 = await self._fetch_openphish(client)
            src2 = await self._fetch_sinkingyachts(client)
        merged = src1 + src2
        # Basic URL-level dedup within this batch
        seen_local: set[str] = set()
        now_ts = int(time.time())
        for it in merged:
            u = it.url
            if not u or u in seen_local:
                continue
            seen_local.add(u)
            # Skip if seen recently via Redis
            try:
                is_new = await self._seen.mark_if_new(u)
            except Exception:
                is_new = True
            if not is_new:
                continue
            dom = str(canonical_domain(u))
            row = {"url": u, "domain": dom, "title": dom, "ts": now_ts, "src": it.source}
            try:
                await self._queue.push(row)
                new_count += 1
            except Exception as e:
                self._logger.warning(f"Failed to enqueue {u}: {e}")
        if new_count:
            self._logger.info(f"Feed poller enqueued {new_count} URLs")
        return new_count

    async def run(self) -> None:
        delay = max(10, int(settings.feed_poll_interval_seconds))
        # Initial warm-up short delay to let app start
        await asyncio.sleep(2)
        while not self._stop.is_set():
            try:
                await self._poll_once()
            except Exception as e:
                self._logger.error(f"Feed poller loop error: {e}")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                continue

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self.run(), name="feed-poller")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except Exception:
                pass

