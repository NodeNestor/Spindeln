"""Ratsit agent — scrapes ratsit.se for Swedish person data.

Extracts: income, tax, family relations, address history, company roles,
payment remarks, and property data.
"""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import (
    Address, CompanyRole, FamilyRelation, Income, PaymentRemark,
    Person, SourceType, Tax,
)

logger = logging.getLogger(__name__)


@register_agent("ratsit")
class RatsitAgent(BaseAgent):
    """Scrapes ratsit.se for comprehensive Swedish personal records."""

    @property
    def name(self) -> str:
        return "ratsit"

    @property
    def source_type(self) -> SourceType:
        return SourceType.RATSIT

    @property
    def description(self) -> str:
        return "Ratsit.se — income, tax, family, address, company roles"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Searching ratsit.se for {person.namn}")

        # Step 1: Search SearXNG for the person on ratsit.se
        query = f'"{person.namn}" site:ratsit.se'
        if person.adress and person.adress.ort:
            query += f" {person.adress.ort}"
        results = await self.search(query, max_results=5)

        if not results:
            await self._report_progress("complete", "No ratsit.se results found")
            return person

        # Step 2: Scrape the top result
        top_url = results[0].url
        scraped = await self.scrape(top_url)
        if not scraped.get("success") or not scraped.get("markdown"):
            await self._report_progress("complete", "Failed to scrape ratsit.se page")
            return person

        # Step 3: Extract structured person data via LLM
        context = f"Looking for: {person.namn}"
        if person.fodelsedatum:
            context += f", born {person.fodelsedatum}"
        extracted = await self.extract_person(scraped["markdown"], context)
        if not extracted:
            await self._report_progress("complete", "Could not extract data from ratsit.se")
            return person

        # Step 4: Merge extracted data into person
        facts = 0
        facts += self._merge_extracted(person, extracted)

        # Step 5: Store facts and source reference
        person.sources.append(self.make_source_ref(top_url))
        if facts > 0:
            await self.store_person_fact(
                person,
                f"Ratsit data: {facts} fields updated from {top_url}",
                tags=["ratsit", "public_records"],
            )

        await self._report_progress("complete", f"Extracted {facts} fields", facts_found=facts)
        return person

    def _merge_extracted(self, person: Person, data: dict) -> int:
        """Merge extracted dict fields into the Person model. Returns count of updates."""
        count = 0

        if data.get("personnummer") and not person.personnummer:
            person.personnummer = data["personnummer"]
            count += 1

        if data.get("fodelsedatum") and not person.fodelsedatum:
            from datetime import date as _date
            try:
                person.fodelsedatum = _date.fromisoformat(data["fodelsedatum"])
                count += 1
            except (ValueError, TypeError):
                pass

        if data.get("kon") and person.kon.value == "okänt":
            from src.models import Kon
            person.kon = Kon(data["kon"]) if data["kon"] in ("man", "kvinna") else person.kon
            count += 1

        if data.get("adress") and not person.adress:
            person.adress = Address(**data["adress"])
            count += 1

        for addr in data.get("adress_historik", []):
            person.adress_historik.append(Address(**addr))
            count += 1

        for inc in data.get("inkomst", []):
            person.inkomst.append(Income(**inc))
            count += 1

        for tax in data.get("skatt", []):
            person.skatt.append(Tax(**tax))
            count += 1

        for remark in data.get("betalningsanmarkningar", []):
            person.betalningsanmarkningar.append(PaymentRemark(**remark))
            count += 1

        if data.get("arbetsgivare") and not person.arbetsgivare:
            person.arbetsgivare = data["arbetsgivare"]
            count += 1

        for role in data.get("foretag", []):
            person.foretag.append(CompanyRole(**role))
            count += 1

        for rel in data.get("familj", []):
            person.familj.append(FamilyRelation(**rel))
            count += 1

        for granne in data.get("grannar", []):
            if granne not in person.grannar:
                person.grannar.append(granne)
                count += 1

        return count
