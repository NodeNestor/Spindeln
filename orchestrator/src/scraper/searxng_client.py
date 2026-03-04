"""SearXNG async client — metasearch engine for web/news/social discovery."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


@dataclass
class SearXResult:
    url: str
    title: str
    snippet: str
    engine: str = ""
    published_date: str = ""
    category: str = ""


def parse_date(date_str: str) -> date | None:
    """Parse a date string from SearXNG results into a date object.

    Handles:
      - ISO 8601 datetime: "2024-03-15T10:30:00+00:00", "2024-03-15T10:30:00Z"
      - ISO date only:     "2024-03-15"
      - Relative strings:  "3 days ago", "5 hours ago", "1 week ago"
    """
    if not date_str:
        return None
    date_str = date_str.strip()

    # 1) Try ISO 8601 datetime (with optional timezone)
    try:
        normalised = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalised)
        return dt.date()
    except (ValueError, IndexError):
        pass

    # 2) Try plain date "2024-03-15"
    try:
        return date.fromisoformat(date_str[:10])
    except (ValueError, IndexError):
        pass

    # 3) Relative time strings: "X <unit> ago"
    m = re.match(
        r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago",
        date_str,
        re.IGNORECASE,
    )
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        now = datetime.now(timezone.utc)
        deltas = {
            "second": timedelta(seconds=amount),
            "minute": timedelta(minutes=amount),
            "hour":   timedelta(hours=amount),
            "day":    timedelta(days=amount),
            "week":   timedelta(weeks=amount),
            "month":  timedelta(days=amount * 30),
            "year":   timedelta(days=amount * 365),
        }
        delta = deltas.get(unit)
        if delta:
            return (now - delta).date()

    logger.debug("Could not parse SearXNG date: '%s'", date_str)
    return None


async def search(query: str, *, categories: str = "general",
                 engines: str = "", language: str = "sv-SE",
                 time_range: str = "", max_results: int = 20) -> list[SearXResult]:
    """Search via SearXNG. Returns parsed results.

    Args:
        query: Search query string
        categories: general, news, images, social media, etc.
        engines: Comma-separated engine list (empty = use defaults)
        language: Language code
        time_range: day, week, month, year, or empty
        max_results: Maximum results to return
    """
    client = await get_client()
    params: dict = {
        "q": query,
        "format": "json",
        "categories": categories,
        "language": language,
        "safesearch": 0,
        "pageno": 1,
    }
    if engines:
        params["engines"] = engines
    if time_range:
        params["time_range"] = time_range

    all_results: list[SearXResult] = []

    try:
        # Fetch up to 2 pages
        for page in range(1, 3):
            params["pageno"] = page
            resp = await client.get(f"{settings.searxng_url}/search", params=params)
            resp.raise_for_status()
            data = resp.json()

            for r in data.get("results", []):
                # SearXNG returns dates under 'publishedDate' (most common)
                # but some engines use 'pubdate' or 'date'. Try all variants.
                raw_date = (
                    r.get("publishedDate")
                    or r.get("pubdate")
                    or r.get("date")
                    or ""
                )
                if raw_date:
                    logger.debug("SearXNG date for %s: '%s'", r.get("url", "")[:60], raw_date)
                all_results.append(SearXResult(
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    snippet=r.get("content", ""),
                    engine=",".join(r.get("engines", [])),
                    published_date=str(raw_date).strip(),
                    category=r.get("category", ""),
                ))
                if len(all_results) >= max_results:
                    return all_results

            # Stop if no more results
            if not data.get("results"):
                break

            await asyncio.sleep(settings.searxng_delay_seconds)

    except Exception as e:
        logger.error("SearXNG search failed for '%s': %s", query, e)

    return all_results


async def search_news(query: str, *, language: str = "sv-SE",
                      time_range: str = "month",
                      max_results: int = 20) -> list[SearXResult]:
    """Shortcut for news-category search."""
    return await search(
        query,
        categories="news",
        language=language,
        time_range=time_range,
        max_results=max_results,
    )


async def search_social(query: str, *, max_results: int = 10) -> list[SearXResult]:
    """Shortcut for social-media discovery search."""
    return await search(
        query,
        categories="social media",
        max_results=max_results,
    )


async def close():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
