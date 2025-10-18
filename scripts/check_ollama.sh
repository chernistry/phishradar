#!/usr/bin/env bash
set -euo pipefail

# Probe Ollama embeddings endpoint and print vector length.
# Usage: OLLAMA_BASE_URL=... EMBED_MODEL_NAME=... ./scripts/check_ollama.sh [prompt]

BASE_URL=${OLLAMA_BASE_URL:-http://localhost:11434}
MODEL=${EMBED_MODEL_NAME:-embeddinggemma:latest}
PROMPT=${1:-"hello world"}

# Build JSON safely without newlines
payload=$(printf '{"model":"%s","prompt":"%s"}' "$MODEL" "$PROMPT")

echo "POST $BASE_URL/api/embeddings (model=$MODEL)" 1>&2
resp=$(curl -fsS "$BASE_URL/api/embeddings" -H 'content-type: application/json' -d "$payload" || true)
if [ -z "$resp" ]; then
  echo "{\"ok\":false,\"error\":\"no response\"}"
  exit 1
fi

# Try to parse both shapes: {embedding:[...]} or {data:[{embedding:[...]}]}
dim=$(printf '%s' "$resp" | jq 'if has("embedding") then (.embedding|length) else (.data[0].embedding|length) end' 2>/dev/null || echo "0")

printf '{"ok":%s,"model":"%s","dim":%s}\n' \
  "$(test "$dim" != "0" && echo true || echo false)" \
  "$MODEL" \
  "$dim"

