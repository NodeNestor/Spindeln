"""Graph builder agent -- constructs HiveMindDB knowledge graph from person data."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType
from src.storage import schemas

logger = logging.getLogger(__name__)


@register_agent("graph_builder")
class GraphBuilderAgent(BaseAgent):
    """Reads all person data and creates entities + relationships in HiveMindDB."""

    name = "graph_builder"
    source_type = SourceType.WEB_SEARCH  # meta agent, no primary source
    description = "Knowledge graph construction from person data"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Building graph for {person.namn}")

        # 1. Create the person entity
        person_id = await self.store_entity(
            name=person.namn,
            entity_type=schemas.ENTITY_PERSON,
            description=self._person_description(person),
            metadata={"person_id": person.id, "pnr": person.personnummer or ""},
        )
        if not person_id:
            logger.error("GraphBuilder: Failed to create person entity")
            return person

        # 2. Address entity
        if person.adress and person.adress.gatuadress:
            addr_id = await self.store_entity(
                name=str(person.adress),
                entity_type=schemas.ENTITY_ADDRESS,
                metadata={"kommun": person.adress.kommun, "lan": person.adress.lan},
            )
            if addr_id:
                await self.store_relation(
                    person_id, addr_id, schemas.REL_LIVES_AT,
                    description=f"{person.namn} bor på {person.adress}",
                )

        # 3. Historical addresses
        for old_addr in person.adress_historik:
            old_id = await self.store_entity(
                name=str(old_addr), entity_type=schemas.ENTITY_ADDRESS,
                metadata={"kommun": old_addr.kommun})
            if old_id:
                await self.store_relation(person_id, old_id, schemas.REL_LIVED_AT)

        # 4. Company entities and roles
        for role in person.foretag:
            company_id = await self.store_entity(
                name=role.foretag_namn,
                entity_type=schemas.ENTITY_COMPANY,
                metadata={"org_nummer": role.org_nummer},
            )
            if company_id:
                rel_type = schemas.role_to_relation(role.roll.value)
                await self.store_relation(
                    person_id, company_id, rel_type,
                    description=f"{person.namn} är {role.roll.value} i {role.foretag_namn}",
                )

        # 5. Social profiles
        for profile in person.social_media:
            meta = {"platform": profile.platform, "url": profile.url,
                    "confidence": profile.confidence}
            pid = await self.store_entity(
                name=f"{profile.platform}: {profile.username or profile.url}",
                entity_type=schemas.ENTITY_SOCIAL_PROFILE, metadata=meta)
            if pid:
                await self.store_relation(
                    person_id, pid, schemas.REL_HAS_PROFILE,
                    weight=profile.confidence)

        # 6. Family relations (person-to-person)
        for rel in person.familj:
            rid = await self.store_entity(
                name=rel.person_namn, entity_type=schemas.ENTITY_PERSON,
                metadata={"relation_to": person.namn})
            if rid:
                await self.store_relation(
                    person_id, rid, schemas.family_to_relation(rel.relation.value))

        # 7. Vehicles
        for vehicle in person.fordon:
            v_name = f"{vehicle.marke} {vehicle.modell} ({vehicle.registreringsnummer})"
            v_id = await self.store_entity(
                name=v_name, entity_type=schemas.ENTITY_VEHICLE,
                metadata={"reg": vehicle.registreringsnummer})
            if v_id:
                await self.store_relation(person_id, v_id, schemas.REL_DRIVES)

        # 8. Breach records
        for breach in person.breaches:
            b_id = await self.store_entity(
                name=breach.breach_name, entity_type=schemas.ENTITY_BREACH,
                metadata={"severity": breach.severity, "source": breach.source})
            if b_id:
                await self.store_relation(person_id, b_id, schemas.REL_EXPOSED_IN)

        person.sources.append(self.make_source_ref("hiveminddb:graph"))
        logger.info("GraphBuilder: Created graph for %s", person.namn)
        return person

    @staticmethod
    def _person_description(person: Person) -> str:
        parts = [person.namn]
        if person.fodelsedatum:
            parts.append(f"född {person.fodelsedatum}")
        if person.adress and person.adress.ort:
            parts.append(person.adress.ort)
        if person.arbetsgivare:
            parts.append(f"arbetar på {person.arbetsgivare}")
        return ", ".join(parts)
