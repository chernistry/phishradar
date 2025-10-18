# PhishRadar Ops Runbook (initial)

- Replay DLQ: `make dlq:replay` (to be implemented)
- Threshold tune: change `DEDUP_THRESHOLD`, observe dup rate.
- Rotate Slack token: update env, restart API service.
- BQ backfill: load from JSONL buffer when streaming insert fails.

## Observability
- Metrics endpoint: `GET /metrics` exposes Prometheus counters/histograms.
  - `phishradar_requests_total{path,method,status}`
  - `phishradar_latency_seconds{path}`
  - `phishradar_readiness`
  - `phishradar_dedup_requests_total`, `phishradar_dedup_duplicates_total`
  - `phishradar_slack_messages_sent_total`, `phishradar_slack_webhooks_total`, `phishradar_slack_webhooks_invalid_total`
- Health: `GET /healthz` returns `{status, env}`.

## Testing & CI
- Local tests: `make test` or `pytest -q` (embeddings integration test disabled by default; enable with `PHISHRADAR_EMBED_TESTS=1`).
- CI: GitHub Actions workflow `.github/workflows/ci.yml` runs ruff, black, mypy, and pytest.

## Qdrant
- Ensure collection size equals `EMBED_DIM` (set at startup). Drop/recreate in dev with `scripts/qdrant_admin.py`.
- Payload indexes: `domain` (keyword), `ts` (integer).

## Slack Webhooks
- Signature verification enforced: HMAC v0 with timestamp freshness (±5m).
- Webhook failures (401) counted via `phishradar_slack_webhooks_invalid_total`.

