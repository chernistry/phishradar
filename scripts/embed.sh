#!/usr/bin/env bash
set -euo pipefail

# Call /embed with safe one-line JSON (avoids newline breakage)
# Usage: API=http://localhost:8000 ./scripts/embed.sh URL [TITLE] [DOMAIN]

API=${API:-http://localhost:8000}
URL=${1:-https://example.com/a}
TITLE=${2:-Example}
DOMAIN=${3:-example.com}

payload=$(printf '{"url":"%s","title":"%s","domain":"%s"}' "$URL" "$TITLE" "$DOMAIN")
curl -fsS -X POST "$API/embed" -H 'content-type: application/json' -d "$payload"

