# PhishRadar — Infra Bootstrap

This repo spins up n8n + FastAPI worker + Qdrant + Redis (and optionally Ollama) for phishing feed ingestion, embedding deduplication, Slack HITL alerts, and BigQuery KPIs.


   
## Digest
- What it is: A "radar" for phishing links. Converts URL/title/domain into vectors and searches for similar vectors in Qdrant (cosine similarity). New items go to Slack, duplicates go to logs.
- For whom: SecOps/SOC/IT security. Working interface - cards in Slack with Approve/Reject buttons.
- Source of links: Public feeds (via seeder), internal sources (via n8n), manual submissions (/ingest/submit).
- Flow process: fetch → enrich → embed (Ollama) → dedup (Qdrant) → notify/log → Slack interaction.
- Why this approach: Embeddings are resilient to URL variations; less noise, faster detection of "new campaigns".
- What to check: `/healthz`, `/metrics`, buffer `buffer/*.jsonl`, diagram `docs/FLOW.md`.


Quick start
1. cp .env.example .env
2. Ensure Ollama is installed with `embeddinggemma:latest` (or uncomment container in compose)
3. make up
4. make smoke

Notes
- Embeddings use Ollama at `OLLAMA_BASE_URL`; Qdrant collection vector size will be finalized by the worker after probing `EMBED_DIM`.
- Patterns borrowed from meulex (docker/qdrant/monitoring) and sense (embed provider resilience design).

## Services
- api: FastAPI worker on :8000
- qdrant: Vector DB on :6333
- redis: DLQ/keys on :6379
- n8n: Flow orchestrator on :5678
- ollama: Optional; host default :11434

### Feeds
- Sources: OpenPhish (public GitHub feed) and SinkingYachts community API (best-effort).
- Polling: manual, via `POST /sources/sync` (use `./scripts/run.sh sources sync`).
- Caching: Redis-backed URL seen-cache with TTL (`FEED_SEEN_TTL_SECONDS`, default 14 days) to avoid re-enqueueing the same URL.
- Queue: New URLs are appended to the file-backed queue (`buffer/incoming.jsonl`) and consumed by n8n via `/ingest/fetch`.
  - Tip: process without n8n via `./scripts/run.sh process 100` (enrich→embed→dedup).

## Health
- curl :8000/healthz
- curl :8000/metrics
- curl :6333/metrics (qdrant)

## n8n Flow
- Import `n8n/flows/phishradar.json` in the n8n UI (http://localhost:5678 → Import from file) and activate. The flow calls the API endpoints in sequence.
- For a deeper technical flow diagram, see `docs/FLOW.md` (in this repo).

## BigQuery
- Create dataset/tables: `make bq_init` (or manually: `bq --location=US mk -d pradar || true && bq query --use_legacy_sql=false < bq/sql/ddl.sql`)
- Buffer events via `/log` (written to `buffer/events.jsonl`).
- Load to BQ: `make bq_load` (or `python scripts/bq_load.py`) — requires `bq` CLI and auth; set `GCP_PROJECT_ID` and optionally `BQ_DATASET`.
- KPI queries: `bq query --use_legacy_sql=false < bq/sql/kpis.sql`

## Common commands
- `./scripts/run.sh dev up` — Build + start compose stack
- `./scripts/run.sh dev logs` — Tail compose logs
- `./scripts/run.sh dev build` — Build images only
- `./scripts/run.sh health` — Check API /healthz
- `./scripts/run.sh check ollama` — Probe Ollama embeddings
- `./scripts/run.sh check qdrant` — Show collection status
- `./scripts/run.sh process [N]` — Process N items: enrich→embed→dedup
- `./scripts/run.sh sources sync` — Trigger feed polling cycle
- `./scripts/run.sh smoke` — Quick embed → dedup + checks
