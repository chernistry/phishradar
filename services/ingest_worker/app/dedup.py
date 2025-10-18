from __future__ import annotations

from typing import Any

from .config import settings
from .qdrant_client import QdrantStore


def is_duplicate(similarity: float, *, same_domain: bool) -> bool:
    """Decide duplicate based on similarity floors.

    - If the nearest neighbor is from the same domain, use a lower threshold.
    - For cross-domain duplicates, require a stricter (higher) similarity.
    """
    same_dom_floor = float(getattr(settings, "dedup_same_domain_min_sim", 0.94))
    global_floor = float(getattr(settings, "dedup_global_min_sim", 0.985))
    floor = same_dom_floor if same_domain else global_floor
    return similarity >= floor


async def upsert_and_check(
    url: str, vector: list[float], payload: dict[str, Any]
) -> tuple[bool, float, str | None]:
    store = QdrantStore()
    domain = (payload.get("domain") or "") if isinstance(payload, dict) else ""
    best: tuple[str, float, dict[str, Any]] | None = None
    # Prefer same-domain neighbors
    hits_same = await store.search_same_domain(vector, str(domain), top_k=5) if domain else []
    hits_all = []
    if not hits_same:
        hits_all = await store.search(vector, top_k=5)

    # Choose best by similarity across the candidate lists
    for src in (hits_same, hits_all):
        for pid, sim, pl in src:
            if best is None or sim > best[1]:
                best = (pid, sim, pl)

    max_sim = best[1] if best else 0.0
    nn_domain = (best[2].get("domain") if best else None) or ""
    same_dom = bool(domain and nn_domain and str(domain) == str(nn_domain)) if best else False
    dup = is_duplicate(max_sim, same_domain=same_dom)
    qid = await store.upsert(url, vector, payload)
    return dup, max_sim, qid if dup else None
