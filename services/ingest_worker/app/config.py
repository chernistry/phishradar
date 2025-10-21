from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
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
    qdrant_rps: int = int(os.getenv("QDRANT_RPS", "10"))
    qdrant_timeout: float = float(os.getenv("QDRANT_TIMEOUT", "5"))

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Slack
    slack_bot_token: str = os.getenv("SLACK_BOT_TOKEN", "")
    slack_signing_secret: str = os.getenv("SLACK_SIGNING_SECRET", "")
    slack_channel_id: str = os.getenv("SLACK_CHANNEL_ID", "")
    slack_approvers_group_id: str | None = os.getenv("SLACK_APPROVERS_GROUP_ID")
    slack_app_level_token: str = os.getenv("SLACK_APP_LEVEL_TOKEN", "")

    # BigQuery
    gcp_project_id: str = os.getenv("GCP_PROJECT_ID", "")
    bq_dataset: str = os.getenv("BQ_DATASET", "pradar")
    google_app_credentials: str | None = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    # Dedup/limits
    # Legacy threshold kept for backward-compat (interpreted as margin from 1.0)
    dedup_threshold: float = float(os.getenv("DEDUP_THRESHOLD", "0.12"))
    # New explicit similarity floors (recommended)
    dedup_same_domain_min_sim: float = float(os.getenv("DEDUP_SAME_DOMAIN_MIN_SIM", "0.94"))
    # Global cross-domain floor (default 0.985 per tests)
    dedup_global_min_sim: float = float(os.getenv("DEDUP_GLOBAL_MIN_SIM", "0.985"))
    rate_limit_feeds_per_host: int = int(os.getenv("RATE_LIMIT_FEEDS_PER_HOST", "2"))
    rate_limit_slack_rps: int = int(os.getenv("RATE_LIMIT_SLACK_RPS", "1"))

    # Feeds/polling
    openphish_feed_url: str = os.getenv(
        "OPENPHISH_FEED_URL",
        # New public feed location maintained via GitHub
        "https://raw.githubusercontent.com/openphish/public_feed/refs/heads/main/feed.txt",
    )
    sinkingyachts_feed_url: str = os.getenv(
        "SINKINGYACHTS_FEED_URL", "https://phish.sinking.yachts/v2/urls"
    )
    feed_poll_interval_seconds: int = int(os.getenv("FEED_POLL_INTERVAL_SECONDS", "60"))
    feed_batch_limit: int = int(os.getenv("FEED_BATCH_LIMIT", "200"))
    feed_seen_ttl_seconds: int = int(os.getenv("FEED_SEEN_TTL_SECONDS", str(14 * 24 * 3600)))

    # Observability
    otel_exporter_otlp_endpoint: str | None = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    prometheus_port: int = int(os.getenv("PROMETHEUS_PORT", "9000"))

    # Retry/backoff defaults
    retry_max_attempts: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "5"))
    retry_initial_delay: float = float(os.getenv("RETRY_INITIAL_DELAY", "0.25"))
    retry_max_delay: float = float(os.getenv("RETRY_MAX_DELAY", "5"))
    retry_multiplier: float = float(os.getenv("RETRY_MULTIPLIER", "2.0"))


settings = Settings()
