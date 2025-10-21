from __future__ import annotations

import hashlib
from typing import Any
import uuid

import asyncio
import time
from anyio import to_thread
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from .config import settings
from .rate_limit import AsyncRateLimiter
from .logging_metrics import (
    qdrant_requests_total,
    qdrant_failures_total,
    qdrant_latency_seconds,
    qdrant_retries_total,
)
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type, before_sleep_log
import logging
from .dlq import write_dlq


def id_key(url: str) -> str:
    # Qdrant supports integer or UUID point ids. Use deterministic UUIDv5 from URL.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url))


class QdrantStore:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.qdrant_url)
        self.collection = settings.qdrant_collection
        self._limiter = AsyncRateLimiter(float(settings.qdrant_rps))

    async def _call(self, op: str, fn):
        logger = logging.getLogger(__name__)

        @retry(
            reraise=True,
            stop=stop_after_attempt(settings.retry_max_attempts),
            wait=wait_exponential_jitter(initial=settings.retry_initial_delay, max=settings.retry_max_delay),
            retry=retry_if_exception_type(Exception),
            before_sleep=lambda rs: qdrant_retries_total.labels(op=op).inc(),
        )
        async def _run():
            await self._limiter.acquire()
            start = time.perf_counter()
            qdrant_requests_total.labels(op=op).inc()
            try:
                async with asyncio.timeout(settings.qdrant_timeout):
                    # Run blocking client call in a thread
                    return await to_thread.run_sync(fn)
            except Exception:
                qdrant_failures_total.labels(op=op).inc()
                raise
            finally:
                elapsed = time.perf_counter() - start
                qdrant_latency_seconds.labels(op=op).observe(elapsed)

        return await _run()

    async def ensure_collection(self, vector_size: int) -> None:
        try:
            col = await self._call("get_collection", lambda: self.client.get_collection(self.collection))
            exist_size = int(col.config.params.vectors.size)  # type: ignore[assignment]
            if exist_size != int(vector_size):
                await self._call("delete_collection", lambda: self.client.delete_collection(self.collection))
                await self._call(
                    "recreate_collection",
                    lambda: self.client.recreate_collection(
                        collection_name=self.collection,
                        vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
                    ),
                )
        except Exception:
            await self._call(
                "recreate_collection",
                lambda: self.client.recreate_collection(
                    collection_name=self.collection,
                    vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
                ),
            )

    async def ensure_payload_indexes(self) -> None:
        try:
            await self._call(
                "create_index_domain",
                lambda: self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name="domain",
                    field_schema=qm.PayloadSchemaType.KEYWORD,
                ),
            )
        except Exception:
            pass
        try:
            await self._call(
                "create_index_ts",
                lambda: self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name="ts",
                    field_schema=qm.PayloadSchemaType.INTEGER,
                ),
            )
        except Exception:
            pass

    async def upsert(self, url: str, vector: list[float], payload: dict[str, Any]) -> str:
        point_id = id_key(url)
        try:
            await self._call(
                "upsert",
                lambda: self.client.upsert(
                    collection_name=self.collection,
                    points=[
                        qm.PointStruct(id=point_id, vector=vector, payload={**payload, "url": url}),
                    ],
                    wait=True,
                ),
            )
        except Exception as e:
            write_dlq("qdrant_upsert", {"url": url, "payload": payload, "vector_dim": len(vector)}, str(e))
            raise
        return point_id

    async def search(self, vector: list[float], top_k: int = 5) -> list[tuple[str, float, dict[str, Any]]]:
        res = await self._call(
            "search",
            lambda: self.client.search(
                collection_name=self.collection,
                query_vector=vector,
                limit=top_k,
                with_payload=True,
            ),
        )
        out: list[tuple[str, float, dict[str, Any]]] = []
        for p in res:
            pid = str(p.id)
            payload = p.payload or {}
            out.append((pid, float(p.score), payload))
        return out

    async def search_same_domain(
        self, vector: list[float], domain: str, top_k: int = 5
    ) -> list[tuple[str, float, dict[str, Any]]]:
        res = await self._call(
            "search_same_domain",
            lambda: self.client.search(
                collection_name=self.collection,
                query_vector=vector,
                limit=top_k,
                query_filter=qm.Filter(
                    must=[qm.FieldCondition(key="domain", match=qm.MatchValue(value=domain))]
                ),
                with_payload=True,
            ),
        )
        return [(str(p.id), float(p.score), p.payload or {}) for p in res]
