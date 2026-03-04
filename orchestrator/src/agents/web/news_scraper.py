"""News scraper agent -- searches Swedish and general news for person mentions."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import NewsMention, Person, SourceType
from src.scraper import extractors, searxng_client
from src.scraper.searxng_client import parse_date as _parse_date

logger = logging.getLogger(__name__)

# Major Swedish news outlets to target specifically
SWEDISH_OUTLETS = [
    "svt.se", "sr.se", "dn.se", "svd.se",
    "aftonbladet.se", "expressen.se",
]


@register_agent("news_scraper")
class NewsScraperAgent(BaseAgent):
    """Searches news sources for mentions of the target person.

    Uses DeepResearch-style per-page fact extraction with quality scoring.
    """

    name = "news_scraper"
    source_type = SourceType.NEWS
    description = "News article mention search"

    async def run(self, person: Person) -> Person:
        if not person.namn:
            return person

        await self._report_progress("running", f"Searching news for {person.namn}")

        total_found = 0
        total_facts = 0

        # General news search via SearXNG news category (quoted + unquoted)
        general_query = f'"{person.namn}"'
        if person.adress and person.adress.ort:
            general_query += f" {person.adress.ort}"

        news_results = await searxng_client.search_news(
            general_query, time_range="year", max_results=15,
        )

        # Unquoted fallback if exact match found nothing
        if not news_results:
            fallback_query = person.namn
            if person.adress and person.adress.ort:
                fallback_query += f" {person.adress.ort}"
            news_results = await searxng_client.search_news(
                fallback_query, time_range="year", max_results=15,
            )

        # Also search Swedish outlets specifically
        for outlet in SWEDISH_OUTLETS:
            outlet_results = await self.search(
                f'{person.namn} site:{outlet}',
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

        logger.info("NewsScraper: %d unique results to scrape", len(unique_results))

        for result in unique_results[:15]:
            scraped = await self.scrape(result.url)
            content = scraped.get("markdown") if scraped.get("success") else None
            publication = _detect_publication(result.url)

            if content:
                # DeepResearch-style: extract structured facts per page
                facts = await self.extract_page_facts(
                    content, person,
                    source_url=result.url,
                    source_title=result.title or "",
                )

                if facts:
                    person.sourced_facts.extend(facts)
                    total_facts += len(facts)

                    # Also create a NewsMention for backward compatibility
                    summary = "; ".join(f.content for f in facts[:3])
                    mention = NewsMention(
                        url=result.url,
                        title=result.title or summary[:80],
                        publication=publication,
                        datum=_parse_date(result.published_date),
                        snippet=summary[:500],
                    )
                    person.news_mentions.append(mention)
                    total_found += 1

                    for fact in facts:
                        await self.store_person_fact(
                            person,
                            f"[{publication or 'news'}] {fact.content}",
                            tags=["news", fact.category, publication or "unknown"],
                        )
                    continue

            # Fallback: use SearXNG snippet directly
            snippet = getattr(result, "snippet", "") or getattr(result, "content", "") or ""
            title = getattr(result, "title", "") or ""
            if snippet and person.namn.lower().split()[0] in (snippet + title).lower():
                mention = NewsMention(
                    url=result.url,
                    title=title[:80],
                    publication=publication,
                    datum=_parse_date(getattr(result, "published_date", "")),
                    snippet=snippet[:500],
                )
                person.news_mentions.append(mention)
                total_found += 1

                await self.store_person_fact(
                    person,
                    f"News mention in {publication or 'unknown'}: {title}",
                    tags=["news", "snippet", publication or "unknown"],
                )

        person.sources.append(self.make_source_ref("searxng:news"))
        logger.info("NewsScraper: Found %d mentions, %d facts for %s",
                     total_found, total_facts, person.namn)
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
