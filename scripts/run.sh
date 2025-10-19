#!/usr/bin/env bash
set -euo pipefail

# PhishRadar helper CLI
# Consolidated runner for common dev/ops actions.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# Defaults (override via env)
API=${API:-http://localhost:8000}
QDRANT_URL=${QDRANT_URL:-http://localhost:6333}
QDRANT_COLLECTION=${QDRANT_COLLECTION:-phishradar_urls}
EMBED_MODEL_NAME=${EMBED_MODEL_NAME:-embeddinggemma:latest}
OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:11434}

usage() {
  cat <<'USAGE'
PhishRadar run.sh — common tasks

Usage: ./scripts/run.sh <command> [args]

Dev/infra:
  dev up                 Build + start compose stack
  dev down               Stop stack (with volumes)
  dev logs               Tail compose logs
  dev build              Build images only
  dev ps                 Show running services

Health/checks:
  health                 Check API /healthz
  check ollama [prompt]  Probe Ollama embeddings (default prompt: "hello")
  check qdrant           Show collection status and vector size

Data/API:
  embed URL [TITLE] [DOMAIN]       Get embedding via /embed (domain auto-derived)
  dedup URL [TITLE] [DOMAIN]       Embed → /dedup in one go
  submit URL [TITLE]               Enqueue URL for n8n via /ingest/submit
  fetch [N]                        Pop up to N items via /ingest/fetch (default 10)
  process [N]                      Drain up to N items: enrich→embed→dedup
  notify-slack URL TITLE SIM [E]   Call /notify/slack with similarity and optional evidence
  mock-slack [approve|reject] URL  Send signed interactive payload to /hooks/slack

Sources (feeds):
  sources sync [--force] [--limit N] [--src openphish|sinkingyachts|both]
                             Trigger one polling cycle (enqueue new URLs)
  sources flush-seen        Flush Redis seen-cache (dev only)

Qdrant maintenance:
  qdrant repair           Create/resize collection to current embed dim
  qdrant wipe             Drop + recreate collection (danger; dev only)

Seed and smoke:
  seed [--limit N]        Seed baseline URLs (uses scripts/seed_baseline.py)
  smoke                   Quick embed → dedup + checks

Env defaults (override via env): API, QDRANT_URL, QDRANT_COLLECTION, OLLAMA_BASE_URL, EMBED_MODEL_NAME
USAGE
}

err() { echo "[ERR] $*" >&2; }
info() { echo "[INFO] $*" >&2; }

derive_domain() {
  # Print canonical domain (hostname lowercased, strip leading www.) from URL
  printf '%s' "$1" | awk -F/ '{print $3}' | tr '[:upper:]' '[:lower:]' | sed -E 's/^www\.//'
}

json_escape() {
  # Escape string as JSON using jq
  jq -Rn --arg v "$1" '$v'
}

cmd_dev() {
  local files=(-f infra/docker-compose.yml)
  # Include override if present for bind mounts and extra envs
  if [ -f infra/docker-compose.override.yml ]; then
    files+=(-f infra/docker-compose.override.yml)
  fi
  case "${1:-}" in
    up) docker compose "${files[@]}" up -d --build ;;
    down) docker compose "${files[@]}" down -v ;;
    logs) docker compose "${files[@]}" logs -f --tail=200 ;;
    build) docker compose "${files[@]}" build ;;
    ps) docker compose "${files[@]}" ps ;;
    *) err "Usage: dev {up|down|logs|build|ps}"; exit 1 ;;
  esac
}

cmd_health() {
  curl -fsS "$API/healthz" | jq .
}

cmd_check_ollama() {
  local prompt="${1:-hello}"
  local payload
  payload=$(jq -n --arg m "$EMBED_MODEL_NAME" --arg p "$prompt" '{model:$m,prompt:$p}')
  info "POST $OLLAMA_BASE_URL/api/embeddings (model=$EMBED_MODEL_NAME)"
  local resp
  resp=$(curl -fsS "$OLLAMA_BASE_URL/api/embeddings" -H 'content-type: application/json' -d "$payload")
  local dim
  dim=$(printf '%s' "$resp" | jq 'if has("embedding") then (.embedding|length) else (.data[0].embedding|length) end')
  jq -n --arg m "$EMBED_MODEL_NAME" --argjson d "$dim" '{ok: ($d>0), model:$m, dim:$d}'
}

cmd_check_qdrant() {
  info "GET $QDRANT_URL/collections/$QDRANT_COLLECTION"
  local resp
  resp=$(curl -fsS "$QDRANT_URL/collections/$QDRANT_COLLECTION" || true)
  if [ -z "$resp" ]; then jq -n '{ok:false,error:"no response"}'; exit 1; fi
  local status size
  status=$(printf '%s' "$resp" | jq -r '.status // "unknown"')
  size=$(printf '%s' "$resp" | jq -r '.result.config.params.vectors.size // .result.vectors_count // 0')
  jq -n --arg s "$status" --arg c "$QDRANT_COLLECTION" --argjson z "$size" '{ok: ($s=="ok"), collection:$c, status:$s, vector_size:$z}'
}

cmd_embed() {
  local url="${1:?URL required}"; shift || true
  local title="${1:-Example}"; shift || true
  local domain="${1:-}"
  if [ -z "$domain" ]; then domain=$(derive_domain "$url"); fi
  local payload
  payload=$(jq -n --arg u "$url" --arg t "$title" --arg d "$domain" '{url:$u,title:$t,domain:$d}')
  curl -fsS -X POST "$API/embed" -H 'content-type: application/json' -d "$payload"
}

cmd_dedup() {
  local url="${1:?URL required}"; shift || true
  local title="${1:-Example}"; shift || true
  local domain="${1:-}"
  if [ -z "$domain" ]; then domain=$(derive_domain "$url"); fi
  local ejson vec payload
  ejson=$(API="$API" "$SCRIPT_DIR/run.sh" embed "$url" "$title" "$domain")
  vec=$(printf '%s' "$ejson" | jq -c '.vector')
  payload=$(jq -n --arg u "$url" --argjson v "$vec" --arg d "$domain" --arg t "$title" --arg ts "$(date +%s)" '{url:$u,vector:$v,payload:{domain:$d,title:$t,ts:($ts|tonumber)}}')
  curl -fsS -X POST "$API/dedup" -H 'content-type: application/json' -d "$payload"
}

cmd_notify_slack() {
  local url="${1:?URL required}"; shift
  local title="${1:?TITLE required}"; shift
  local sim="${1:?SIM required}"; shift || true
  local evidence="${1:-}"
  local payload
  payload=$(jq -n --arg u "$url" --arg t "$title" --argjson s "$sim" --arg e "$evidence" '{url:$u,title:$t,similarity:$s,evidence:($e|select(length>0))}')
  curl -fsS -X POST "$API/notify/slack" -H 'content-type: application/json' -d "$payload"
}

cmd_qdrant_repair() {
  # Probe embed dim then create/resize collection
  local ejson dim
  ejson=$("$SCRIPT_DIR/run.sh" embed https://example.com/dim probe example.com)
  dim=$(printf '%s' "$ejson" | jq '.vector|length')
  if [ "$dim" -eq 0 ]; then err "embed dim=0; check Ollama"; exit 1; fi
  info "PUT $QDRANT_URL/collections/$QDRANT_COLLECTION (size=$dim)"
  jq -n --argjson z "$dim" '{vectors:{size:$z,distance:"Cosine"}}' \
    | curl -fsS -X PUT "$QDRANT_URL/collections/$QDRANT_COLLECTION" -H 'content-type: application/json' -d @- | jq .
}

cmd_qdrant_wipe() {
  local ejson dim
  ejson=$("$SCRIPT_DIR/run.sh" embed https://example.com/dim probe example.com)
  dim=$(printf '%s' "$ejson" | jq '.vector|length')
  if [ "$dim" -eq 0 ]; then err "embed dim=0; check Ollama"; exit 1; fi
  info "DELETE $QDRANT_URL/collections/$QDRANT_COLLECTION"
  curl -fsS -X DELETE "$QDRANT_URL/collections/$QDRANT_COLLECTION" || true
  info "PUT $QDRANT_URL/collections/$QDRANT_COLLECTION (size=$dim)"
  jq -n --argjson z "$dim" '{vectors:{size:$z,distance:"Cosine"}}' \
    | curl -fsS -X PUT "$QDRANT_URL/collections/$QDRANT_COLLECTION" -H 'content-type: application/json' -d @- | jq .
}

cmd_seed() {
  local limit="" args=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --limit) limit="$2"; shift 2;;
      *) args+=("$1"); shift;;
    esac
  done
  local py="python"
  if command -v python3 >/dev/null 2>&1; then py=python3; fi
  local cmd=("$py" scripts/seed_baseline.py --api "$API")
  if [ -n "$limit" ]; then cmd+=(--limit "$limit"); fi
  "${cmd[@]}"
}

cmd_submit() {
  local url="${1:?URL required}"; shift || true
  local title="${1:-}"
  local payload
  if [ -n "$title" ]; then
    payload=$(jq -n --arg u "$url" --arg t "$title" '{url:$u,title:$t}')
  else
    payload=$(jq -n --arg u "$url" '{url:$u}')
  fi
  curl -fsS -X POST "$API/ingest/submit" -H 'content-type: application/json' -d "$payload"
}

cmd_fetch() {
  local n="${1:-10}"
  curl -fsS -X POST "$API/ingest/fetch?limit=$n" | jq .
}

cmd_process() {
  local target="${1:-50}"
  local processed=0
  while [ "$processed" -lt "$target" ]; do
    local batch
    batch=$(curl -fsS -X POST "$API/ingest/fetch?limit=10")
    local count
    count=$(printf '%s' "$batch" | jq 'length')
    if [ "$count" -eq 0 ]; then
      info "Queue empty after processing $processed items"
      break
    fi
    for i in $(seq 0 $((count-1))); do
      local url title domain
      url=$(printf '%s' "$batch" | jq -r ".[$i].url")
      domain=$(printf '%s' "$batch" | jq -r ".[$i].domain")
      title="$domain"
      info "Processing: $url"
      # Embed
      local ejson vec
      ejson=$(jq -n --arg u "$url" --arg t "$title" --arg d "$domain" '{url:$u,title:$t,domain:$d}')
      vec=$(curl -fsS -X POST "$API/embed" -H 'content-type: application/json' -d "$ejson" | jq -c '.vector')
      # Dedup
      local djson
      djson=$(jq -n --arg u "$url" --argjson v "$vec" --arg d "$domain" --arg t "$title" --arg ts "$(date +%s)" '{url:$u,vector:$v,payload:{domain:$d,title:$t,ts:($ts|tonumber)}}')
      curl -fsS -X POST "$API/dedup" -H 'content-type: application/json' -d "$djson" | jq '{is_duplicate,similarity}'
      processed=$((processed+1))
      if [ "$processed" -ge "$target" ]; then break; fi
    done
  done
  info "Processed $processed items"
}

cmd_mock_slack() {
  local action="${1:-approve}"
  local url="${2:?URL required}"
  local secret="${SLACK_SIGNING_SECRET:-}"
  if [ -z "$secret" ]; then err "Set SLACK_SIGNING_SECRET env"; exit 1; fi
  local val_json payload_json enc body ts base sig
  val_json=$(jq -n --arg a "$action" --arg u "$url" '{action:$a,url:$u}')
  payload_json=$(jq -n --argjson v "$val_json" --arg a "$action" '{type:"block_actions",user:{id:"UDEV",username:"dev"},response_url:"https://httpbin.org/post",actions:[{action_id:("phishradar_"+$a),value:$v|tojson}]}' )
  enc=$(printf '%s' "$payload_json" | jq -s -R -r @uri)
  body="payload=$enc"
  ts=$(date +%s)
  base="v0:$ts:$body"
  sig=$(printf '%s' "$base" | openssl dgst -sha256 -hmac "$secret" | awk '{print $NF}')
  curl -fsS -X POST "$API/hooks/slack" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -H "X-Slack-Request-Timestamp: $ts" \
    -H "X-Slack-Signature: v0=$sig" \
    --data "$body" | jq .
}

cmd_smoke() {
  echo "== Health ==" >&2; "$SCRIPT_DIR/run.sh" health || true
  echo "== Ollama ==" >&2; "$SCRIPT_DIR/run.sh" check ollama || true
  echo "== Qdrant ==" >&2; "$SCRIPT_DIR/run.sh" check qdrant || true
  echo "== Embed ==" >&2; "$SCRIPT_DIR/run.sh" embed https://example.com Example | jq '{dim:(.vector|length),ms,model}'
  echo "== Dedup roundtrip ==" >&2; "$SCRIPT_DIR/run.sh" dedup https://example.com/a Example | jq . && "$SCRIPT_DIR/run.sh" dedup https://example.com/a Example | jq .
}

case "${1:-}" in
  dev) shift; cmd_dev "$@" ;;
  health) shift; cmd_health "$@" ;;
  check)
    shift; case "${1:-}" in
      ollama) shift; cmd_check_ollama "$@" ;;
      qdrant) shift; cmd_check_qdrant "$@" ;;
      *) err "Usage: check {ollama|qdrant}"; exit 1;;
    esac ;;
  embed) shift; cmd_embed "$@" ;;
  dedup) shift; cmd_dedup "$@" ;;
  notify-slack) shift; cmd_notify_slack "$@" ;;
  qdrant)
    shift; case "${1:-}" in
      repair) shift; cmd_qdrant_repair "$@" ;;
      wipe) shift; cmd_qdrant_wipe "$@" ;;
      *) err "Usage: qdrant {repair|wipe}"; exit 1;;
    esac ;;
  sources)
    shift; case "${1:-}" in
      sync)
        shift
        force="0"; limit=""; src=""
        while [[ $# -gt 0 ]]; do
          case "$1" in
            --force) force="1"; shift ;;
            --limit) limit="$2"; shift 2 ;;
            --src) src="$2"; shift 2 ;;
            *) err "Unknown option: $1"; exit 1 ;;
          esac
        done
        qs=("force=$force")
        if [ -n "$limit" ]; then qs+=("limit=$limit"); fi
        if [ -n "$src" ]; then qs+=("src=$src"); fi
        url="$API/sources/sync?$(IFS='&'; echo "${qs[*]}")"
        curl -fsS -X POST "$url" | jq . ;;
      *) err "Usage: sources sync [--force] [--limit N] [--src openphish|sinkingyachts|both]"; exit 1;;
    esac ;;
  sources)
    shift; case "${1:-}" in
      flush-seen)
        shift
        info "Flushing Redis seen-cache keys (phishradar:seen:url:*)"
        # Best-effort: within redis container
        docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml exec -T redis sh -lc "redis-cli --no-auth-warning -u \"${REDIS_URL:-redis://localhost:6379/0}\" keys 'phishradar:seen:url:*' | xargs -r redis-cli --no-auth-warning -u \"${REDIS_URL:-redis://localhost:6379/0}\" del | wc -l" ;;
      *) err "Usage: sources {sync|flush-seen}"; exit 1;;
    esac ;;
  seed) shift; cmd_seed "$@" ;;
  submit) shift; cmd_submit "$@" ;;
  fetch) shift; cmd_fetch "$@" ;;
  process) shift; cmd_process "$@" ;;
  mock-slack) shift; cmd_mock_slack "$@" ;;
  smoke) shift; cmd_smoke "$@" ;;
  ""|help|-h|--help) usage ;;
  *) err "Unknown command: $1"; usage; exit 1 ;;
esac
