"""Riksdag agent — queries the Swedish Parliament open data API.

Uses the free Riksdag API to check if a person is a current or former
politician and retrieve political data (party, constituency, sessions).
"""

from __future__ import annotations

import logging

import httpx

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType, WebMention

logger = logging.getLogger(__name__)

RIKSDAG_API = "https://data.riksdagen.se"


@register_agent("riksdag")
class RiksdagAgent(BaseAgent):
    """Queries Riksdag API for political roles and parliamentary data."""

    @property
    def name(self) -> str:
        return "riksdag"

    @property
    def source_type(self) -> SourceType:
        return SourceType.RIKSDAG

    @property
    def description(self) -> str:
        return "Riksdag — political roles, parliamentary data"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Querying Riksdag API for {person.namn}")

        # Split name into first/last for API query
        name_parts = person.namn.strip().split()
        if len(name_parts) < 2:
            await self._report_progress("complete", "Need first and last name for Riksdag search")
            return person

        fornamn = name_parts[0]
        efternamn = " ".join(name_parts[1:])

        # Step 1: Query the Riksdag person list API
        politicians = await self._search_person(fornamn, efternamn)
        if not politicians:
            await self._report_progress("complete", "Person not found in Riksdag")
            return person

        # Step 2: Process matching politicians
        facts = 0
        for pol in politicians:
            # Store political data as web mention with details
            parti = pol.get("parti", "")
            valkrets = pol.get("valkrets", "")
            status = pol.get("status", "")
            sourceid = pol.get("sourceid", "")

            url = f"{RIKSDAG_API}/personlista/?iid={sourceid}&format=json" if sourceid else ""
            summary = f"Riksdagsledamot: {parti}"
            if valkrets:
                summary += f", valkrets: {valkrets}"
            if status:
                summary += f", status: {status}"

            person.web_mentions.append(WebMention(
                url=url or f"{RIKSDAG_API}/personlista/",
                title=f"Riksdagsledamot — {parti}",
                snippet=summary,
                source_type="riksdag",
            ))
            facts += 1

            # Store in knowledge graph
            await self.store_person_fact(
                person, summary,
                tags=["riksdag", "politics", "public_records", parti],
            )

        person.sources.append(self.make_source_ref(f"{RIKSDAG_API}/personlista/"))
        await self._report_progress("complete", f"Found {facts} political records", facts_found=facts)
        return person

    async def _search_person(self, fornamn: str, efternamn: str) -> list[dict]:
        """Query Riksdag personlista API."""
        url = f"{RIKSDAG_API}/personlista/"
        params = {
            "fnamn": fornamn,
            "enamn": efternamn,
            "format": "json",
            "utformat": "json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                # API returns personlista -> person (list or single object)
                persons = data.get("personlista", {}).get("person", [])
                if isinstance(persons, dict):
                    persons = [persons]
                return persons
            except Exception as e:
                logger.warning("Riksdag API search failed: %s", e)
                return []
