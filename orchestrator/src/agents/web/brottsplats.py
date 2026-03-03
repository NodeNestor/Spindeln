"""Brottsplatskartan agent -- scrapes crime events near person's address."""

from __future__ import annotations

import logging
from datetime import date

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType, WebMention

logger = logging.getLogger(__name__)

BROTTSPLATS_URL = "https://brottsplatskartan.se"


@register_agent("brottsplats")
class BrottsplatsAgent(BaseAgent):
    """Searches Brottsplatskartan for crime events near person's address."""

    name = "brottsplats"
    source_type = SourceType.BROTTSPLATSKARTAN
    description = "Brottsplatskartan crime event search near address"

    async def run(self, person: Person) -> Person:
        if not person.adress or not person.adress.gatuadress:
            logger.info("Brottsplats: No address for %s, skipping", person.namn)
            return person

        await self._report_progress(
            "running", f"Checking crime events near {person.adress}",
        )

        queries = self._build_queries(person)
        total_found = 0
        seen_urls: set[str] = set()

        for query in queries:
            results = await self.search(query)
            if not results:
                continue

            for result in results[:10]:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)

                scraped = await self.scrape(result.url)
                if not scraped.get("success") or not scraped.get("markdown"):
                    continue

                extracted = await self.extract_json(
                    scraped["markdown"],
                    system=CRIME_EXTRACT_SYSTEM,
                    user=f"Extract crime events near '{person.adress}' from this page.",
                )
                if not extracted or not extracted.get("events"):
                    continue

                for event in extracted["events"]:
                    mention = WebMention(
                        url=result.url,
                        title=event.get("title", "Crime event"),
                        snippet=event.get("summary", "")[:500],
                        datum=_parse_date(event.get("date")),
                        source_type="brottsplatskartan",
                    )
                    person.web_mentions.append(mention)
                    total_found += 1

                    await self.store_person_fact(
                        person,
                        f"Crime near address ({person.adress}): "
                        f"{event.get('crime_type', '?')} - "
                        f"{event.get('summary', '')}",
                        tags=["brottsplatskartan", "crime",
                              event.get("crime_type", "unknown")],
                    )

        person.sources.append(self.make_source_ref(BROTTSPLATS_URL))
        logger.info(
            "Brottsplats: Found %d crime events near %s", total_found, person.adress,
        )
        return person

    def _build_queries(self, person: Person) -> list[str]:
        """Build search queries for crime events near address."""
        addr = person.adress
        queries: list[str] = []
        if addr.gatuadress:
            queries.append(
                f'"{addr.gatuadress}" site:brottsplatskartan.se',
            )
        if addr.ort:
            queries.append(
                f'"{addr.ort}" site:brottsplatskartan.se',
            )
        if addr.gatuadress and addr.ort:
            queries.append(
                f'"{addr.gatuadress}" "{addr.ort}" brottsplatskartan',
            )
        return queries[:2]


def _parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str[:10])
    except (ValueError, IndexError):
        return None


CRIME_EXTRACT_SYSTEM = """You are extracting crime event data from Brottsplatskartan (Swedish crime map).

Return JSON:
{
  "events": [
    {
      "title": "Event title",
      "crime_type": "stöld|misshandel|inbrott|rån|brand|narkotika|bedrägeri|skadegörelse|trafikolycka|other",
      "date": "YYYY-MM-DD",
      "location": "Street or area",
      "summary": "Brief description of the event",
      "distance_note": "Near / at / close to the target address"
    }
  ]
}

Only include events that are geographically near the target address."""
