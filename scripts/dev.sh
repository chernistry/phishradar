#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  up)
    docker compose -f infra/docker-compose.yml up -d --build
    ;;
  down)
    docker compose -f infra/docker-compose.yml down -v
    ;;
  logs)
    docker compose -f infra/docker-compose.yml logs -f --tail=200
    ;;
  *)
    echo "Usage: $0 {up|down|logs}";
    ;;
esac

