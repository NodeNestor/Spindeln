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
    AgentProgress, Person, Company, SourceReference, SourceType,
)
from src.scraper import crawl4ai_client, searxng_client, extractors
from src.storage.client import HiveMindClient

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all Spindeln research agents.

    Subclasses implement `run()` which uses the provided helper methods
    to search, scrape, extract, and store data.
    """

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
        """Generic LLM JSON extraction."""
        return await extractors.extract_json(content, system, user)

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
