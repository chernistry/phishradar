# PhishRadar — Infra Bootstrap

This repo spins up n8n + FastAPI worker + Qdrant + Redis (and optionally Ollama) for phishing feed ingestion, embedding deduplication, Slack HITL alerts, and BigQuery KPIs. See dev/prep/project.md for detailed architecture and acceptance.

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

## Health
- curl :8000/healthz
- curl :8000/metrics
- curl :6333/metrics (qdrant)

## n8n Flow
- Import `n8n/flows/phishradar.json` in the n8n UI (http://localhost:5678 → Import from file) and activate. The flow calls the API endpoints in sequence.

## BigQuery
- Create dataset/tables: `make bq_init` (or manually: `bq --location=US mk -d pradar || true && bq query --use_legacy_sql=false < bq/sql/ddl.sql`)
- Buffer events via `/log` (written to `buffer/events.jsonl`).
- Load to BQ: `make bq_load` (or `python scripts/bq_load.py`) — requires `bq` CLI and auth; set `GCP_PROJECT_ID` and optionally `BQ_DATASET`.
- KPI queries: `bq query --use_legacy_sql=false < bq/sql/kpis.sql`

## Common commands
- make build — rebuild containers
- make logs — tail logs
- make api — enter API container shell

## Troubleshooting
1) Qdrant version mismatch
   - Align client and server versions; see repo notes for upgrades.
2) Ollama cold start
   - Pre-pull model: `ollama pull embeddinggemma:latest`. First request warms the model.
3) Port conflicts
   - Adjust ports in infra/docker-compose.yml; ensure OS firewall allows local ports.
