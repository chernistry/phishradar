# PhishRadar Ops Runbook (initial)

- Replay DLQ: `make dlq:replay` (to be implemented)
- Threshold tune: change `DEDUP_THRESHOLD`, observe dup rate.
- Rotate Slack token: update env, restart API service.
- BQ backfill: load from JSONL buffer when streaming insert fails.

