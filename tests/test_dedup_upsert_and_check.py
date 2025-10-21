import pytest

import importlib
from app import dedup as dedup_mod


class FakeStore:
    async def search_same_domain(self, vector, domain, top_k=5):  # noqa: D401
        return []

    async def search(self, vector, top_k=5):
        return []

    async def upsert(self, url, vector, payload):
        return "fake-id"


@pytest.mark.asyncio
async def test_upsert_and_check_no_hits_not_duplicate(monkeypatch):
    # Replace QdrantStore in the original module where the function was defined
    orig = importlib.import_module("services.ingest_worker.app.dedup")
    monkeypatch.setattr(orig, "QdrantStore", lambda: FakeStore())
    dup, sim, qid = await dedup_mod.upsert_and_check(
        url="https://example.com/a",
        vector=[0.0, 0.1, 0.2],
        payload={"title": "Example"},
    )
    assert dup is False
    assert sim == 0.0
    assert qid is None
