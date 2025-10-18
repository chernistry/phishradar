from __future__ import annotations

from typing import Any

from .config import settings
from .qdrant_client import QdrantStore


def is_duplicate(similarity: float, threshold: float | None = None) -> bool:
    th = threshold if threshold is not None else settings.dedup_threshold
    return similarity >= (1.0 - th)


async def upsert_and_check(
    url: str, vector: list[float], payload: dict[str, Any]
) -> tuple[bool, float, str | None]:
    store = QdrantStore()
    domain = payload.get("domain")
    if domain:
        hits = await store.search_same_domain(vector, str(domain), top_k=5)
        if not hits:
            hits = await store.search(vector, top_k=5)
    else:
        hits = await store.search(vector, top_k=5)
    max_sim = 0.0
    max_id: str | None = None
    for pid, sim in hits:
        if sim > max_sim:
            max_sim, max_id = sim, pid
    dup = is_duplicate(max_sim)
    qid = await store.upsert(url, vector, payload)
    return dup, max_sim, qid if dup else None
