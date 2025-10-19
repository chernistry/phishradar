from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from .config import settings
from .logging_metrics import (
    correlation_id,
    latency_hist,
    metrics_router,
    req_counter,
    setup_logging,
    dedup_requests_total,
    dedup_duplicates_total,
    set_ready,
    set_unready,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    # OTel instrumentation (safe if exporter unset)
    try:
        FastAPIInstrumentor.instrument_app(app)  # type: ignore[name-defined]
        HTTPXClientInstrumentor().instrument()
    except Exception as e:
        logging.getLogger(__name__).warning(f"OTel instrumentation failed: {e}")
    # Probe embeddings dimension (warm-up Ollama)
    try:
        from .embeddings import OllamaEmbeddings

        emb = OllamaEmbeddings()
        dim = await emb.dim()
        logging.getLogger(__name__).info(f"EMBED_DIM={dim} (model={emb.model})")
        app.state.embed_dim = dim  # type: ignore[attr-defined]
        # Ensure Qdrant collection and payload indexes
        try:
            from .qdrant_client import QdrantStore

            store = QdrantStore()
            await store.ensure_collection(dim)
            await store.ensure_payload_indexes()
        except Exception as qe:
            logging.getLogger(__name__).warning(f"Qdrant ensure failed: {qe}")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Embedding probe failed: {e}")
    # Start Slack Socket Mode if configured (no public URL needed)
    try:
        await start_socket_mode()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Socket Mode start failed: {e}")
    # Feed poller is not auto-started; triggered on demand via /sources/sync
    # Mark ready after startup tasks
    set_ready()
    yield
    # On shutdown mark unready
    set_unready()
    try:
        await stop_socket_mode()
    except Exception:
        pass
    # No background feed poller to stop (manual trigger only)


app = FastAPI(title="PhishRadar Ingest Worker", version="0.1.0", lifespan=lifespan)
app.include_router(metrics_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_mw(request: Request, call_next):  # type: ignore[no-untyped-def]
    url = str(request.url)
    cid = hashlib.sha256(url.encode()).hexdigest()[:16]
    token = correlation_id.set(cid)
    try:
        response = await call_next(request)
        response.headers["x-correlation-id"] = cid
        return response
    finally:
        correlation_id.reset(token)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    status = "500"
    try:
        response = await call_next(request)
        status = str(getattr(response, "status_code", 500))
        return response
    finally:
        elapsed = time.perf_counter() - start
        path = request.url.path
        try:
            latency_hist.labels(path=path).observe(elapsed)
            req_counter.labels(path=path, method=request.method, status=status).inc()
        except Exception:
            pass


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception):  # type: ignore[no-untyped-def]
    logging.getLogger(__name__).exception("Unhandled error")
    return JSONResponse({"code": "ERR_UNKNOWN", "message": str(exc)}, status_code=500)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}

# Embeddings endpoint (Ticket 3)
from fastapi import Body, HTTPException, Header, Form  # noqa: E402
from .models import (
    EmbedIn,
    EmbedOut,
    DedupIn,
    DedupOut,
    SlackNotifyIn,
    UrlItem,
    EnrichIn,
    EnrichOut,
)  # noqa: E402
from .embeddings import OllamaEmbeddings  # noqa: E402
from .dedup import upsert_and_check  # noqa: E402
from .slack import (
    send_message,
    verify_signature,
    action_blocks,
    respond,
    start_socket_mode,
    stop_socket_mode,
)  # noqa: E402
from .logging_metrics import slack_messages_sent_total, slack_webhooks_total, slack_webhooks_invalid_total  # noqa: E402
from .domain import canonical_domain  # noqa: E402
from .paths import BUFFER_DIR  # noqa: E402
from .ingest_queue import IngestQueue  # noqa: E402
from .feed_poller import FeedPoller  # noqa: E402


@app.post("/embed", response_model=EmbedOut)
async def embed(request: Request) -> EmbedOut:
    """Return embedding for the given URL/title/domain.

    Primary contract: JSON body matching EmbedIn. For resilience with tools like n8n
    misconfigured to not send JSON, we also accept form fields or query params.
    """
    # Extract fields
    url_val: str | None = None
    title_val: str | None = None
    domain_val: str | None = None
    try:
        data = await request.json()
    except Exception:
        data = None
    if isinstance(data, dict) and data:
        url_val = str(data.get("url") or "") or None
        title_val = data.get("title") or None
        domain_val = data.get("domain") or None
    else:
        # Try form or query
        try:
            form = await request.form()
            url_val = url_val or form.get("url")
            title_val = title_val or form.get("title")
            domain_val = domain_val or form.get("domain")
        except Exception:
            pass
        if not url_val:
            url_val = request.query_params.get("url")
        if not title_val:
            title_val = request.query_params.get("title")
        if not domain_val:
            domain_val = request.query_params.get("domain")
        if not url_val:
            raise HTTPException(status_code=422, detail="url required")
        if not title_val:
            # fallback title = domain
            title_val = canonical_domain(str(url_val))
    dom = canonical_domain(str(url_val))
    emb = OllamaEmbeddings()
    vector, ms, model = await emb.embed_async_single(f"{url_val} | {title_val} | {dom}")
    try:
        _append_jsonl("receipts.jsonl", {"model": model, "tokens": 0, "ms": ms, "cost": 0.0})
    except Exception:
        pass
    return EmbedOut(vector=vector, model=model, ms=ms, url=str(url_val), title=str(title_val or dom), domain=dom)


@app.post("/dedup", response_model=DedupOut)
async def dedup(request: Request) -> DedupOut:
    dedup_requests_total.inc()
    # Accept JSON body (preferred) or form-encoded fields; tolerate stringified vector/payload
    url_val: str | None = None
    vector_val: list[float] | None = None
    payload_val: dict | None = None  # type: ignore[type-arg]

    # Try JSON body first
    try:
        body = await request.json()
    except Exception:
        body = None
    if isinstance(body, dict) and body:
        url_val = str(body.get("url") or "") or None
        vector_val = body.get("vector")
        payload_val = body.get("payload") if isinstance(body.get("payload"), dict) else None
    else:
        # Try to parse JSON or form
        raw_handled = False
        try:
            data = await request.json()
            raw_handled = True
        except Exception:
            data = None
        if isinstance(data, dict) and data:
            url_val = str(data.get("url") or "") or None
            vector_val = data.get("vector")  # may be list or str
            payload_val = data.get("payload") if isinstance(data.get("payload"), dict) else None
            if isinstance(vector_val, str):
                try:
                    import json as _json

                    vector_val = _json.loads(vector_val)
                except Exception:
                    vector_val = None
        if url_val is None or vector_val is None:
            # Try form fields
            try:
                form = await request.form()
                url_val = url_val or form.get("url")
                v = form.get("vector")
                if v and isinstance(v, str):
                    try:
                        import json as _json

                        vector_val = _json.loads(v)
                    except Exception:
                        vector_val = None
                if payload_val is None:
                    p = form.get("payload")
                    if p and isinstance(p, str):
                        try:
                            import json as _json

                            payload_val = _json.loads(p)
                        except Exception:
                            payload_val = None
            except Exception:
                if not raw_handled:
                    # Last resort: read raw and attempt JSON
                    try:
                        raw = await request.body()
                        import json as _json

                        d2 = _json.loads(raw.decode("utf-8"))
                        url_val = url_val or d2.get("url")
                        vector_val = vector_val or d2.get("vector")
                        payload_val = payload_val or d2.get("payload")
                    except Exception:
                        pass

    if not url_val:
        raise HTTPException(status_code=422, detail="url required")
    if not isinstance(vector_val, list) or not vector_val:
        raise HTTPException(status_code=400, detail="empty or invalid vector")

    # Validate dimension if known
    embed_dim = getattr(app.state, "embed_dim", None)  # type: ignore[attr-defined]
    if embed_dim is not None and len(vector_val) != int(embed_dim):
        raise HTTPException(status_code=400, detail="vector dimension mismatch")

    payload_val = payload_val or {}
    dup, sim, qid = await upsert_and_check(str(url_val), vector_val, payload_val)
    if dup:
        dedup_duplicates_total.inc()
    return DedupOut(is_duplicate=dup, similarity=sim, qdrant_id=qid)


@app.post("/ingest/fetch")
async def ingest_fetch(request: Request) -> list[UrlItem]:
    # Pop up to `limit` items from the local file-backed queue. Returns [] if empty.
    try:
        limit_str = request.query_params.get("limit")
        limit = max(1, min(50, int(limit_str))) if limit_str else 10
    except Exception:
        limit = 10
    q = IngestQueue()
    rows = await q.fetch(limit=limit)
    return [UrlItem(url=r["url"], domain=r["domain"], ts=r["ts"]) for r in rows]


@app.post("/sources/sync")
async def sources_sync(request: Request) -> dict[str, int]:
    """Trigger a single poll cycle immediately (no background loop).

    Query params:
      - force=1 to bypass seen-cache (for testing)
      - limit=N to cap enqueued items
      - src=openphish|sinkingyachts|both to select sources (default: both)
    """
    try:
        qp = request.query_params
        force = str(qp.get("force") or "").strip().lower() in ("1", "true", "yes")
        lim_raw = qp.get("limit")
        limit = int(str(lim_raw).strip()) if lim_raw is not None and str(lim_raw).strip().isdigit() else None
        src_raw = str(qp.get("src") or "").strip().lower()
        src = src_raw if src_raw in ("openphish", "sinkingyachts", "both") else None
    except Exception:
        force, limit, src = False, None, None
    try:
        poller = FeedPoller()
        logging.getLogger(__name__).info(f"sources_sync: force={force} limit={limit} src={src}")
        count = await poller._poll_once(force=force, limit=limit, src=src)
    except Exception:
        count = 0
    return {"enqueued": int(count)}


@app.post("/ingest/submit")
async def ingest_submit(body: dict = Body(...)) -> dict[str, bool]:  # type: ignore[type-arg]
    # Accepts: {url, title?}. Derives domain and ts, enqueues for n8n to process via /ingest/fetch
    from datetime import datetime, timezone

    url = str(body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=422, detail="url required")
    dom = canonical_domain(url)
    row = {
        "url": url,
        "domain": dom,
        "title": body.get("title") or dom,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    q = IngestQueue()
    await q.push(row)
    return {"ok": True}


@app.post("/enrich", response_model=EnrichOut)
async def enrich(request: Request, body: EnrichIn | None = Body(None)) -> EnrichOut:
    """Enrich URL with minimal metadata.

    Accepts JSON body {"url": ...}. If body is missing (e.g., n8n misconfigured),
    falls back to parsing form-encoded or query param `url`.
    """
    from urllib.parse import urlparse

    url_val: str | None = None
    if body and getattr(body, "url", None):
        url_val = str(body.url)
    else:
        # Try form
        try:
            form = await request.form()
            url_val = form.get("url") or url_val
        except Exception:
            pass
        # Try query string
        if not url_val:
            url_val = request.query_params.get("url")
        if not url_val:
            raise HTTPException(status_code=422, detail="url required")

    parsed = urlparse(str(url_val))
    title = parsed.netloc or ""
    return EnrichOut(url=str(url_val), title=title, snapshot_hash=None)


@app.post("/log")
async def log_event(request: Request, payload: Any = Body(None)) -> dict[str, bool]:  # type: ignore[type-arg]
    """Best-effort logging endpoint.

    Accepts JSON body (preferred). If missing, tolerates form-encoded (payload=JSON)
    or raw query params; appends `ts` if absent and writes a JSONL line.
    """
    from datetime import datetime, timezone

    data: dict[str, Any] | None = None
    if isinstance(payload, dict):
        data = payload
    else:
        # Try JSON
        try:
            j = await request.json()
            if isinstance(j, dict):
                data = j
        except Exception:
            pass
        # Try form (payload field containing JSON)
        if data is None:
            try:
                form = await request.form()
                p = form.get("payload")
                if isinstance(p, str):
                    import json as _json

                    data = _json.loads(p)
            except Exception:
                pass
        # Fallback to query
        if data is None:
            data = dict(request.query_params)

    if "ts" not in data:
        data["ts"] = datetime.now(timezone.utc).isoformat()
    try:
        _append_jsonl("events.jsonl", data)
    except Exception:
        # best-effort; surface ok anyway to not break flow
        pass
    return {"ok": True}


import os as _os
import json as _json

_os.makedirs(BUFFER_DIR, exist_ok=True)


def _append_jsonl(filename: str, obj: dict) -> None:  # type: ignore[type-arg]
    path = _os.path.join(BUFFER_DIR, filename)
    with open(path, "a", encoding="utf-8") as f:
        f.write(_json.dumps(obj, ensure_ascii=False) + "\n")


def main() -> None:
    host = os.getenv("HOST", settings.api_host)
    port = int(os.getenv("PORT", str(settings.api_port)))
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
        factory=False,
    )


if __name__ == "__main__":
    main()
@app.post("/notify/slack")
async def notify_slack(body: SlackNotifyIn):
    blocks = action_blocks(str(body.url), body.title, body.similarity)
    data = await send_message(text=f"New phishing alert: {body.title}", blocks=blocks)
    slack_messages_sent_total.inc()
    return {"ok": True, "ts": data.get("ts"), "channel": data.get("channel")}


@app.post("/hooks/slack")
async def hooks_slack(
    request: Request,
    x_slack_signature: str = Header(""),
    x_slack_request_timestamp: str = Header(""),
):
    slack_webhooks_total.inc()
    # Verify signature using the exact raw body bytes as Slack sent (form-encoded)
    raw_body = await request.body()
    if not verify_signature(x_slack_request_timestamp, x_slack_signature, raw_body):
        slack_webhooks_invalid_total.inc()
        raise HTTPException(status_code=401, detail="invalid signature")
    # Parse interactive payload from x-www-form-urlencoded: payload=<json>
    try:
        from urllib.parse import parse_qs

        form = parse_qs(raw_body.decode("utf-8"), strict_parsing=False)
        payload_list = form.get("payload", [])
        if not payload_list:
            raise ValueError("missing payload")
        event = json.loads(payload_list[0])
    except Exception:
        raise HTTPException(status_code=400, detail="invalid payload")
    # Quick ack via response_url if provided
    resp_url = event.get("response_url")
    if resp_url:
        try:
            await respond(resp_url, "Thanks. Action received.")
        except Exception:
            pass
    action = (event.get("actions") or [{}])[0]
    action_val = action.get("value")
    try:
        parsed = json.loads(action_val) if action_val else {}
    except Exception:
        parsed = {"action": "unknown"}
    user = (event.get("user") or {}).get("username") or (event.get("user") or {}).get("id")
    # TODO(T7): persist to BQ
    return {"ok": True, "user": user, "action": parsed}
