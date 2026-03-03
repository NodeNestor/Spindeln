"""Investigation pipeline — orchestrates the multi-phase research swarm."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable

from src.config import settings
from src.models import (
    InvestigationPhase, InvestigationSession, Person, ProgressEvent,
)
from src.agents.base import BaseAgent
from src.agents.registry import get_agents_by_category, get_all_agents
from src.storage.client import HiveMindClient

logger = logging.getLogger(__name__)


async def run_investigation(
    query: str,
    location: str | None,
    session: InvestigationSession,
    progress_callback: Callable | None,
    hivemind: HiveMindClient,
) -> Person:
    """Run full investigation pipeline for a person.

    Phases:
        0. Seed resolution — anchor identity from Ratsit/Hitta
        1. Public records — parallel swarm across Swedish registries
        2. Social media — discover profiles via SearXNG
        3. Web + news — general web mentions
        3.5. Breach check — exposure data
        4. Graph construction — build relationships in HiveMindDB
        5. Embeddings — multi-category vectors
        6. Loom bridge — temporal context
    """

    async def _progress(phase: InvestigationPhase, agent: str = "",
                        status: str = "", message: str = "", facts: int = 0):
        session.current_phase = phase
        if progress_callback:
            await progress_callback(ProgressEvent(
                session_id=session.id,
                phase=phase,
                agent_name=agent,
                status=status,
                message=message,
                facts_found=facts,
            ))

    # ── Phase 0: Seed Resolution ──────────────────────────────────────────
    await _progress(InvestigationPhase.SEED_RESOLUTION, status="running",
                    message=f"Resolving identity for: {query}")

    person = Person(namn=query)
    if location:
        from src.models import Address
        person.adress = Address(ort=location)

    # Try to resolve via public record agents (ratsit, hitta first)
    seed_agents = _get_seed_agents()
    if seed_agents:
        person = await _run_agent(seed_agents[0], person, hivemind, progress_callback, session)

    await _progress(InvestigationPhase.SEED_RESOLUTION, status="complete",
                    message=f"Identity anchored: {person.namn}")

    # ── Phase 1: Public Records ───────────────────────────────────────────
    await _progress(InvestigationPhase.PUBLIC_RECORDS, status="running",
                    message="Launching public records swarm")

    public_agents = get_agents_by_category("public_records")
    person = await _run_parallel_agents(
        public_agents, person, hivemind, progress_callback, session,
    )

    await _progress(InvestigationPhase.PUBLIC_RECORDS, status="complete",
                    facts=session.facts_discovered)

    # ── Phase 2: Social Media ─────────────────────────────────────────────
    await _progress(InvestigationPhase.SOCIAL_MEDIA, status="running",
                    message="Discovering social media profiles")

    social_agents = get_agents_by_category("social_media")
    person = await _run_parallel_agents(
        social_agents, person, hivemind, progress_callback, session,
    )

    await _progress(InvestigationPhase.SOCIAL_MEDIA, status="complete",
                    facts=session.facts_discovered)

    # ── Phase 3: Web + News ───────────────────────────────────────────────
    await _progress(InvestigationPhase.WEB_NEWS, status="running",
                    message="Searching web and news sources")

    web_agents = get_agents_by_category("web")
    person = await _run_parallel_agents(
        web_agents, person, hivemind, progress_callback, session,
    )

    await _progress(InvestigationPhase.WEB_NEWS, status="complete",
                    facts=session.facts_discovered)

    # ── Phase 3.5: Breach Check ───────────────────────────────────────────
    await _progress(InvestigationPhase.BREACH_CHECK, status="running",
                    message="Checking breach databases")

    breach_agents = get_agents_by_category("breach")
    person = await _run_parallel_agents(
        breach_agents, person, hivemind, progress_callback, session,
    )

    await _progress(InvestigationPhase.BREACH_CHECK, status="complete",
                    facts=session.facts_discovered)

    # ── Phase 4: Graph Construction ───────────────────────────────────────
    await _progress(InvestigationPhase.GRAPH_CONSTRUCTION, status="running",
                    message="Building knowledge graph")

    analysis_agents = get_agents_by_category("analysis")
    for agent in analysis_agents:
        if "graph" in agent.name:
            person = await _run_agent(agent, person, hivemind, progress_callback, session)

    await _progress(InvestigationPhase.GRAPH_CONSTRUCTION, status="complete")

    # ── Phase 5: Embeddings ───────────────────────────────────────────────
    await _progress(InvestigationPhase.EMBEDDING_GENERATION, status="running",
                    message="Generating multi-category embeddings")

    try:
        from src.embeddings import generate_embeddings
        person = await generate_embeddings(person)
    except Exception as e:
        logger.warning("Embedding generation failed: %s", e)

    await _progress(InvestigationPhase.EMBEDDING_GENERATION, status="complete")

    # ── Phase 6: Loom Bridge ──────────────────────────────────────────────
    await _progress(InvestigationPhase.LOOM_BRIDGE, status="running",
                    message="Querying Loom temporal data")

    try:
        from src.loom.client import LoomBridge
        loom = LoomBridge()
        loom_events = await loom.search_person(person)
        logger.info("Found %d Loom events for %s", len(loom_events), person.namn)
    except Exception as e:
        logger.warning("Loom bridge failed: %s", e)

    await _progress(InvestigationPhase.LOOM_BRIDGE, status="complete")

    # ── Done ──────────────────────────────────────────────────────────────
    person.last_updated = datetime.utcnow()
    session.facts_discovered = _count_facts(person)
    await _progress(InvestigationPhase.COMPLETE, status="complete",
                    message="Investigation complete",
                    facts=session.facts_discovered)

    return person


def _get_seed_agents() -> list[BaseAgent]:
    """Get agents suitable for seed resolution (ratsit first, then hitta)."""
    from src.agents.registry import _REGISTRY
    seed_names = ["ratsit", "hitta", "merinfo"]
    agents = []
    for name in seed_names:
        cls = _REGISTRY.get(name)
        if cls:
            agents.append(cls())
    return agents


async def _run_agent(agent: BaseAgent, person: Person, hivemind: HiveMindClient,
                     progress_callback, session: InvestigationSession) -> Person:
    """Run a single agent with progress reporting."""
    agent.hivemind = hivemind

    if progress_callback:
        async def _cb(progress):
            session.agent_progress.append(progress)
            await progress_callback(ProgressEvent(
                session_id=session.id,
                phase=session.current_phase,
                agent_name=progress.agent_name,
                status=progress.status,
                message=progress.message,
                facts_found=progress.facts_found,
            ))
        agent.set_progress_callback(_cb)

    return await agent.safe_run(person)


async def _run_parallel_agents(agents: list[BaseAgent], person: Person,
                               hivemind: HiveMindClient,
                               progress_callback, session: InvestigationSession,
                               max_concurrent: int | None = None) -> Person:
    """Run multiple agents in parallel with bounded concurrency.

    Each agent gets a copy of the person to read from, but all updates
    are merged back into a single Person at the end.
    """
    if not agents:
        return person

    concurrency = max_concurrent or settings.scrape_concurrency
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded_run(agent: BaseAgent) -> Person:
        async with semaphore:
            return await _run_agent(agent, person, hivemind, progress_callback, session)

    tasks = [_bounded_run(a) for a in agents]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge all results into person
    for result in results:
        if isinstance(result, Person):
            person = _merge_person(person, result)
        elif isinstance(result, Exception):
            logger.warning("Agent failed: %s", result)

    return person


def _merge_person(base: Person, update: Person) -> Person:
    """Merge data from update into base, keeping all unique entries."""
    # Merge list fields (append unique items)
    for field in [
        "inkomst", "skatt", "betalningsanmarkningar", "foretag",
        "fastigheter", "fordon", "familj", "grannar",
        "social_media", "web_mentions", "news_mentions", "breaches",
        "sources", "adress_historik",
    ]:
        base_list = getattr(base, field)
        update_list = getattr(update, field)
        for item in update_list:
            if item not in base_list:
                base_list.append(item)

    # Merge scalar fields (prefer non-empty update)
    if update.personnummer and not base.personnummer:
        base.personnummer = update.personnummer
    if update.fodelsedatum and not base.fodelsedatum:
        base.fodelsedatum = update.fodelsedatum
    if update.kon != "okänt" and base.kon == "okänt":
        base.kon = update.kon
    if update.adress and not base.adress:
        base.adress = update.adress
    if update.arbetsgivare and not base.arbetsgivare:
        base.arbetsgivare = update.arbetsgivare

    return base


def _count_facts(person: Person) -> int:
    """Count total facts discovered about a person."""
    count = 0
    count += len(person.inkomst)
    count += len(person.skatt)
    count += len(person.betalningsanmarkningar)
    count += len(person.foretag)
    count += len(person.fastigheter)
    count += len(person.fordon)
    count += len(person.familj)
    count += len(person.grannar)
    count += len(person.social_media)
    count += len(person.web_mentions)
    count += len(person.news_mentions)
    count += len(person.breaches)
    count += 1 if person.personnummer else 0
    count += 1 if person.adress else 0
    count += 1 if person.arbetsgivare else 0
    return count
