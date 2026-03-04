"""Base agent — all scraper agents inherit from this.

Pattern: search → scrape → extract → store.
Each agent focuses on one data source and knows how to parse it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from src.config import settings
from src.models import (
    AgentProgress, Person, Company, SourcedFact, SourceReference, SourceType,
)
from src.scraper import crawl4ai_client, searxng_client, extractors
from src.storage.client import HiveMindClient

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all Spindeln research agents.

    Subclasses implement `run()` which uses the provided helper methods
    to search, scrape, extract, and store data.
    """

    use_synthesis_model: bool = False

    def __init__(self, hivemind: HiveMindClient | None = None):
        self.hivemind = hivemind or HiveMindClient()
        self._progress_callback: Any = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent identifier, e.g. 'ratsit', 'facebook'."""
        ...

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Which source type this agent provides."""
        ...

    @property
    def description(self) -> str:
        return f"{self.name} agent"

    def set_progress_callback(self, callback):
        """Set callback for progress updates: callback(AgentProgress)."""
        self._progress_callback = callback

    async def _report_progress(self, status: str, message: str = "",
                               facts_found: int = 0):
        if self._progress_callback:
            progress = AgentProgress(
                agent_name=self.name,
                status=status,
                facts_found=facts_found,
                message=message,
            )
            await self._progress_callback(progress)

    # ── Helper Methods ────────────────────────────────────────────────────

    async def search(self, query: str, **kwargs) -> list:
        """Search via SearXNG."""
        await asyncio.sleep(settings.searxng_delay_seconds)
        return await searxng_client.search(query, **kwargs)

    async def scrape(self, url: str, **kwargs) -> dict:
        """Scrape a URL via Crawl4AI, returns markdown + metadata."""
        await asyncio.sleep(settings.scrape_delay_seconds)
        return await crawl4ai_client.scrape(url, **kwargs)

    async def extract_person(self, content: str, context: str = "") -> dict | None:
        """Extract person data from scraped content via LLM."""
        return await extractors.extract_person_data(content, context)

    async def extract_company(self, content: str) -> dict | None:
        """Extract company data from scraped content via LLM."""
        return await extractors.extract_company_data(content)

    async def extract_json(self, content: str, system: str, user: str) -> dict | None:
        """Generic LLM JSON extraction. Uses synthesis model if use_synthesis_model is True."""
        if self.use_synthesis_model:
            return await extractors.extract_json_synthesis(content, system, user)
        return await extractors.extract_json(content, system, user)

    def _build_identity_anchors(self, person: Person) -> dict:
        """Build identity anchors from known person data for disambiguation."""
        anchors = {}
        if person.fodelsedatum:
            anchors["birth_date"] = str(person.fodelsedatum)
        if person.adress:
            addr_parts = []
            if person.adress.gatuadress:
                addr_parts.append(person.adress.gatuadress)
            if person.adress.ort:
                addr_parts.append(person.adress.ort)
            if addr_parts:
                anchors["address"] = ", ".join(addr_parts)
        if person.personnummer:
            anchors["personnummer"] = person.personnummer
        return anchors

    def get_search_identifiers(self, person: Person) -> dict:
        """Collect all known identifiers for multi-identifier search.

        Returns dict with lists of emails, handles, phones, companies.
        """
        identifiers: dict[str, list[str]] = {
            "emails": [],
            "handles": [],
            "phones": [],
            "companies": [],
        }

        # From social profiles
        for sp in person.social_media:
            if sp.username:
                identifiers["handles"].append(sp.username)

        # From sourced_facts — scan for emails and handles
        import re
        email_re = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
        handle_re = re.compile(r'@([\w.]{3,30})')
        phone_re = re.compile(r'\b(?:\+46|0)\d[\d\s-]{6,12}\d\b')
        for fact in person.sourced_facts:
            for email in email_re.findall(fact.content):
                if email not in identifiers["emails"]:
                    identifiers["emails"].append(email)
            for handle in handle_re.findall(fact.content):
                if handle not in identifiers["handles"]:
                    identifiers["handles"].append(handle)
            for phone in phone_re.findall(fact.content):
                cleaned = phone.strip()
                if cleaned not in identifiers["phones"]:
                    identifiers["phones"].append(cleaned)

        # From breach data
        for breach in person.breaches:
            for exp in breach.exposed_data:
                if "@" in exp and exp not in identifiers["emails"]:
                    identifiers["emails"].append(exp)

        # From companies
        for co in person.foretag:
            if co.foretag_namn and co.foretag_namn not in identifiers["companies"]:
                identifiers["companies"].append(co.foretag_namn)

        return identifiers

    async def extract_page_facts(self, content: str, person: Person,
                                  source_url: str = "", source_title: str = "") -> list[SourcedFact]:
        """DeepResearch-style per-page fact extraction with quality scoring.

        Returns list of SourcedFact objects extracted from the page.
        """
        context_parts = []
        if person.adress and person.adress.ort:
            context_parts.append(f"Location: {person.adress.ort}")
        if person.arbetsgivare:
            context_parts.append(f"Employer: {person.arbetsgivare}")
        person_context = ". ".join(context_parts)

        identity_anchors = self._build_identity_anchors(person)

        result = await extractors.extract_page_facts(
            content, person.namn,
            person_context=person_context,
            source_url=source_url,
            source_title=source_title,
            identity_anchors=identity_anchors,
        )

        if not result or not result.get("relevant"):
            return []

        quality = result.get("quality", 0)
        if quality < 2:
            return []

        facts = []
        for f in result.get("facts", []):
            fact = SourcedFact(
                content=f.get("fact", ""),
                confidence=f.get("confidence", 0.5),
                source_url=source_url,
                source_title=source_title,
                source_type=self.source_type.value,
                quality_score=quality,
                entities=[e.get("name", "") for e in result.get("entities", []) if isinstance(e, dict)],
                relationships=[r for r in result.get("relationships", []) if isinstance(r, dict)],
                category=f.get("category") or "general",
            )
            if fact.content:
                facts.append(fact)

        return facts

    async def store_person_fact(self, person: Person, fact: str,
                                tags: list[str] | None = None):
        """Store a fact about a person in HiveMindDB."""
        await self.hivemind.add_memory(
            content=fact,
            agent_id=f"spindeln:{self.name}",
            tags=tags or [self.name, "person", person.namn],
            metadata={"person_id": person.id, "source_type": self.source_type.value},
        )

    async def store_entity(self, name: str, entity_type: str,
                           description: str = "", metadata: dict | None = None) -> int | None:
        """Create an entity in HiveMindDB knowledge graph."""
        return await self.hivemind.add_entity(
            name=name,
            entity_type=entity_type,
            description=description,
            agent_id=f"spindeln:{self.name}",
            metadata=metadata or {},
        )

    async def store_relation(self, source_id: int, target_id: int,
                             relation_type: str, description: str = "",
                             weight: float = 1.0):
        """Create a relationship between entities in HiveMindDB."""
        await self.hivemind.add_relationship(
            source_entity_id=source_id,
            target_entity_id=target_id,
            relation_type=relation_type,
            description=description,
            weight=weight,
            created_by=f"spindeln:{self.name}",
        )

    def make_source_ref(self, url: str = "") -> SourceReference:
        """Create a source reference for this agent."""
        return SourceReference(source_type=self.source_type, url=url)

    # ── Main Interface ────────────────────────────────────────────────────

    @abstractmethod
    async def run(self, person: Person) -> Person:
        """Run the agent's investigation for a person.

        Args:
            person: Person object with at least namn (and optionally more seed data).

        Returns:
            Updated Person object with newly discovered data merged in.
        """
        ...

    async def safe_run(self, person: Person) -> Person:
        """Run with error handling and progress reporting."""
        start = time.time()
        await self._report_progress("running", f"Starting {self.description}")

        try:
            result = await self.run(person)
            elapsed = time.time() - start
            n_sources = len(result.sources) - len(person.sources)
            await self._report_progress(
                "complete",
                f"Done in {elapsed:.1f}s",
                facts_found=n_sources,
            )
            return result

        except Exception as e:
            logger.exception("Agent %s failed: %s", self.name, e)
            await self._report_progress("failed", str(e))
            return person
