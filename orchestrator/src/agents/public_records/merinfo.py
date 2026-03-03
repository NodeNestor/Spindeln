"""Merinfo agent — scrapes merinfo.se for age, property value, neighbors."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Address, Person, Property, SourceType

logger = logging.getLogger(__name__)


@register_agent("merinfo")
class MerinfoAgent(BaseAgent):
    """Scrapes merinfo.se for age, property value, and neighbor data."""

    @property
    def name(self) -> str:
        return "merinfo"

    @property
    def source_type(self) -> SourceType:
        return SourceType.MERINFO

    @property
    def description(self) -> str:
        return "Merinfo.se — age, property value, neighbors"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Searching merinfo.se for {person.namn}")

        # Step 1: Search for the person on merinfo.se
        query = f'"{person.namn}" site:merinfo.se'
        if person.adress and person.adress.ort:
            query += f" {person.adress.ort}"
        results = await self.search(query, max_results=5)

        if not results:
            await self._report_progress("complete", "No merinfo.se results found")
            return person

        # Step 2: Scrape the top result
        top_url = results[0].url
        scraped = await self.scrape(top_url)
        if not scraped.get("success") or not scraped.get("markdown"):
            await self._report_progress("complete", "Failed to scrape merinfo.se page")
            return person

        # Step 3: Extract person data via LLM
        context = f"Looking for: {person.namn}"
        extracted = await self.extract_person(scraped["markdown"], context)
        if not extracted:
            await self._report_progress("complete", "Could not extract data from merinfo.se")
            return person

        # Step 4: Merge extracted data
        facts = self._merge_extracted(person, extracted)

        # Step 5: Store source reference
        person.sources.append(self.make_source_ref(top_url))
        if facts > 0:
            await self.store_person_fact(
                person,
                f"Merinfo data: age/property/neighbors from {top_url}",
                tags=["merinfo", "public_records"],
            )

        await self._report_progress("complete", f"Extracted {facts} fields", facts_found=facts)
        return person

    def _merge_extracted(self, person: Person, data: dict) -> int:
        """Merge merinfo.se data into Person. Returns update count."""
        count = 0

        if data.get("fodelsedatum") and not person.fodelsedatum:
            from datetime import date as _date
            try:
                person.fodelsedatum = _date.fromisoformat(data["fodelsedatum"])
                count += 1
            except (ValueError, TypeError):
                pass

        if data.get("adress") and not person.adress:
            person.adress = Address(**data["adress"])
            count += 1

        # Merinfo is strong on property values
        for prop in data.get("fastigheter", []):
            person.fastigheter.append(Property(**prop))
            count += 1

        # Neighbors
        for granne in data.get("grannar", []):
            if granne not in person.grannar:
                person.grannar.append(granne)
                count += 1

        if data.get("personnummer") and not person.personnummer:
            person.personnummer = data["personnummer"]
            count += 1

        return count
