#!/usr/bin/env bash
set -euo pipefail

# Send a signed mock Slack interactive payload to /hooks/slack.
# Requires env SLACK_SIGNING_SECRET. Useful to validate signature path.
# Usage: API=http://localhost:8000 ./scripts/mock_slack_interaction.sh [approve|reject] [URL]

API=${API:-http://localhost:8000}
SECRET=${SLACK_SIGNING_SECRET:-}
if [ -z "$SECRET" ]; then
  echo "Set SLACK_SIGNING_SECRET in env" 1>&2
  exit 1
fi

ACTION=${1:-approve}
URLVAL=${2:-https://example.com/x1}

# Build the interactive payload JSON
VAL_JSON=$(printf '{"action":"%s","url":"%s"}' "$ACTION" "$URLVAL")
PAYLOAD_JSON=$(printf '{"type":"block_actions","user":{"id":"UDEV","username":"dev"},"response_url":"https://httpbin.org/post","actions":[{"action_id":"phishradar_%s","value":%s}]}' "$ACTION" "$(printf '%s' "$VAL_JSON" | jq -Rs .)")

# URL-encode the payload for form delivery
ENC=$(printf '%s' "$PAYLOAD_JSON" | jq -s -R -r @uri)
BODY="payload=$ENC"

TS=$(date +%s)
BASE=$(printf 'v0:%s:%s' "$TS" "$BODY")
SIG_HEX=$(printf '%s' "$BASE" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $NF}')

curl -sS -X POST "$API/hooks/slack" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H "X-Slack-Request-Timestamp: $TS" \
  -H "X-Slack-Signature: v0=$SIG_HEX" \
  --data "$BODY" | jq .

