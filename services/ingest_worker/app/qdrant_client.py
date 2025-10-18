from __future__ import annotations

import hashlib
from typing import Any
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from .config import settings


def id_key(url: str) -> str:
    # Qdrant supports integer or UUID point ids. Use deterministic UUIDv5 from URL.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url))


class QdrantStore:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.qdrant_url)
        self.collection = settings.qdrant_collection

    async def ensure_collection(self, vector_size: int) -> None:
        try:
            col = self.client.get_collection(self.collection)
            # Access size from collection config; fall back to recreate on any issues
            exist_size = int(col.config.params.vectors.size)  # type: ignore[assignment]
            if exist_size != int(vector_size):
                self.client.delete_collection(self.collection)
                self.client.recreate_collection(
                    collection_name=self.collection,
                    vectors_config=qm.VectorParams(
                        size=vector_size, distance=qm.Distance.COSINE
                    ),
                )
        except Exception:
            self.client.recreate_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
            )

    async def ensure_payload_indexes(self) -> None:
        try:
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name="domain",
                field_schema=qm.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass
        try:
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name="ts",
                field_schema=qm.PayloadSchemaType.INTEGER,
            )
        except Exception:
            pass

    async def upsert(self, url: str, vector: list[float], payload: dict[str, Any]) -> str:
        point_id = id_key(url)
        self.client.upsert(
            collection_name=self.collection,
            points=[
                qm.PointStruct(id=point_id, vector=vector, payload={**payload, "url": url}),
            ],
            wait=True,
        )
        return point_id

    async def search(self, vector: list[float], top_k: int = 5) -> list[tuple[str, float]]:
        res = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            limit=top_k,
        )
        out: list[tuple[str, float]] = []
        for p in res:
            pid = str(p.id)
            out.append((pid, float(p.score)))
        return out

    async def search_same_domain(
        self, vector: list[float], domain: str, top_k: int = 5
    ) -> list[tuple[str, float]]:
        res = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            limit=top_k,
            query_filter=qm.Filter(
                must=[qm.FieldCondition(key="domain", match=qm.MatchValue(value=domain))]
            ),
        )
        return [(str(p.id), float(p.score)) for p in res]
