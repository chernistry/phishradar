import importlib
import pytest


@pytest.mark.asyncio
async def test_ingest_queue_push_and_fetch(tmp_path, monkeypatch):
    monkeypatch.setenv("BUFFER_DIR", str(tmp_path))
    # Reload modules to pick up new BUFFER_DIR
    paths_mod = importlib.import_module("services.ingest_worker.app.paths")
    importlib.reload(paths_mod)
    iq_mod = importlib.import_module("services.ingest_worker.app.ingest_queue")
    importlib.reload(iq_mod)
    IngestQueue = iq_mod.IngestQueue
    q = IngestQueue()
    row1 = {"url": "https://a/1", "domain": "a", "ts": "0"}
    row2 = {"url": "https://a/2", "domain": "a", "ts": "1"}
    await q.push(row1)
    await q.push(row2)

    got = await q.fetch(limit=1)
    assert got == [row1]

    got2 = await q.fetch(limit=10)
    assert got2 == [row2]
