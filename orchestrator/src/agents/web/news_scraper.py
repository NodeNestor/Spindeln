"""News scraper agent -- searches Swedish and general news for person mentions."""

from __future__ import annotations

import logging
from datetime import date

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import NewsMention, Person, SourceType
from src.scraper import extractors, searxng_client

logger = logging.getLogger(__name__)

# Major Swedish news outlets to target specifically
SWEDISH_OUTLETS = [
    "svt.se", "sr.se", "dn.se", "svd.se",
    "aftonbladet.se", "expressen.se",
]


@register_agent("news_scraper")
class NewsScraperAgent(BaseAgent):
    """Searches news sources for mentions of the target person."""

    name = "news_scraper"
    source_type = SourceType.NEWS
    description = "News article mention search"

    async def run(self, person: Person) -> Person:
        if not person.namn:
            return person

        await self._report_progress("running", f"Searching news for {person.namn}")

        total_found = 0

        # General news search via SearXNG news category
        general_query = f'"{person.namn}"'
        if person.adress and person.adress.ort:
            general_query += f" {person.adress.ort}"

        news_results = await searxng_client.search_news(
            general_query, time_range="year", max_results=15,
        )

        # Also search Swedish outlets specifically
        for outlet in SWEDISH_OUTLETS:
            outlet_results = await self.search(
                f'"{person.namn}" site:{outlet}',
                categories="general",
            )
            news_results.extend(outlet_results[:3])

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_results = []
        for r in news_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                unique_results.append(r)

        # Scrape and extract from top results
        for result in unique_results[:15]:
            scraped = await self.scrape(result.url)
            if not scraped.get("success") or not scraped.get("markdown"):
                continue

            extracted = await extractors.extract_news_mention(
                scraped["markdown"], person.namn,
            )
            if not extracted or not extracted.get("mentions_person"):
                continue

            mention = NewsMention(
                url=result.url,
                title=result.title or extracted.get("summary", "")[:80],
                publication=_detect_publication(result.url),
                datum=_parse_date(result.published_date),
                snippet=extracted.get("summary", "")[:500],
            )
            person.news_mentions.append(mention)
            total_found += 1

            sentiment = extracted.get("sentiment", "neutral")
            await self.store_person_fact(
                person,
                f"News mention in {mention.publication or 'unknown'}: "
                f"{mention.title}. Sentiment: {sentiment}. "
                f"Role: {extracted.get('person_role', 'mentioned')}",
                tags=["news", sentiment, mention.publication or "unknown"],
            )

        person.sources.append(self.make_source_ref("searxng:news"))
        logger.info("NewsScraper: Found %d mentions for %s", total_found, person.namn)
        return person


def _detect_publication(url: str) -> str:
    """Detect publication name from URL domain."""
    domain_map = {
        "svt.se": "SVT Nyheter", "sr.se": "Sveriges Radio",
        "dn.se": "Dagens Nyheter", "svd.se": "Svenska Dagbladet",
        "aftonbladet.se": "Aftonbladet", "expressen.se": "Expressen",
        "gp.se": "Göteborgs-Posten", "sydsvenskan.se": "Sydsvenskan",
    }
    for domain, name in domain_map.items():
        if domain in url:
            return name
    return ""


def _parse_date(date_str: str) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str[:10])
    except (ValueError, IndexError):
        return None
