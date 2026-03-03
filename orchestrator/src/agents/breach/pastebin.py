"""Pastebin agent — searches paste sites for leaked data via SearXNG."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import BreachRecord, Person, SourceType
from src.scraper import extractors

logger = logging.getLogger(__name__)

PASTE_SITES = "site:pastebin.com OR site:ghostbin.com OR site:paste.ee OR site:dpaste.org"


@register_agent("pastebin")
class PastebinAgent(BaseAgent):
    """Searches paste sites for leaked person data via SearXNG."""

    name = "pastebin"
    source_type = SourceType.PASTEBIN
    description = "Paste site leak search"

    async def run(self, person: Person) -> Person:
        queries = self._build_queries(person)
        if not queries:
            return person

        await self._report_progress("running", f"Searching paste sites for {person.namn}")

        total_found = 0
        for query in queries:
            results = await self.search(query)
            if not results:
                continue

            for result in results[:10]:  # Limit scraping to top 10
                scraped = await self.scrape(result.url)
                if not scraped.get("success") or not scraped.get("markdown"):
                    continue

                extracted = await extractors.extract_breach_data(
                    scraped["markdown"],
                    person_context=f"Person: {person.namn}",
                )
                if not extracted:
                    continue

                for breach in extracted.get("breaches", []):
                    record = BreachRecord(
                        breach_name=breach.get("breach_name", f"Paste: {result.title}"),
                        exposed_data=breach.get("exposed_data", []),
                        source="pastebin",
                        severity=breach.get("severity", "medium"),
                    )
                    person.breaches.append(record)
                    total_found += 1

                    await self.store_person_fact(
                        person,
                        f"Paste site exposure at {result.url}: "
                        f"{', '.join(record.exposed_data)}",
                        tags=["pastebin", "breach", record.severity],
                    )

                for paste in extracted.get("paste_mentions", []):
                    await self.store_person_fact(
                        person,
                        f"Paste mention ({paste.get('source', '?')}): "
                        f"{paste.get('content_summary', '')}",
                        tags=["pastebin", "mention"],
                    )

        person.sources.append(self.make_source_ref("searxng:pastebin"))
        logger.info("Pastebin: Found %d exposures for %s", total_found, person.namn)
        return person

    def _build_queries(self, person: Person) -> list[str]:
        """Build SearXNG queries targeting paste sites."""
        queries: list[str] = []
        email = self._get_email(person)

        if person.namn and email:
            queries.append(f'"{person.namn}" OR "{email}" {PASTE_SITES}')
        elif person.namn:
            queries.append(f'"{person.namn}" {PASTE_SITES}')
        elif email:
            queries.append(f'"{email}" {PASTE_SITES}')

        return queries

    @staticmethod
    def _get_email(person: Person) -> str | None:
        for profile in person.social_media:
            if "@" in profile.username:
                return profile.username
        return None
