#!/usr/bin/env python3
from __future__ import annotations

import argparse
import uuid
from qdrant_client import QdrantClient


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="URL used as point key (uuid5)")
    ap.add_argument("--qurl", default="http://localhost:6333")
    ap.add_argument("--collection", default="phishradar_urls")
    ns = ap.parse_args()
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, ns.url))
    cli = QdrantClient(url=ns.qurl)
    res = cli.retrieve(collection_name=ns.collection, ids=[pid], with_payload=True, with_vectors=False)
    for r in res:
        print({"id": str(r.id), "payload": r.payload})


if __name__ == "__main__":
    main()

