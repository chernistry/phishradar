#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass
import os
from typing import Iterable
from urllib.parse import urlparse

import httpx


# OpenPhish public feed moved to GitHub
OPENPHISH_FEED = "https://raw.githubusercontent.com/openphish/public_feed/refs/heads/main/feed.txt"
# PhishTank registrations closed; skip unless an explicit URL is provided
PHISHTANK_FEED_DEFAULT = None
# Community API (no key): returns JSON objects with a `url` field
SINKINGYACHTS_FEED = "https://phish.sinking.yachts/v2/urls"


@dataclass
class SeedStats:
    total: int = 0
    embedded: int = 0
    new: int = 0
    duplicates: int = 0
    failed: int = 0


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


async def fetch_openphish(limit: int, client: httpx.AsyncClient) -> list[str]:
    try:
        r = await client.get(OPENPHISH_FEED, headers={"User-Agent": "curl/8 seed"})
        r.raise_for_status()
        urls = []
        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                continue
            urls.append(line)
            if len(urls) >= limit:
                break
        return urls
    except Exception:
        return []


async def fetch_phishtank(limit: int, client: httpx.AsyncClient, url: str | None) -> list[str]:
    if not url:
        return []
    try:
        r = await client.get(url, headers={"User-Agent": "curl/8 seed"})
        r.raise_for_status()
        data = r.json()
        out: list[str] = []
        for it in data:
            u = it.get("url")
            if u:
                out.append(u)
                if len(out) >= limit:
                    break
        return out
    except Exception:
        return []


async def fetch_sinkingyachts(limit: int, client: httpx.AsyncClient) -> list[str]:
    """Fetch recent phishing URLs from SinkingYachts community API.
    API is unauthenticated; apply per_page limit and simple pagination guard.
    """
    try:
        # Try to request up to `limit` in one call if supported
        r = await client.get(SINKINGYACHTS_FEED, params={"per_page": min(limit, 500)}, headers={"User-Agent": "curl/8 seed"})
        r.raise_for_status()
        data = r.json()
        out: list[str] = []
        for it in data:
            u = it.get("url")
            if u:
                out.append(u)
                if len(out) >= limit:
                    break
        return out
    except Exception:
        return []


async def seed(urls: Iterable[str], api_base: str, concurrency: int) -> SeedStats:
    stats = SeedStats(total=0)
    sem = asyncio.Semaphore(concurrency)

    async def process(u: str) -> None:
        nonlocal stats
        async with sem:
            stats.total += 1
            dom = _domain(u)
            title = dom
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    t0 = time.perf_counter()
                    er = await client.post(
                        f"{api_base}/embed",
                        json={"url": u, "title": title, "domain": dom},
                    )
                    er.raise_for_status()
                    e = er.json()
                    stats.embedded += 1
                    vec = e["vector"]
                    dr = await client.post(
                        f"{api_base}/dedup",
                        json={
                            "url": u,
                            "vector": vec,
                            "payload": {"domain": dom, "title": title, "ts": int(time.time())},
                        },
                    )
                    dr.raise_for_status()
                    d = dr.json()
                    if d.get("is_duplicate"):
                        stats.duplicates += 1
                    else:
                        stats.new += 1
            except Exception:
                stats.failed += 1

    await asyncio.gather(*(process(u) for u in urls))
    return stats


async def main() -> None:
    ap = argparse.ArgumentParser(description="Seed Qdrant with baseline phishing URLs")
    ap.add_argument("--limit", type=int, default=200, help="Max URLs per source")
    ap.add_argument("--phishtank", default=None, help="PhishTank JSON URL (optional)")
    ap.add_argument("--api", default="http://localhost:8000", help="API base URL")
    ap.add_argument("--concurrency", type=int, default=10, help="Concurrent requests")
    ap.add_argument("--file", default="scripts/seeds/baseline.txt", help="Local fallback file with URLs (one per line)")
    ap.add_argument("--qurl", default=os.getenv("QDRANT_URL", "http://localhost:6333"), help="Qdrant URL")
    ap.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "phishradar_urls"), help="Qdrant collection name")
    ns = ap.parse_args()

    async with httpx.AsyncClient(timeout=30.0) as client:
        src1 = await fetch_openphish(ns.limit, client)
        src2 = await fetch_phishtank(ns.limit, client, ns.phishtank)
        src3 = await fetch_sinkingyachts(ns.limit, client)
    # De-duplicate and basic sanity
    urls = []
    seen: set[str] = set()
    for u in src1 + src2 + src3:
        if not u or u in seen:
            continue
        seen.add(u)
        urls.append(u)

    # Fallback to local file if nothing fetched
    if not urls:
        try:
            with open(ns.file, "r", encoding="utf-8") as fh:
                for line in fh:
                    u = line.strip()
                    if not u or u in seen:
                        continue
                    seen.add(u)
                    urls.append(u)
        except Exception:
            pass

    # Ensure Qdrant collection exists with proper dimension by probing /embed once
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            probe = await client.post(f"{ns.api}/embed", json={"url": "https://example.com/probe", "title": "probe", "domain": "example.com"})
            probe.raise_for_status()
            dim = int(len(probe.json().get("vector") or []))
        except Exception:
            dim = 0
        if dim > 0:
            # Create collection if missing or mismatched
            try:
                r = await client.get(f"{ns.qurl}/collections/{ns.collection}")
                if r.status_code != 200 or int((r.json().get("result", {}).get("config", {}).get("params", {}).get("vectors", {}).get("size", 0))) != dim:
                    await client.put(
                        f"{ns.qurl}/collections/{ns.collection}",
                        headers={"content-type": "application/json"},
                        json={"vectors": {"size": dim, "distance": "Cosine"}},
                    )
            except Exception:
                # Best-effort; continue
                pass

    print(f"Collected {len(urls)} URLs; seeding via {ns.api}")
    stats = await seed(urls, ns.api, ns.concurrency)
    print(
        f"Done. total={stats.total} embedded={stats.embedded} new={stats.new} duplicates={stats.duplicates} failed={stats.failed}"
    )


if __name__ == "__main__":
    asyncio.run(main())
