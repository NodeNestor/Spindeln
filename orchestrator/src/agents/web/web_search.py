"""Web search agent -- general-purpose web search for person-relevant data."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType, WebMention

logger = logging.getLogger(__name__)


@register_agent("web_search")
class WebSearchAgent(BaseAgent):
    """Performs general web search via SearXNG and extracts person-relevant data."""

    name = "web_search"
    source_type = SourceType.WEB_SEARCH
    description = "General web search for person data"

    async def run(self, person: Person) -> Person:
        if not person.namn:
            return person

        await self._report_progress("running", f"Web searching for {person.namn}")

        queries = self._build_queries(person)
        total_found = 0
        seen_urls: set[str] = set()

        for query in queries:
            results = await self.search(query)
            if not results:
                continue

            for result in results[:8]:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)

                scraped = await self.scrape(result.url)
                if not scraped.get("success") or not scraped.get("markdown"):
                    continue

                # Extract person-relevant data via LLM
                extracted = await self.extract_json(
                    scraped["markdown"],
                    system=WEB_EXTRACT_SYSTEM,
                    user=f"Find information about '{person.namn}' in this page. "
                         f"Known location: {person.adress or 'unknown'}. "
                         f"Known employer: {person.arbetsgivare or 'unknown'}.",
                )
                if not extracted or not extracted.get("relevant"):
                    continue

                mention = WebMention(
                    url=result.url,
                    title=result.title,
                    snippet=extracted.get("summary", result.snippet)[:500],
                    source_type="web_search",
                )
                person.web_mentions.append(mention)
                total_found += 1

                await self.store_person_fact(
                    person,
                    f"Web mention at {result.url}: {extracted.get('summary', '')}",
                    tags=["web_search", extracted.get("category", "general")],
                )

                # If the page reveals new structured data, try to merge it
                if extracted.get("new_data"):
                    await self._merge_new_data(person, extracted["new_data"])

        person.sources.append(self.make_source_ref("searxng:web"))
        logger.info("WebSearch: Found %d mentions for %s", total_found, person.namn)
        return person

    def _build_queries(self, person: Person) -> list[str]:
        """Build varied search queries for the person."""
        queries = [f'"{person.namn}"']
        if person.adress and person.adress.ort:
            queries.append(f'"{person.namn}" {person.adress.ort}')
        if person.arbetsgivare:
            queries.append(f'"{person.namn}" {person.arbetsgivare}')
        if person.personnummer:
            queries.append(f'"{person.personnummer}"')
        return queries[:4]

    async def _merge_new_data(self, person: Person, new_data: dict):
        """Merge newly discovered data fields into person."""
        if new_data.get("arbetsgivare") and not person.arbetsgivare:
            person.arbetsgivare = new_data["arbetsgivare"]
        if new_data.get("telefon"):
            await self.store_person_fact(
                person, f"Phone number found: {new_data['telefon']}",
                tags=["web_search", "phone"],
            )


WEB_EXTRACT_SYSTEM = """You are analyzing a webpage for information about a specific person.

Return JSON:
{
  "relevant": true/false,
  "summary": "Brief summary of what the page says about this person",
  "category": "professional|financial|social|legal|personal|other",
  "new_data": {
    "arbetsgivare": "Employer if found",
    "telefon": "Phone if found",
    "email": "Email if found"
  }
}

Only set relevant=true if the page clearly discusses the target person.
Do not confuse people with similar names."""
