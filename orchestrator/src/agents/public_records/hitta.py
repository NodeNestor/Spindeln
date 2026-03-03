"""Hitta agent — scrapes hitta.se for phone, address, neighbors, map data."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Address, Person, SourceType

logger = logging.getLogger(__name__)


@register_agent("hitta")
class HittaAgent(BaseAgent):
    """Scrapes hitta.se for contact details, address, and neighbor data."""

    @property
    def name(self) -> str:
        return "hitta"

    @property
    def source_type(self) -> SourceType:
        return SourceType.HITTA

    @property
    def description(self) -> str:
        return "Hitta.se — phone, address, neighbors, map location"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Searching hitta.se for {person.namn}")

        # Step 1: Search for the person on hitta.se
        query = f'"{person.namn}" site:hitta.se'
        if person.adress and person.adress.ort:
            query += f" {person.adress.ort}"
        results = await self.search(query, max_results=5)

        if not results:
            await self._report_progress("complete", "No hitta.se results found")
            return person

        # Step 2: Scrape the top result
        top_url = results[0].url
        scraped = await self.scrape(top_url)
        if not scraped.get("success") or not scraped.get("markdown"):
            await self._report_progress("complete", "Failed to scrape hitta.se page")
            return person

        # Step 3: Extract person data via LLM
        context = f"Looking for: {person.namn}"
        extracted = await self.extract_person(scraped["markdown"], context)
        if not extracted:
            await self._report_progress("complete", "Could not extract data from hitta.se")
            return person

        # Step 4: Merge extracted data
        facts = self._merge_extracted(person, extracted)

        # Step 5: Store source reference
        person.sources.append(self.make_source_ref(top_url))
        if facts > 0:
            await self.store_person_fact(
                person,
                f"Hitta data: phone/address/neighbors from {top_url}",
                tags=["hitta", "public_records"],
            )

        await self._report_progress("complete", f"Extracted {facts} fields", facts_found=facts)
        return person

    def _merge_extracted(self, person: Person, data: dict) -> int:
        """Merge hitta.se data into Person. Returns update count."""
        count = 0

        # Address (hitta often has the most current address)
        if data.get("adress"):
            addr = Address(**data["adress"])
            if not person.adress:
                person.adress = addr
                count += 1
            elif addr.gatuadress and addr.gatuadress != person.adress.gatuadress:
                person.adress_historik.append(person.adress)
                person.adress = addr
                count += 1

        # Coordinates from map
        if data.get("adress") and person.adress:
            addr_data = data["adress"]
            if addr_data.get("latitude") and not person.adress.latitude:
                person.adress.latitude = addr_data["latitude"]
                person.adress.longitude = addr_data.get("longitude")
                count += 1

        # Neighbors
        for granne in data.get("grannar", []):
            if granne not in person.grannar:
                person.grannar.append(granne)
                count += 1

        # Personnummer if found
        if data.get("personnummer") and not person.personnummer:
            person.personnummer = data["personnummer"]
            count += 1

        return count
