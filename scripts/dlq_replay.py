#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

from phishradar.services.ingest_worker.app.paths import BUFFER_DIR
from phishradar.services.ingest_worker.app.qdrant_client import QdrantStore


async def replay_qdrant_upsert(path: str) -> int:
    store = QdrantStore()
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                payload = row.get("payload") or {}
                url = payload.get("url") or (payload.get("payload") or {}).get("url")
                vec_dim = int(payload.get("vector_dim") or 0)
                # We cannot reconstruct vector from DLQ safely; skip if missing vector
                vector = payload.get("vector") or []
                if not url or not isinstance(vector, list) or not vector:
                    continue
                await store.upsert(url, vector, payload.get("payload") or {})
                n += 1
            except Exception:
                continue
    return n


async def main() -> None:
    ap = argparse.ArgumentParser(description="Replay DLQ operations")
    ap.add_argument("op", choices=["qdrant_upsert"], help="DLQ operation to replay")
    ns = ap.parse_args()
    dlq_dir = os.path.join(BUFFER_DIR, "dlq")
    path = os.path.join(dlq_dir, f"{ns.op}.jsonl")
    if not os.path.exists(path):
        print("No DLQ file found", flush=True)
        return
    if ns.op == "qdrant_upsert":
        n = await replay_qdrant_upsert(path)
        print(f"Replayed {n} entries from {ns.op}")


if __name__ == "__main__":
    asyncio.run(main())

