#!/usr/bin/env bash
set -euo pipefail

# Send a test Slack notification via /notify/slack.
# Usage: API=http://localhost:8000 ./scripts/notify_slack.sh URL [TITLE] [SIMILARITY] [EVIDENCE]

API=${API:-http://localhost:8000}
URL=${1:-https://example.com/x1}
TITLE=${2:-Example 1}
SIM=${3:-0.95}
EVIDENCE=${4:-}

payload=$(printf '{"url":"%s","title":"%s","similarity":%s,"evidence":"%s"}' \
  "$URL" "$TITLE" "$SIM" "$EVIDENCE")

curl -fsS -X POST "$API/notify/slack" -H 'content-type: application/json' -d "$payload"

