"""Flashback agent — discovers mentions on flashback.org (Swedish forum)."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType, WebMention
from src.scraper.searxng_client import parse_date

logger = logging.getLogger(__name__)


@register_agent("flashback")
class FlashbackAgent(BaseAgent):
    """Discovers mentions and threads on Flashback forum."""

    @property
    def name(self) -> str:
        return "flashback"

    @property
    def source_type(self) -> SourceType:
        return SourceType.FLASHBACK

    @property
    def description(self) -> str:
        return "Flashback — Swedish forum mentions"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Searching Flashback for {person.namn}")

        # Step 1: Build search queries — name + identifiers
        queries = [f'"{person.namn}" site:flashback.org']

        ids = self.get_search_identifiers(person)
        for handle in ids["handles"][:1]:
            queries.append(f'"{handle}" site:flashback.org')
        for email in ids["emails"][:1]:
            queries.append(f'"{email}" site:flashback.org')

        # Step 2: Search with multiple queries
        all_results = []
        seen_urls = set()
        for q in queries[:3]:
            results = await self.search(q, max_results=10)
            for r in results:
                if "flashback.org" in r.url and r.url not in seen_urls:
                    all_results.append(r)
                    seen_urls.add(r.url)

        if not all_results:
            await self._report_progress("complete", "No Flashback mentions found")
            return person

        # Step 3: Scrape and extract relevant mentions
        facts = 0
        for result in all_results[:5]:

            scraped = await self.scrape(result.url)
            if not scraped.get("success") or not scraped.get("markdown"):
                # Even without scraping, record the search result as a mention
                person.web_mentions.append(WebMention(
                    url=result.url,
                    title=result.title,
                    snippet=result.snippet[:300],
                    source_type="flashback",
                ))
                facts += 1
                continue

            # Step 3: Use LLM to check if the content is actually about this person
            verification = await self.extract_json(
                scraped["markdown"],
                system="Determine if this Flashback forum thread mentions a specific person. "
                       "Return JSON: {\"mentions_person\": true/false, \"context\": \"brief summary\", "
                       "\"sentiment\": \"positive|negative|neutral\"}",
                user=f"Does this thread mention '{person.namn}'?",
            )

            if verification and verification.get("mentions_person"):
                context = verification.get("context", result.snippet[:300])
                person.web_mentions.append(WebMention(
                    url=result.url,
                    title=result.title,
                    snippet=context,
                    datum=parse_date(result.published_date),
                    source_type="flashback",
                ))
                facts += 1

                await self.store_person_fact(
                    person,
                    f"Flashback mention: {result.title} — {context[:100]}",
                    tags=["flashback", "social_media", "forum"],
                )

        person.sources.append(self.make_source_ref("https://flashback.org"))
        await self._report_progress("complete", f"Found {facts} mentions", facts_found=facts)
        return person
