"""Spindeln configuration — environment-based with Pydantic settings + runtime overrides."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path("/app/data/config.json")


class Settings(BaseSettings):
    model_config = {"env_prefix": "SPINDELN_", "env_file": ".env", "extra": "ignore"}

    # Server
    host: str = "0.0.0.0"
    port: int = 8082
    log_level: str = "INFO"

    # HiveMindDB
    hiveminddb_url: str = Field("http://hiveminddb:8100", alias="HIVEMINDDB_URL")

    # vLLM (legacy — used as defaults for bulk_* fields)
    vllm_url: str = Field("http://vllm:8000/v1", alias="VLLM_URL")
    vllm_model: str = Field("Qwen/Qwen3-8B-AWQ", alias="VLLM_MODEL")
    vllm_api_key: str = Field("", alias="VLLM_API_KEY")

    # Bulk extraction model (defaults from vllm_* for backward compat)
    bulk_api_url: str = Field("", alias="BULK_API_URL")
    bulk_model: str = Field("", alias="BULK_MODEL")
    bulk_api_key: str = Field("", alias="BULK_API_KEY")
    bulk_max_tokens: int = Field(4096, alias="BULK_MAX_TOKENS")

    # Synthesis / report writer model
    synthesis_api_url: str = Field("", alias="SYNTHESIS_API_URL")
    synthesis_model: str = Field("", alias="SYNTHESIS_MODEL")
    synthesis_api_key: str = Field("", alias="SYNTHESIS_API_KEY")
    synthesis_max_tokens: int = Field(16384, alias="SYNTHESIS_MAX_TOKENS")

    # SearXNG
    searxng_url: str = Field("http://searxng:8080", alias="SEARXNG_URL")

    # Crawl4AI
    crawl4ai_url: str = Field("http://crawl4ai:11235", alias="CRAWL4AI_URL")

    # Loom bridge
    loom_db_path: str = Field("/data/loom/loom.db", alias="LOOM_DB_PATH")

    # Optional API keys
    hibp_api_key: str = Field("", alias="HIBP_API_KEY")
    intelx_api_key: str = Field("", alias="INTELX_API_KEY")
    hudsonrock_api_key: str = Field("", alias="HUDSONROCK_API_KEY")

    # Tor proxy
    tor_proxy: str = Field("socks5://tor-proxy:9050", alias="TOR_PROXY")

    # Rate limiting
    scrape_concurrency: int = Field(5, alias="SCRAPE_CONCURRENCY")
    scrape_delay_seconds: float = Field(2.0, alias="SCRAPE_DELAY_SECONDS")
    searxng_delay_seconds: float = Field(1.0, alias="SEARXNG_DELAY_SECONDS")

    # Discovery loop
    max_discovery_iterations: int = Field(5, alias="MAX_DISCOVERY_ITERATIONS")

    def _apply_bulk_defaults(self):
        """Fill empty bulk_* fields from legacy vllm_* fields."""
        if not self.bulk_api_url:
            self.bulk_api_url = self.vllm_url
        if not self.bulk_model:
            self.bulk_model = self.vllm_model
        if not self.bulk_api_key:
            self.bulk_api_key = self.vllm_api_key
        # Synthesis defaults to same as bulk if not explicitly set
        if not self.synthesis_api_url:
            self.synthesis_api_url = self.bulk_api_url
        if not self.synthesis_model:
            self.synthesis_model = self.bulk_model


# ── Runtime Config Layer ────────────────────────────────────────────────────

_RUNTIME_FIELDS: set[str] = {
    "bulk_api_url", "bulk_model", "bulk_api_key", "bulk_max_tokens",
    "synthesis_api_url", "synthesis_model", "synthesis_api_key", "synthesis_max_tokens",
    "hiveminddb_url", "searxng_url", "crawl4ai_url", "scrape_concurrency",
    "max_discovery_iterations",
}

_KEY_FIELDS: set[str] = {"bulk_api_key", "synthesis_api_key"}


def _load_persisted() -> dict:
    """Load runtime overrides from disk."""
    try:
        if _CONFIG_PATH.exists():
            data = json.loads(_CONFIG_PATH.read_text())
            return {k: v for k, v in data.items() if k in _RUNTIME_FIELDS}
    except Exception as e:
        logger.warning("Failed to load persisted config: %s", e)
    return {}


def _save_persisted(data: dict):
    """Persist runtime overrides to disk."""
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(data, indent=2))
    except Exception as e:
        logger.warning("Failed to save persisted config: %s", e)


def _mask_key(value: str) -> str:
    """Mask an API key for safe display."""
    if not value or len(value) <= 4:
        return "***" if value else ""
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def get_runtime_config() -> dict:
    """Return all editable runtime fields, with API keys masked."""
    result = {}
    for field in sorted(_RUNTIME_FIELDS):
        value = getattr(settings, field)
        if field in _KEY_FIELDS:
            result[field] = _mask_key(str(value))
        else:
            result[field] = value
    return result


def update_runtime_config(updates: dict) -> dict:
    """Partial update of runtime fields. Persists to disk. Returns updated config."""
    # Load existing persisted data to merge with
    persisted = _load_persisted()

    for key, value in updates.items():
        if key not in _RUNTIME_FIELDS:
            continue
        # Skip masked keys (user didn't change them)
        if key in _KEY_FIELDS and "***" in str(value):
            continue
        setattr(settings, key, value)
        persisted[key] = value

    _save_persisted(persisted)
    return get_runtime_config()


# ── Initialization ──────────────────────────────────────────────────────────

settings = Settings()
settings._apply_bulk_defaults()

# Apply any persisted runtime overrides on startup
_persisted = _load_persisted()
for _k, _v in _persisted.items():
    if _k in _RUNTIME_FIELDS:
        setattr(settings, _k, _v)
