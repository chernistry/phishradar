#!/usr/bin/env python3
import argparse

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["recreate", "drop", "info"])  # noqa: ARG002
    ap.add_argument("--url", default="http://localhost:6333")
    ap.add_argument("--collection", default="phishradar_urls")
    ap.add_argument("--size", type=int, default=1024)
    ns = ap.parse_args()
    cli = QdrantClient(url=ns.url)
    if ns.action == "recreate":
        cli.recreate_collection(
            collection_name=ns.collection,
            vectors_config=qm.VectorParams(size=ns.size, distance=qm.Distance.COSINE),
        )
        print("recreated")
    elif ns.action == "drop":
        cli.delete_collection(ns.collection)
        print("dropped")
    else:
        print(cli.get_collection(ns.collection))


if __name__ == "__main__":
    main()

