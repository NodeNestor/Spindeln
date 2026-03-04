"""Web search agent -- general-purpose web search for person-relevant data."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType, WebMention
from src.scraper.searxng_client import parse_date

logger = logging.getLogger(__name__)


@register_agent("web_search")
class WebSearchAgent(BaseAgent):
    """Performs general web search via SearXNG and extracts person-relevant data.

    Uses DeepResearch-style per-page fact extraction with quality scoring.
    """

    name = "web_search"
    source_type = SourceType.WEB_SEARCH
    description = "General web search for person data"

    async def run(self, person: Person) -> Person:
        if not person.namn:
            return person

        await self._report_progress("running", f"Web searching for {person.namn}")

        queries = self._build_queries(person)
        total_found = 0
        total_facts = 0
        seen_urls: set[str] = set()

        for query in queries:
            results = await self.search(query)
            logger.info("WebSearch query '%s' returned %d results", query, len(results) if results else 0)
            if not results:
                continue

            for result in results[:8]:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)

                content = None
                scraped = await self.scrape(result.url)
                if scraped.get("success") and scraped.get("markdown"):
                    content = scraped["markdown"]

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

                        # Also create a WebMention for backward compatibility
                        summary = "; ".join(f.content for f in facts[:3])
                        mention = WebMention(
                            url=result.url,
                            title=result.title,
                            snippet=summary[:500],
                            datum=parse_date(result.published_date),
                            source_type="web_search",
                        )
                        person.web_mentions.append(mention)
                        total_found += 1

                        # Store aggregated facts in HiveMindDB
                        for fact in facts:
                            await self.store_person_fact(
                                person, fact.content,
                                tags=["web_search", fact.category, str(fact.quality_score)],
                            )
                        continue

                # Fallback: use SearXNG snippet directly if it mentions the person
                if result.snippet and person.namn.lower().split()[0] in result.snippet.lower():
                    mention = WebMention(
                        url=result.url,
                        title=result.title,
                        snippet=result.snippet[:500],
                        datum=parse_date(result.published_date),
                        source_type="web_search",
                    )
                    person.web_mentions.append(mention)
                    total_found += 1

                    await self.store_person_fact(
                        person,
                        f"Web mention at {result.url}: {result.snippet[:300]}",
                        tags=["web_search", "snippet"],
                    )

        person.sources.append(self.make_source_ref("searxng:web"))
        logger.info("WebSearch: Found %d mentions, %d facts for %s",
                     total_found, total_facts, person.namn)
        return person

    def _build_queries(self, person: Person) -> list[str]:
        """Build varied search queries for the person."""
        queries = [
            f'"{person.namn}"',   # exact match
            person.namn,           # unquoted fallback
        ]
        if person.adress and person.adress.ort:
            queries.append(f'{person.namn} {person.adress.ort}')
        if person.arbetsgivare:
            queries.append(f'{person.namn} {person.arbetsgivare}')
        if person.personnummer:
            queries.append(f'"{person.personnummer}"')
        return queries[:5]
