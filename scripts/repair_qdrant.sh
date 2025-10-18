#!/usr/bin/env bash
set -euo pipefail

# Recreate Qdrant collection with the current embedding dimension (probed via /embed).
# Usage: API=http://localhost:8000 QDRANT_URL=http://localhost:6333 QDRANT_COLLECTION=phishradar_urls ./scripts/repair_qdrant.sh

API=${API:-http://localhost:8000}
QURL=${QDRANT_URL:-http://localhost:6333}
QCOL=${QDRANT_COLLECTION:-phishradar_urls}

# Probe embed dim
EJSON=$(API="$API" "$PWD/scripts/embed.sh" "https://example.com/dim" "probe" "example.com" || true)
DIM=$(printf '%s' "$EJSON" | jq '.vector|length // 0')
if [ "$DIM" -eq 0 ]; then
  echo "Embedding dimension probe failed (dim=0). Check Ollama: ./scripts/check_ollama.sh" 1>&2
  exit 1
fi

echo "Recreating Qdrant collection $QCOL with size=$DIM" 1>&2
payload=$(printf '{"vectors":{"size":%s,"distance":"Cosine"}}' "$DIM")
curl -fsS -X PUT "$QURL/collections/$QCOL" -H 'content-type: application/json' -d "$payload" | jq .

