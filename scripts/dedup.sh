#!/usr/bin/env bash
set -euo pipefail

# Compute embedding then call /dedup with that vector.
# Usage: API=http://localhost:8000 ./scripts/dedup.sh URL [TITLE] [DOMAIN]

API=${API:-http://localhost:8000}
URL=${1:-https://example.com/a}
TITLE=${2:-Example}
DOMAIN=${3:-example.com}

# 1) Embed
EMBED_JSON=$(API="$API" "$PWD/scripts/embed.sh" "$URL" "$TITLE" "$DOMAIN" || true)
if [ -z "$EMBED_JSON" ]; then
  echo '{"ok":false,"error":"embed failed"}'
  exit 1
fi

DIM=$(printf '%s' "$EMBED_JSON" | jq '.vector|length // 0')
if [ "$DIM" -eq 0 ]; then
  echo '{"ok":false,"error":"empty embedding vector","hint":"Run scripts/check_ollama.sh to debug model"}'
  exit 1
fi

VEC=$(printf '%s' "$EMBED_JSON" | jq -c '.vector')
PAYLOAD=$(printf '{"url":"%s","vector":%s,"payload":{"domain":"%s","title":"%s","ts":%s}}' \
  "$URL" "$VEC" "$DOMAIN" "$TITLE" "$(date +%s)")

curl -fsS -X POST "$API/dedup" -H 'content-type: application/json' -d "$PAYLOAD"

