"""Bolagsverket agent — queries the Swedish Companies Registration Office API.

Uses the free Bolagsverket open data API to find company registrations,
board positions, and corporate roles for a person.
"""

from __future__ import annotations

import logging

import httpx

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import CompanyRole, CompanyRoleType, Person, SourceType

logger = logging.getLogger(__name__)

BOLAGSVERKET_API = "https://data.bolagsverket.se"


@register_agent("bolagsverket")
class BolagsverketAgent(BaseAgent):
    """Queries Bolagsverket API for company registrations and board positions."""

    @property
    def name(self) -> str:
        return "bolagsverket"

    @property
    def source_type(self) -> SourceType:
        return SourceType.BOLAGSVERKET

    @property
    def description(self) -> str:
        return "Bolagsverket — company registrations, board positions"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Querying Bolagsverket for {person.namn}")

        # Step 1: Search by person name via API
        companies = await self._search_person(person.namn)
        if not companies:
            await self._report_progress("complete", "No Bolagsverket results found")
            return person

        # Step 2: Parse company roles from API response
        facts = 0
        for company in companies:
            role = self._parse_company_role(company, person.namn)
            if role:
                existing_orgs = {r.org_nummer for r in person.foretag if r.org_nummer}
                if role.org_nummer not in existing_orgs:
                    person.foretag.append(role)
                    facts += 1

                    # Store entity and relationship in knowledge graph
                    company_entity = await self.store_entity(
                        name=role.foretag_namn,
                        entity_type="company",
                        description=f"Org.nr: {role.org_nummer}",
                        metadata={"org_nummer": role.org_nummer},
                    )
                    if company_entity:
                        person_entity = await self.store_entity(
                            name=person.namn,
                            entity_type="person",
                        )
                        if person_entity:
                            await self.store_relation(
                                person_entity, company_entity,
                                relation_type=role.roll.value,
                                description=f"{person.namn} is {role.roll.value} at {role.foretag_namn}",
                            )

        # Step 3: Store source reference
        person.sources.append(self.make_source_ref(BOLAGSVERKET_API))
        if facts > 0:
            await self.store_person_fact(
                person,
                f"Bolagsverket: {facts} company roles found",
                tags=["bolagsverket", "public_records", "company"],
            )

        await self._report_progress("complete", f"Found {facts} company roles", facts_found=facts)
        return person

    async def _search_person(self, namn: str) -> list[dict]:
        """Search Bolagsverket API for companies linked to a person name."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(
                    f"{BOLAGSVERKET_API}/v1/sokperson",
                    params={"namn": namn, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("foretag", data.get("results", []))
            except Exception as e:
                logger.warning("Bolagsverket API search failed: %s", e)
                return []

    @staticmethod
    def _parse_company_role(company_data: dict, person_namn: str) -> CompanyRole | None:
        """Parse a company record from API response into a CompanyRole."""
        namn = company_data.get("namn", company_data.get("foretagsnamn", ""))
        org_nr = company_data.get("org_nummer", company_data.get("organisationsnummer", ""))
        if not namn:
            return None

        # Determine role type from API data
        roll_str = company_data.get("befattning", company_data.get("roll", "styrelseledamot"))
        roll_map = {
            "styrelseledamot": CompanyRoleType.STYRELSELEDAMOT,
            "VD": CompanyRoleType.VD,
            "verkställande direktör": CompanyRoleType.VD,
            "ordförande": CompanyRoleType.ORDFORANDE,
            "suppleant": CompanyRoleType.SUPPLEANT,
            "ägare": CompanyRoleType.AGARE,
            "revisor": CompanyRoleType.REVISOR,
        }
        roll = roll_map.get(roll_str, CompanyRoleType.STYRELSELEDAMOT)

        return CompanyRole(foretag_namn=namn, org_nummer=org_nr, roll=roll)
