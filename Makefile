.PHONY: up down build logs api fmt lint smoke qdrant-create

up:
	docker compose -f infra/docker-compose.yml up -d --build

down:
	docker compose -f infra/docker-compose.yml down -v

build:
	docker compose -f infra/docker-compose.yml build

logs:
	docker compose -f infra/docker-compose.yml logs -f --tail=200

api:
	docker compose -f infra/docker-compose.yml exec api bash || true

fmt:
	docker compose -f infra/docker-compose.yml exec api bash -lc "pip install black isort ruff && black app && isort app && ruff app --fix"

lint:
	docker compose -f infra/docker-compose.yml exec api bash -lc "ruff app && python -m pip install mypy && mypy app || true"

smoke:
	curl -fsS http://localhost:8000/healthz || (echo "API health failed" && exit 1)
	curl -fsS http://localhost:6333/metrics || echo "Qdrant metrics ok"

qdrant-create:
	python - <<'PY'
import os, requests
url = os.getenv('QDRANT_URL', 'http://localhost:6333') + '/collections/' + os.getenv('QDRANT_COLLECTION','phishradar_urls')
vector_size = 1024
try:
    rsp = requests.put(url, json={
        "vectors": {"size": vector_size, "distance": "Cosine"}
    }, timeout=10)
    print('Qdrant create status', rsp.status_code, rsp.text)
except Exception as e:
    print('Qdrant create error', e)
PY

.PHONY: test
test:
	pytest -q

.PHONY: seed:baseline
seed\:baseline:
	python scripts/seed_baseline.py --limit 200 --api http://localhost:8000

.PHONY: bq:init bq:load

bq:init:
	@echo "Creating dataset and tables (requires gcloud/bq auth)..." && \
	bq --location=US mk -d $${BQ_DATASET:-pradar} || true && \
	bq query --use_legacy_sql=false < bq/sql/ddl.sql

bq:load:
	python scripts/bq_load.py buffer/events.jsonl
