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
from src.scraper.extractors import deduplicate_facts
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

    # ── Phase 3.6: Fact Validation ─────────────────────────────────────────
    await _progress(InvestigationPhase.FACT_VALIDATION, status="running",
                    message="Validating facts against identity profile")

    if person.sourced_facts:
        try:
            from src.fact_validator import validate_facts, detect_contradictions, validate_structured_fields
            before_val = len(person.sourced_facts)
            person.sourced_facts = await validate_facts(person.sourced_facts, person)
            contradictions = detect_contradictions(person.sourced_facts, person)
            logger.info("Fact validation: %d → %d facts, %d contradictions",
                       before_val, len(person.sourced_facts), len(contradictions))

            # Validate structured fields (company roles, social profiles)
            person = await validate_structured_fields(person)
        except Exception as e:
            logger.warning("Fact validation failed, continuing: %s", e)

    await _progress(InvestigationPhase.FACT_VALIDATION, status="complete",
                    facts=session.facts_discovered)

    # ── Phase 3.7: Discovery Loop ──────────────────────────────────────────
    await _progress(InvestigationPhase.DISCOVERY_LOOP, status="running",
                    message="Running iterative discovery loop")

    try:
        person = await _run_discovery_loop(person, hivemind, session, _progress)
    except Exception as e:
        logger.warning("Discovery loop failed, continuing: %s", e)

    await _progress(InvestigationPhase.DISCOVERY_LOOP, status="complete",
                    facts=session.facts_discovered)

    # ── Phase 4: Graph Construction + Timeline ─────────────────────────────
    await _progress(InvestigationPhase.GRAPH_CONSTRUCTION, status="running",
                    message="Building knowledge graph")

    analysis_agents = get_agents_by_category("analysis")
    for agent in analysis_agents:
        if "graph" in agent.name:
            person = await _run_agent(agent, person, hivemind, progress_callback, session)

    # Run TimelineBuilder after graph construction
    for agent in analysis_agents:
        if "timeline" in agent.name:
            person = await _run_agent(agent, person, hivemind, progress_callback, session)

    await _progress(InvestigationPhase.GRAPH_CONSTRUCTION, status="complete")

    # ── Fact Deduplication ────────────────────────────────────────────────
    if person.sourced_facts:
        before = len(person.sourced_facts)
        person.sourced_facts = deduplicate_facts(person.sourced_facts)
        logger.info("Deduplication: %d → %d facts for %s",
                     before, len(person.sourced_facts), person.namn)

    # ── Phase 4.5: Report Synthesis ──────────────────────────────────────
    await _progress(InvestigationPhase.REPORT_SYNTHESIS, status="running",
                    message="Generating intelligence report")

    for agent in analysis_agents:
        if "profile_synth" in agent.name:
            person = await _run_agent(agent, person, hivemind, progress_callback, session)

    # Use the LLM synthesis result as the report if available, fallback to raw data
    if hasattr(person, '_synth_report') and person._synth_report:
        session.report = person._synth_report
    else:
        session.report = _build_report(person)

    await _progress(InvestigationPhase.REPORT_SYNTHESIS, status="complete",
                    message="Report synthesis complete")

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
        "sources", "adress_historik", "sourced_facts",
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


def _build_report(person: Person) -> dict:
    """Build a report dict from all gathered person data."""
    news = [
        {"title": n.title, "publication": n.publication or "", "snippet": n.snippet or ""}
        for n in person.news_mentions[:10]
    ]
    web = [
        {"title": w.title or "", "url": w.url, "snippet": w.snippet or ""}
        for w in person.web_mentions[:10]
    ]
    companies = [
        {"name": c.foretag_namn, "role": c.roll.value if hasattr(c.roll, "value") else str(c.roll)}
        for c in person.foretag
    ]
    return {
        "name": person.namn,
        "personnummer": person.personnummer,
        "address": str(person.adress) if person.adress else None,
        "employer": person.arbetsgivare,
        "news_mentions": news,
        "web_mentions": web,
        "companies": companies,
        "social_profiles": [
            {"platform": s.platform, "username": s.username or "", "url": s.url}
            for s in person.social_media
        ],
        "breaches": [
            {"name": b.breach_name, "severity": b.severity}
            for b in person.breaches
        ],
        "total_facts": _count_facts(person),
        "sources_count": len(person.sources),
    }


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


# ── Discovery Loop ────────────────────────────────────────────────────────────

import re as _re

_EMAIL_RE = _re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
_HANDLE_RE = _re.compile(r'@([\w.]{3,30})')


def _collect_identifiers(person: Person) -> set[str]:
    """Collect all known identifiers from person data for re-search."""
    ids: set[str] = set()

    # Emails and handles from social profiles
    for sp in person.social_media:
        if sp.username:
            ids.add(sp.username)

    # From sourced_facts
    for fact in person.sourced_facts:
        for email in _EMAIL_RE.findall(fact.content):
            ids.add(email)
        for handle in _HANDLE_RE.findall(fact.content):
            ids.add(handle)

    # From breach data
    for breach in person.breaches:
        for exp in breach.exposed_data:
            if "@" in exp:
                ids.add(exp)

    # Company names
    for co in person.foretag:
        if co.foretag_namn:
            ids.add(co.foretag_namn)

    return ids


async def _run_discovery_loop(
    person: Person,
    hivemind: HiveMindClient,
    session: InvestigationSession,
    progress_fn,
) -> Person:
    """Iterative discovery: use found identifiers to search for more data.

    Searches with emails, handles, and company names found during earlier phases.
    Stops when no new identifiers are found or max iterations reached.
    """
    from src.scraper import searxng_client, crawl4ai_client
    from src.scraper.extractors import deduplicate_facts
    from src.agents.base import BaseAgent
    from src.models import SourcedFact, SourceType

    max_iters = settings.max_discovery_iterations
    seen_identifiers: set[str] = {person.namn.lower()}
    # Seed with already-known identifiers so we don't re-search them
    for ident in _collect_identifiers(person):
        seen_identifiers.add(ident.lower())

    for iteration in range(max_iters):
        # Collect current identifiers
        current_ids = _collect_identifiers(person)
        new_ids = {i for i in current_ids if i.lower() not in seen_identifiers}

        if not new_ids:
            logger.info("Discovery loop: converged after %d iterations (no new identifiers)", iteration)
            break

        logger.info("Discovery loop iteration %d: %d new identifiers: %s",
                    iteration + 1, len(new_ids), list(new_ids)[:5])

        await progress_fn(
            InvestigationPhase.DISCOVERY_LOOP, status="running",
            message=f"Discovery iteration {iteration + 1}: searching {len(new_ids)} new identifiers",
        )

        # Mark these as seen
        for ident in new_ids:
            seen_identifiers.add(ident.lower())

        # Search with each new identifier (limit to 5 per iteration)
        search_queries = []
        for ident in list(new_ids)[:5]:
            if "@" in ident and "." in ident:
                # Email — search directly
                search_queries.append(f'"{ident}"')
            elif ident.startswith("@") or (len(ident) > 3 and not " " in ident):
                # Handle — search with person name context
                search_queries.append(f'"{ident}" {person.namn}')
            else:
                # Company or other — search with context
                search_queries.append(f'"{ident}" {person.namn}')

        new_facts_count = 0
        for query in search_queries:
            try:
                await asyncio.sleep(settings.searxng_delay_seconds)
                results = await searxng_client.search(query, max_results=3)
            except Exception as e:
                logger.debug("Discovery search failed for %s: %s", query, e)
                continue

            for result in results[:2]:
                try:
                    await asyncio.sleep(settings.scrape_delay_seconds)
                    scraped = await crawl4ai_client.scrape(result.url)
                except Exception:
                    continue

                if not scraped.get("success") or not scraped.get("markdown"):
                    continue

                # Use a temporary BaseAgent-like extraction
                from src.scraper.extractors import extract_page_facts as _extract

                # Build identity anchors
                anchors = {}
                if person.fodelsedatum:
                    anchors["birth_date"] = str(person.fodelsedatum)
                if person.adress and person.adress.gatuadress:
                    anchors["address"] = f"{person.adress.gatuadress}, {person.adress.ort or ''}"
                if person.personnummer:
                    anchors["personnummer"] = person.personnummer

                context_parts = []
                if person.adress and person.adress.ort:
                    context_parts.append(f"Location: {person.adress.ort}")
                if person.arbetsgivare:
                    context_parts.append(f"Employer: {person.arbetsgivare}")

                fact_result = await _extract(
                    scraped["markdown"], person.namn,
                    person_context=". ".join(context_parts),
                    source_url=result.url,
                    source_title=getattr(result, 'title', ''),
                    identity_anchors=anchors,
                )

                if not fact_result or not fact_result.get("relevant"):
                    continue

                quality = fact_result.get("quality", 0)
                if quality < 2:
                    continue

                for f in fact_result.get("facts", []):
                    fact = SourcedFact(
                        content=f.get("fact", ""),
                        confidence=f.get("confidence", 0.5),
                        source_url=result.url,
                        source_title=getattr(result, 'title', ''),
                        source_type=SourceType.WEB_SEARCH.value,
                        quality_score=quality,
                        entities=[e.get("name", "") for e in fact_result.get("entities", []) if isinstance(e, dict)],
                        relationships=[r for r in fact_result.get("relationships", []) if isinstance(r, dict)],
                        category=f.get("category") or "general",
                    )
                    if fact.content:
                        person.sourced_facts.append(fact)
                        new_facts_count += 1

        logger.info("Discovery loop iteration %d: found %d new facts", iteration + 1, new_facts_count)

        if new_facts_count == 0:
            logger.info("Discovery loop: no new facts in iteration %d, stopping", iteration + 1)
            break

    return person
