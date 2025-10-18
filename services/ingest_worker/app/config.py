from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    env: str = os.getenv("ENV", "dev")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Embeddings
    embed_provider: str = os.getenv("EMBED_PROVIDER", "ollama")
    embed_model_name: str = os.getenv("EMBED_MODEL_NAME", "embeddinggemma:latest")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    remote_embed_api_key: str | None = os.getenv("REMOTE_EMBED_API_KEY")

    # Qdrant
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "phishradar_urls")

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Slack
    slack_bot_token: str = os.getenv("SLACK_BOT_TOKEN", "")
    slack_signing_secret: str = os.getenv("SLACK_SIGNING_SECRET", "")
    slack_channel_id: str = os.getenv("SLACK_CHANNEL_ID", "")
    slack_approvers_group_id: str | None = os.getenv("SLACK_APPROVERS_GROUP_ID")

    # BigQuery
    gcp_project_id: str = os.getenv("GCP_PROJECT_ID", "")
    bq_dataset: str = os.getenv("BQ_DATASET", "pradar")
    google_app_credentials: str | None = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    # Dedup/limits
    dedup_threshold: float = float(os.getenv("DEDUP_THRESHOLD", "0.12"))
    rate_limit_feeds_per_host: int = int(os.getenv("RATE_LIMIT_FEEDS_PER_HOST", "2"))
    rate_limit_slack_rps: int = int(os.getenv("RATE_LIMIT_SLACK_RPS", "1"))

    # Observability
    otel_exporter_otlp_endpoint: str | None = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    prometheus_port: int = int(os.getenv("PROMETHEUS_PORT", "9000"))


settings = Settings()
