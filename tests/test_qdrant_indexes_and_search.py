import types
import pytest

from app.qdrant_client import QdrantStore


class FakePoint:
    def __init__(self, id, score, payload):
        self.id = id
        self.score = score
        self.payload = payload


@pytest.mark.asyncio
async def test_qdrant_ensure_payload_indexes(monkeypatch):
    store = QdrantStore()
    called = {"domain": 0, "ts": 0}

    def fake_create_index(**kwargs):  # type: ignore[no-redef]
        field = kwargs.get("field_name")
        if field == "domain":
            called["domain"] += 1
        elif field == "ts":
            called["ts"] += 1
        return None

    monkeypatch.setattr(store.client, "create_payload_index", fake_create_index)
    await store.ensure_payload_indexes()
    assert called["domain"] == 1 and called["ts"] == 1


@pytest.mark.asyncio
async def test_qdrant_search_wrappers(monkeypatch):
    store = QdrantStore()

    def fake_search(**kwargs):  # type: ignore[no-redef]
        return [FakePoint("id1", 0.9, {"domain": "example.com"})]

    monkeypatch.setattr(store.client, "search", fake_search)
    out = await store.search([0.0, 0.1, 0.2])
    assert out and out[0][0] == "id1" and abs(out[0][1] - 0.9) < 1e-6

    out2 = await store.search_same_domain([0.0, 0.1, 0.2], "example.com")
    assert out2 and out2[0][2]["domain"] == "example.com"


@pytest.mark.asyncio
async def test_qdrant_ensure_collection_no_recreate(monkeypatch):
    store = QdrantStore()
    deleted = {"yes": False, "recreated": False}

    class _Col:
        class _Cfg:
            class _Params:
                class _Vec:
                    size = 256

                vectors = _Vec()

            params = _Params()

        config = _Cfg()

    def fake_get_collection(name):  # type: ignore[no-redef]
        return _Col()

    def fake_delete(name):  # type: ignore[no-redef]
        deleted["yes"] = True
        return None

    def fake_recreate(**kwargs):  # type: ignore[no-redef]
        deleted["recreated"] = True
        return None

    monkeypatch.setattr(store.client, "get_collection", fake_get_collection)
    monkeypatch.setattr(store.client, "delete_collection", fake_delete)
    monkeypatch.setattr(store.client, "recreate_collection", fake_recreate)

    await store.ensure_collection(vector_size=256)
    assert not deleted["yes"] and not deleted["recreated"]

