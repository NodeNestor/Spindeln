"""Spindeln configuration — environment-based with Pydantic settings."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    model_config = {"env_prefix": "SPINDELN_", "env_file": ".env", "extra": "ignore"}

    # Server
    host: str = "0.0.0.0"
    port: int = 8082
    log_level: str = "INFO"

    # HiveMindDB
    hiveminddb_url: str = Field("http://hiveminddb:8100", alias="HIVEMINDDB_URL")

    # vLLM
    vllm_url: str = Field("http://vllm:8000/v1", alias="VLLM_URL")
    vllm_model: str = Field("Qwen/Qwen3-8B-AWQ", alias="VLLM_MODEL")
    vllm_api_key: str = Field("", alias="VLLM_API_KEY")

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


settings = Settings()
