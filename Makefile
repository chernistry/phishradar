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
	QURL=$${QDRANT_URL:-http://localhost:6333}; QCOL=$${QDRANT_COLLECTION:-phishradar_urls}; \
	curl -sS -X PUT "$$QURL/collections/$$QCOL" \
	  -H 'content-type: application/json' \
	  -d '{"vectors":{"size":1024,"distance":"Cosine"}}' || true

.PHONY: test
test:
	pytest -q

.PHONY: seed_baseline
seed_baseline:
	python scripts/seed_baseline.py --limit 200 --api http://localhost:8000

.PHONY: bq_init bq_load

bq_init:
	@echo "Creating dataset and tables (requires gcloud/bq auth)..." && \
	bq --location=US mk -d $${BQ_DATASET:-pradar} || true && \
	bq query --use_legacy_sql=false < bq/sql/ddl.sql

bq_load:
	python scripts/bq_load.py buffer/events.jsonl
