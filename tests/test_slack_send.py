import pytest

from app import slack as slack_mod


class DummyResp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "ts": "1", "channel": "C"}


class DummyClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):  # noqa: A002 - shadowing json name acceptable in test
        return DummyResp()


@pytest.mark.asyncio
async def test_send_message_success(monkeypatch):
    # Configure tokens
    slack_mod.settings.slack_bot_token = "xoxb-test"
    slack_mod.settings.slack_channel_id = "C123"
    # Reset circuit breaker in case other tests opened it
    # Patch the original module (re-exported by app.slack)
    import importlib
    orig = importlib.import_module("services.ingest_worker.app.slack")
    # Use a fresh circuit breaker to avoid OPEN state from previous tests
    orig._slack_cb = orig.CircuitBreaker(failure_threshold=100, recovery_time=0.01)  # type: ignore[attr-defined]
    async def _run(fn):
        return await fn()
    # Bypass breaker behavior for this success test
    monkeypatch.setattr(orig._slack_cb, "run", _run)  # type: ignore[attr-defined]
    # Patch HTTP client to dummy
    monkeypatch.setattr(orig, "async_http_client", lambda timeout=10.0: DummyClient())
    data = await slack_mod.send_message("hello", blocks=None)
    assert data["ok"] is True and data["channel"] == "C"


@pytest.mark.asyncio
async def test_send_message_not_configured_raises(monkeypatch):
    # Clear channel/token
    slack_mod.settings.slack_bot_token = ""
    slack_mod.settings.slack_channel_id = ""
    with pytest.raises(slack_mod.SlackError):
        await slack_mod.send_message("x")


@pytest.mark.asyncio
async def test_respond_uses_http(monkeypatch):
    # Just ensure it calls into HTTP client; DummyClient.post returns DummyResp
    monkeypatch.setattr(slack_mod, "async_http_client", lambda timeout=10.0: DummyClient())
    await slack_mod.respond("https://example.com/response", "ok")
