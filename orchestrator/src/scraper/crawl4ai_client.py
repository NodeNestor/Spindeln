"""Crawl4AI async client — wraps the Crawl4AI REST API for JS-rendered scraping."""

from __future__ import annotations

import asyncio
import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=120.0)
    return _client


async def scrape(url: str, *, wait_for: str = "", css_selector: str = "",
                 remove_selectors: list[str] | None = None,
                 screenshot: bool = False) -> dict:
    """Scrape a URL via Crawl4AI and return markdown + metadata.

    Returns:
        {
            "markdown": str,        # Clean markdown of page content
            "html": str,            # Raw HTML (if needed)
            "metadata": dict,       # Title, description, etc.
            "success": bool,
            "error": str | None,
        }
    """
    client = await get_client()

    payload: dict = {
        "urls": [url],
        "priority": 5,
        "word_count_threshold": 10,
        "extraction_config": {
            "type": "basic",
        },
    }

    # Default noise removal — strip nav, footer, cookie banners, ads
    default_remove = [
        "nav", "footer", "header",
        "[class*='cookie']", "[class*='consent']", "[class*='banner']",
        "[class*='ad-']", "[class*='sidebar']", "[id*='cookie']",
    ]

    crawler_params: dict = {
        "headless": True,
        "page_timeout": 30000,
    }
    if wait_for:
        crawler_params["wait_for"] = wait_for
    merged_remove = list(set((remove_selectors or []) + default_remove))
    crawler_params["remove_selectors"] = merged_remove
    payload["crawler_params"] = crawler_params

    if css_selector:
        payload["css_selector"] = css_selector

    if screenshot:
        payload["screenshot"] = True

    try:
        resp = await client.post(
            f"{settings.crawl4ai_url}/crawl",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        # Crawl4AI returns a task_id — poll for result
        task_id = data.get("task_id")
        if task_id:
            return await _poll_task(client, task_id)

        # Some versions return results directly
        result = data.get("result") or data.get("results", [{}])[0]

        # Check HTTP status — skip 4xx/5xx pages
        status_code = result.get("status_code", 200)
        if isinstance(status_code, int) and status_code >= 400:
            return {
                "markdown": "",
                "html": "",
                "metadata": result.get("metadata", {}),
                "success": False,
                "error": f"HTTP {status_code}",
            }

        # markdown may be a dict (newer Crawl4AI) or a string (older)
        raw_md = result.get("markdown", "")
        if isinstance(raw_md, dict):
            raw_md = raw_md.get("raw_markdown", "") or raw_md.get("fit_markdown", "")

        return {
            "markdown": raw_md,
            "html": result.get("html", ""),
            "metadata": result.get("metadata", {}),
            "success": bool(raw_md),
            "error": None,
        }

    except Exception as e:
        logger.error("Crawl4AI scrape failed for %s: %s", url, e)
        return {
            "markdown": "",
            "html": "",
            "metadata": {},
            "success": False,
            "error": str(e),
        }


async def _poll_task(client: httpx.AsyncClient, task_id: str,
                     max_wait: int = 120) -> dict:
    """Poll Crawl4AI task until complete."""
    url = f"{settings.crawl4ai_url}/task/{task_id}"
    for _ in range(max_wait // 2):
        await asyncio.sleep(2)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")
            if status == "completed":
                result = data.get("result", {})
                raw_md = result.get("markdown", "")
                if isinstance(raw_md, dict):
                    raw_md = raw_md.get("raw_markdown", "") or raw_md.get("fit_markdown", "")
                return {
                    "markdown": raw_md,
                    "html": result.get("html", ""),
                    "metadata": result.get("metadata", {}),
                    "success": bool(raw_md),
                    "error": None,
                }
            if status == "failed":
                return {
                    "markdown": "",
                    "html": "",
                    "metadata": {},
                    "success": False,
                    "error": data.get("error", "Task failed"),
                }
        except Exception:
            continue

    return {
        "markdown": "",
        "html": "",
        "metadata": {},
        "success": False,
        "error": "Task polling timed out",
    }


async def close():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
