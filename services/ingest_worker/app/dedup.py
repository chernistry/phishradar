from __future__ import annotations

import logging
from typing import Any

from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException

from .config import settings
from .qdrant_client import QdrantStore
from .domain import canonical_domain

logger = logging.getLogger(__name__)


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
    # Always derive canonical domain from the URL; do not trust incoming payload
    domain = canonical_domain(url)
    best: tuple[str, float, dict[str, Any]] | None = None
    
    try:
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
    except (UnexpectedResponse, ResponseHandlingException) as e:
        logger.error(f"Qdrant search failed for URL {url}: {e}")
        # Continue with empty results - will treat as non-duplicate
        best = None
    except Exception as e:
        logger.exception(f"Unexpected error during dedup search for URL {url}: {e}")
        raise

    max_sim = best[1] if best else 0.0
    nn_domain = (best[2].get("domain") if best else None) or ""
    same_dom = bool(domain and nn_domain and str(domain) == str(nn_domain)) if best else False
    # Cross-domain duplicates can be disabled via config by setting a very high global floor
    dup = is_duplicate(max_sim, same_domain=same_dom)
    # Ensure stored payload contains the derived canonical domain
    clean_payload = dict(payload) if isinstance(payload, dict) else {}
    clean_payload["domain"] = domain
    
    try:
        qid = await store.upsert(url, vector, clean_payload)
    except (UnexpectedResponse, ResponseHandlingException) as e:
        logger.error(f"Qdrant upsert failed for URL {url}: {e}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during upsert for URL {url}: {e}")
        raise
    
    return dup, max_sim, qid if dup else None
