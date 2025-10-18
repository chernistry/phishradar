#!/usr/bin/env bash
set -euo pipefail

# Check Qdrant collection presence and vector size.
# Usage: QDRANT_URL=http://localhost:6333 QDRANT_COLLECTION=phishradar_urls ./scripts/check_qdrant.sh

QURL=${QDRANT_URL:-http://localhost:6333}
QCOL=${QDRANT_COLLECTION:-phishradar_urls}

echo "GET $QURL/collections/$QCOL" 1>&2
resp=$(curl -fsS "$QURL/collections/$QCOL" || true)
if [ -z "$resp" ]; then
  echo '{"ok":false,"error":"no response from qdrant"}'
  exit 1
fi

status=$(printf '%s' "$resp" | jq -r '.status // "unknown"')
size=$(printf '%s' "$resp" | jq -r '.result.config.params.vectors.size // .result.vectors_count // 0' 2>/dev/null || echo 0)

printf '{"ok":%s,"collection":"%s","status":"%s","vector_size":%s}\n' \
  "$(test "$status" = "ok" && echo true || echo false)" \
  "$QCOL" "$status" "$size"

