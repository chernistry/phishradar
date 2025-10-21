import asyncio
import types

import pytest

from phishradar.services.ingest_worker.app.qdrant_client import QdrantStore


@pytest.mark.asyncio
async def test_upsert_retries_then_succeeds(monkeypatch):
    store = QdrantStore()
    calls = {"n": 0}

    def fake_upsert(**kwargs):  # type: ignore[no-redef]
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return None

    monkeypatch.setattr(store.client, "upsert", fake_upsert)
    pid = await store.upsert("https://example.com/a", [0.0, 0.1, 0.2], {"domain": "example.com"})
    assert isinstance(pid, str)
    assert calls["n"] == 2


class _Col:
    class _Cfg:
        class _Params:
            class _Vec:
                size = 123

            vectors = _Vec()

        params = _Params()

    config = _Cfg()


@pytest.mark.asyncio
async def test_ensure_collection_recreate_on_mismatch(monkeypatch):
    store = QdrantStore()
    got = {"deleted": False, "recreated": False}

    def fake_get_collection(name):  # type: ignore[no-redef]
        return _Col()

    def fake_delete(name):  # type: ignore[no-redef]
        got["deleted"] = True
        return None

    def fake_recreate(**kwargs):  # type: ignore[no-redef]
        got["recreated"] = True
        return None

    monkeypatch.setattr(store.client, "get_collection", fake_get_collection)
    monkeypatch.setattr(store.client, "delete_collection", fake_delete)
    monkeypatch.setattr(store.client, "recreate_collection", fake_recreate)

    await store.ensure_collection(vector_size=256)
    assert got["deleted"]
    assert got["recreated"]

