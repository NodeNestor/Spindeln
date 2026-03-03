"""Eniro agent — scrapes eniro.se for phone, address, business listings."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Address, CompanyRole, Person, SourceType

logger = logging.getLogger(__name__)


@register_agent("eniro")
class EniroAgent(BaseAgent):
    """Scrapes eniro.se for contact details, addresses, and business listings."""

    @property
    def name(self) -> str:
        return "eniro"

    @property
    def source_type(self) -> SourceType:
        return SourceType.ENIRO

    @property
    def description(self) -> str:
        return "Eniro.se — phone, address, business listings"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Searching eniro.se for {person.namn}")

        # Step 1: Search for the person on eniro.se
        query = f'"{person.namn}" site:eniro.se'
        if person.adress and person.adress.ort:
            query += f" {person.adress.ort}"
        results = await self.search(query, max_results=5)

        if not results:
            await self._report_progress("complete", "No eniro.se results found")
            return person

        # Step 2: Scrape the top result
        top_url = results[0].url
        scraped = await self.scrape(top_url)
        if not scraped.get("success") or not scraped.get("markdown"):
            await self._report_progress("complete", "Failed to scrape eniro.se page")
            return person

        # Step 3: Extract person data via LLM
        context = f"Looking for: {person.namn}"
        extracted = await self.extract_person(scraped["markdown"], context)
        if not extracted:
            await self._report_progress("complete", "Could not extract data from eniro.se")
            return person

        # Step 4: Merge extracted data
        facts = self._merge_extracted(person, extracted)

        # Step 5: Store source reference
        person.sources.append(self.make_source_ref(top_url))
        if facts > 0:
            await self.store_person_fact(
                person,
                f"Eniro data: phone/address/business from {top_url}",
                tags=["eniro", "public_records"],
            )

        await self._report_progress("complete", f"Extracted {facts} fields", facts_found=facts)
        return person

    def _merge_extracted(self, person: Person, data: dict) -> int:
        """Merge eniro.se data into Person. Returns update count."""
        count = 0

        if data.get("adress") and not person.adress:
            person.adress = Address(**data["adress"])
            count += 1

        if data.get("personnummer") and not person.personnummer:
            person.personnummer = data["personnummer"]
            count += 1

        # Eniro is strong on business listings
        for role in data.get("foretag", []):
            existing_orgs = {r.org_nummer for r in person.foretag if r.org_nummer}
            org_nr = role.get("org_nummer", "")
            if org_nr not in existing_orgs:
                person.foretag.append(CompanyRole(**role))
                count += 1

        if data.get("arbetsgivare") and not person.arbetsgivare:
            person.arbetsgivare = data["arbetsgivare"]
            count += 1

        return count
