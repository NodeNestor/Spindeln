"""Ahmia agent — searches clearnet index of Tor .onion sites for person mentions."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import BreachRecord, Person, SourceType, WebMention
from src.scraper import extractors

logger = logging.getLogger(__name__)

AHMIA_SEARCH_URL = "https://ahmia.fi/search/"


@register_agent("ahmia")
class AhmiaAgent(BaseAgent):
    """Searches Ahmia (clearnet Tor index) for dark web mentions."""

    name = "ahmia"
    source_type = SourceType.AHMIA
    description = "Ahmia dark web (.onion) mention search"

    async def run(self, person: Person) -> Person:
        queries = self._build_queries(person)
        if not queries:
            return person

        await self._report_progress("running", f"Searching Ahmia for {person.namn}")

        total_found = 0
        for query in queries:
            scraped = await self.scrape(
                f"{AHMIA_SEARCH_URL}?q={query}",
                css_selector=".result",
            )
            if not scraped.get("success") or not scraped.get("markdown"):
                continue

            # Use LLM to extract relevant mentions
            extracted = await self.extract_json(
                scraped["markdown"],
                system=DARK_WEB_EXTRACT_SYSTEM,
                user=f"Find any mentions of '{person.namn}' in these dark web "
                     f"search results. Look for leaked data, marketplace "
                     f"listings, forum posts, or any references.",
            )
            if not extracted or not extracted.get("mentions"):
                continue

            for mention in extracted["mentions"]:
                severity = mention.get("severity", "medium")
                # If it looks like breach data, add as BreachRecord
                if mention.get("is_breach"):
                    person.breaches.append(BreachRecord(
                        breach_name=f"Dark web: {mention.get('source', 'unknown')}",
                        exposed_data=mention.get("exposed_data", []),
                        source="ahmia",
                        severity=severity,
                    ))
                else:
                    person.web_mentions.append(WebMention(
                        url=mention.get("url", AHMIA_SEARCH_URL),
                        title=mention.get("title", "Dark web mention"),
                        snippet=mention.get("summary", ""),
                        source_type="ahmia",
                    ))

                await self.store_person_fact(
                    person,
                    f"Dark web mention via Ahmia: {mention.get('summary', '')}",
                    tags=["ahmia", "darkweb", severity],
                )
                total_found += 1

        person.sources.append(self.make_source_ref(AHMIA_SEARCH_URL))
        logger.info("Ahmia: Found %d dark web mentions for %s", total_found, person.namn)
        return person

    def _build_queries(self, person: Person) -> list[str]:
        """Build search queries from person data."""
        queries: list[str] = []
        if person.namn:
            queries.append(f'"{person.namn}"')
        # Add email if known
        for profile in person.social_media:
            if "@" in profile.username:
                queries.append(f'"{profile.username}"')
                break
        return queries[:2]


DARK_WEB_EXTRACT_SYSTEM = """You are analyzing search results from Ahmia, a dark web search engine.
Extract any mentions relevant to the target person.

Return JSON:
{
  "mentions": [
    {
      "title": "Result title",
      "url": "URL if available",
      "summary": "Brief description of the mention",
      "source": "Forum name / marketplace / paste site",
      "is_breach": true/false,
      "exposed_data": ["email", "password"],
      "severity": "low|medium|high|critical"
    }
  ]
}

Only include results that clearly reference the target person. Be conservative."""
