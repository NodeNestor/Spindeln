"""Spindeln — FastAPI orchestrator + WebSocket live progress + MCP server."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
import re
from datetime import datetime, date as date_type

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import httpx

from src.config import settings, get_runtime_config, update_runtime_config
from src.models import (
    InvestigateRequest, InvestigationSession, InvestigationStatus,
    Person, ProgressEvent, SearchRequest, SearchResult, GraphRequest,
    TimelineEvent,
)
from src.investigate import run_investigation
from src.storage.client import HiveMindClient

logger = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────────────

sessions: dict[str, InvestigationSession] = {}
ws_clients: set[WebSocket] = set()
hivemind = HiveMindClient()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logger.info("Spindeln starting on %s:%d", settings.host, settings.port)
    yield
    await hivemind.close()
    logger.info("Spindeln shutdown")


app = FastAPI(
    title="Spindeln",
    description="Swedish Person Intelligence Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket Broadcast ──────────────────────────────────────────────────────

async def broadcast_progress(event: ProgressEvent):
    """Send progress event to all connected WebSocket clients."""
    data = event.model_dump_json()
    dead: list[WebSocket] = []
    for ws in ws_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive
    except WebSocketDisconnect:
        ws_clients.discard(ws)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    hive_ok = await hivemind.health()
    return {
        "status": "ok",
        "hiveminddb": "ok" if hive_ok else "unavailable",
        "version": "0.1.0",
    }


# ── Investigation ────────────────────────────────────────────────────────────

@app.post("/api/investigate")
async def investigate(req: InvestigateRequest):
    """Start a full investigation. Returns session_id immediately, streams progress via WS."""
    session = InvestigationSession(
        query=req.query,
        started_at=datetime.utcnow(),
        status=InvestigationStatus.RUNNING,
    )
    sessions[session.id] = session

    # Run in background
    asyncio.create_task(_run_investigation(session, req))

    return {"session_id": session.id, "status": session.status.value}


async def _run_investigation(session: InvestigationSession, req: InvestigateRequest):
    try:
        person = await run_investigation(
            query=req.query,
            location=req.location,
            session=session,
            progress_callback=broadcast_progress,
            hivemind=hivemind,
        )
        session.person = person
        session.status = InvestigationStatus.COMPLETE
        session.finished_at = datetime.utcnow()
    except Exception as e:
        logger.exception("Investigation failed: %s", e)
        session.status = InvestigationStatus.FAILED
        session.error = str(e)
        session.finished_at = datetime.utcnow()


@app.get("/api/investigate/{session_id}")
async def get_investigation(session_id: str):
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}, 404
    return session.model_dump()


@app.get("/api/sessions")
async def list_sessions():
    return [
        {
            "id": s.id,
            "query": s.query,
            "status": s.status.value,
            "phase": s.current_phase.value,
            "facts": s.facts_discovered,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        }
        for s in sessions.values()
    ]


# ── Stats (Dashboard) ────────────────────────────────────────────────────────

@app.get("/api/stats")
async def stats():
    """Aggregate stats for the dashboard."""
    persons = set()
    for s in sessions.values():
        if s.person:
            persons.add(s.person.id)
    running = sum(1 for s in sessions.values() if s.status == InvestigationStatus.RUNNING)
    return {
        "total_persons": len(persons),
        "total_investigations": len(sessions),
        "active_agents": running,
    }


@app.get("/api/investigations/recent")
async def recent_investigations():
    """Return recent investigations for the dashboard."""
    ordered = sorted(
        sessions.values(),
        key=lambda s: s.started_at or datetime.min,
        reverse=True,
    )[:20]
    return [
        {
            "id": s.id,
            "target": s.query,
            "status": "running" if s.status == InvestigationStatus.RUNNING
                      else "completed" if s.status == InvestigationStatus.COMPLETE
                      else "failed",
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "total_facts": s.facts_discovered,
            "person_id": s.person.id if s.person else None,
        }
        for s in ordered
    ]


@app.get("/api/investigate/{session_id}/report")
async def get_report(session_id: str):
    """Get the synthesis report for a completed investigation."""
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}, 404
    return {"report": session.report, "person_id": session.person.id if session.person else None}


# ── Profile ──────────────────────────────────────────────────────────────────

async def _resolve_person(person_id: str) -> dict | None:
    """Find person by id — checks sessions first, then HiveMindDB."""
    for s in sessions.values():
        if s.person and s.person.id == person_id:
            return s.person.model_dump()
    # Also check by session id (frontend may pass session id)
    if person_id in sessions and sessions[person_id].person:
        return sessions[person_id].person.model_dump()
    entity = await hivemind.find_entity(person_id)
    return entity


@app.get("/api/profile/{person_id}")
async def get_profile(person_id: str):
    """Get assembled person profile from graph."""
    data = await _resolve_person(person_id)
    if data:
        return data
    return {"error": "Person not found"}, 404


@app.get("/api/persons/{person_id}")
async def get_person(person_id: str):
    """Return person data transformed for the frontend profile store."""
    data = await _resolve_person(person_id)
    if not data:
        return {"error": "Person not found"}, 404
    result = _transform_person_for_frontend(data)
    # Attach report if available from session
    for s in sessions.values():
        if s.person and (s.person.id == person_id or s.id == person_id):
            if s.report:
                result["report"] = s.report
            break
    return result


def _transform_person_for_frontend(p: dict) -> dict:
    """Map backend Person model (Swedish fields) to frontend PersonProfile shape."""
    adress = p.get("adress") or {}
    inkomst = p.get("inkomst") or []
    latest_income = max(inkomst, key=lambda i: i.get("ar", 0)) if inkomst else {}

    companies = [
        {
            "company_name": c.get("foretag_namn", ""),
            "org_number": c.get("org_nummer", ""),
            "role": c.get("roll", ""),
            "since": c.get("fran"),
        }
        for c in (p.get("foretag") or [])
    ]

    social_profiles = [
        {
            "platform": s.get("platform", ""),
            "username": s.get("username", ""),
            "url": s.get("url", ""),
            "verified": s.get("verified", False),
        }
        for s in (p.get("social_media") or [])
    ]

    breaches = [
        {
            "breach_name": b.get("breach_name", ""),
            "date": b.get("breach_date"),
            "exposed_data": b.get("exposed_data", []),
            "source": b.get("source", ""),
        }
        for b in (p.get("breaches") or [])
    ]

    connections = []
    for f in (p.get("familj") or []):
        connections.append({
            "id": f.get("person_id") or f.get("person_namn", ""),
            "name": f.get("person_namn", ""),
            "type": "person",
            "relationship": f.get("relation", ""),
        })

    # Add news publications as company connections
    pub_counts: dict[str, int] = {}
    for nm in (p.get("news_mentions") or []):
        pub = nm.get("publication") or ""
        if pub:
            pub_counts[pub] = pub_counts.get(pub, 0) + 1
    for pub, count in pub_counts.items():
        connections.append({
            "id": f"pub_{pub}",
            "name": pub,
            "type": "company",
            "relationship": f"omnämnd i {count} {'artiklar' if count > 1 else 'artikel'}",
        })

    # Add companies as connections
    for c in (p.get("foretag") or []):
        name = c.get("foretag_namn", "")
        if name:
            connections.append({
                "id": f"co_{name}",
                "name": name,
                "type": "company",
                "relationship": c.get("roll", "koppling"),
            })

    # Build facts — prefer sourced_facts (DeepResearch-style) if available
    facts = []
    sourced = p.get("sourced_facts") or []
    if sourced:
        for sf in sourced:
            facts.append({
                "id": sf.get("source_url", "") or sf.get("content", "")[:40],
                "content": sf.get("content", ""),
                "category": sf.get("category", "general"),
                "source": sf.get("source_type", ""),
                "confidence": sf.get("confidence", 0.5),
                "timestamp": sf.get("discovered_at") or "",
                "quality_score": sf.get("quality_score", 5),
                "source_url": sf.get("source_url", ""),
                "source_title": sf.get("source_title", ""),
            })

    # Also include facts from legacy mentions
    for wm in (p.get("web_mentions") or []):
        facts.append({
            "id": wm.get("url", ""),
            "content": f"{wm.get('title', '')} — {wm.get('snippet', '')}",
            "category": wm.get("source_type", "web"),
            "source": wm.get("source_type", "web"),
            "confidence": 0.7,
            "timestamp": wm.get("datum") or "",
        })
    for nm in (p.get("news_mentions") or []):
        facts.append({
            "id": nm.get("url", ""),
            "content": f"{nm.get('title', '')} — {nm.get('snippet', '')}",
            "category": "news",
            "source": nm.get("publication", "news"),
            "confidence": 0.8,
            "timestamp": nm.get("datum") or "",
        })
    for br in (p.get("breaches") or []):
        facts.append({
            "id": br.get("breach_name", ""),
            "content": f"Breach: {br.get('breach_name', '')} — exposed: {', '.join(br.get('exposed_data', []))}",
            "category": "breach",
            "source": br.get("source", ""),
            "confidence": 0.9,
            "timestamp": br.get("breach_date") or "",
        })

    # Category completeness (rough heuristic)
    news_mentions = p.get("news_mentions") or []
    web_mentions = p.get("web_mentions") or []
    cat = {}
    cat["identity"] = min(1.0, (0.3 if p.get("personnummer") else 0) + (0.3 if adress else 0) + (0.2 if p.get("fodelsedatum") else 0) + 0.2)
    cat["financial"] = min(1.0, len(inkomst) * 0.2 + len(p.get("betalningsanmarkningar") or []) * 0.3)
    cat["professional"] = min(1.0, len(companies) * 0.3)
    cat["social"] = min(1.0, len(social_profiles) * 0.2)
    cat["digital"] = min(1.0, len(breaches) * 0.3 + len(web_mentions) * 0.1)
    cat["news"] = min(1.0, len(news_mentions) * 0.1)
    cat["connections"] = min(1.0, len(connections) * 0.15)

    return {
        "id": p.get("id", ""),
        "name": p.get("namn", "Unknown"),
        "age": None,
        "date_of_birth": p.get("fodelsedatum"),
        "personnummer": p.get("personnummer"),
        "address": adress.get("gatuadress", ""),
        "city": adress.get("ort", ""),
        "postal_code": adress.get("postnummer", ""),
        "phone": None,
        "email": None,
        "photo_url": None,
        "facts": facts,
        "connections": connections,
        "companies": companies,
        "social_profiles": social_profiles,
        "breaches": breaches,
        "financial": {
            "income": latest_income.get("belopp"),
            "tax": (max(p.get("skatt") or [{"belopp": None}], key=lambda t: t.get("ar", 0))).get("belopp") if p.get("skatt") else None,
            "payment_remarks": len(p.get("betalningsanmarkningar") or []) > 0,
            "remark_count": len(p.get("betalningsanmarkningar") or []),
            "income_history": [{"year": i["ar"], "amount": i["belopp"]} for i in inkomst],
        },
        "category_completeness": cat,
        "total_facts": len(facts),
        "last_updated": p.get("last_updated") or "",
    }


# ── Search ────────────────────────────────────────────────────────────────────

@app.post("/api/search")
async def search_people(req: SearchRequest):
    """Search for people across HiveMindDB."""
    results = await hivemind.search_memories(
        query=req.query,
        limit=req.limit,
        tags=["person"] + ([req.category] if req.category else []),
        include_graph=True,
    )
    return {"results": results, "count": len(results)}


@app.get("/api/search")
async def search_people_get(q: str = "", category: str = "", limit: int = 20):
    """GET search — used by frontend Search page."""
    if not q.strip():
        return {"results": [], "count": 0}
    results = await hivemind.search_memories(
        query=q.strip(),
        limit=limit,
        tags=["person"] + ([category] if category else []),
        include_graph=True,
    )
    return {"results": results, "count": len(results)}


# ── Graph ─────────────────────────────────────────────────────────────────────

@app.post("/api/graph")
async def graph_traverse(req: GraphRequest):
    """Traverse the knowledge graph from an entity."""
    try:
        entity_id = int(req.entity_id)
    except ValueError:
        entity = await hivemind.find_entity(req.entity_id)
        if not entity:
            return {"error": "Entity not found"}, 404
        entity_id = entity["id"]

    nodes = await hivemind.traverse(entity_id, depth=req.depth)
    return {"nodes": nodes, "root_id": entity_id}


@app.get("/api/persons/{person_id}/graph")
async def get_person_graph(person_id: str, depth: int = 2):
    """GET graph for a person — builds graph from person data."""
    person_data = await _resolve_person(person_id)
    if not person_data:
        return {"nodes": [], "links": [], "root_id": person_id}
    return _build_person_graph(person_data, person_id)


def _build_person_graph(p: dict, person_id: str) -> dict:
    """Build a graph from person data — nodes + links for the frontend."""
    nodes = []
    links = []
    seen_ids = set()

    # Center node: the person
    person_node_id = person_id
    nodes.append({
        "id": person_node_id,
        "name": p.get("namn", "Unknown"),
        "type": "person",
        "val": 10,
    })
    seen_ids.add(person_node_id)

    def _add_node(nid: str, name: str, ntype: str, link_label: str, val: int = 5):
        if nid not in seen_ids:
            nodes.append({"id": nid, "name": name, "type": ntype, "val": val})
            seen_ids.add(nid)
        links.append({"source": person_node_id, "target": nid, "label": link_label})

    # Address
    adress = p.get("adress") or {}
    if adress.get("ort"):
        addr_str = adress.get("gatuadress", "")
        ort = adress["ort"]
        _add_node(f"addr_{ort}", f"{addr_str}, {ort}" if addr_str else ort, "address", "bor i")

    # Companies
    for c in (p.get("foretag") or []):
        name = c.get("foretag_namn", "")
        if name:
            _add_node(f"co_{name}", name, "company", c.get("roll", "koppling"))

    # Family
    for f in (p.get("familj") or []):
        name = f.get("person_namn", "")
        if name:
            _add_node(f"fam_{name}", name, "person", f.get("relation", "familj"), val=7)

    # News publications (group by publication)
    pubs: dict[str, int] = {}
    for nm in (p.get("news_mentions") or []):
        pub = nm.get("publication") or ""
        if pub:
            pubs[pub] = pubs.get(pub, 0) + 1
    for pub, count in pubs.items():
        _add_node(f"pub_{pub}", pub, "company", f"{count} artiklar", val=4 + min(count, 6))

    # Web mentions (group by domain)
    domains: dict[str, int] = {}
    for wm in (p.get("web_mentions") or []):
        url = wm.get("url", "")
        if url:
            from urllib.parse import urlparse
            try:
                domain = urlparse(url).netloc
                if domain:
                    domains[domain] = domains.get(domain, 0) + 1
            except Exception:
                pass
    for domain, count in domains.items():
        _add_node(f"web_{domain}", domain, "email", f"{count} omnämnanden", val=3 + min(count, 4))

    # Social media
    for s in (p.get("social_media") or []):
        platform = s.get("platform", "")
        username = s.get("username", "")
        if platform:
            _add_node(f"social_{platform}", f"{platform}: {username}", "email", "profil")

    # Breaches
    for b in (p.get("breaches") or []):
        name = b.get("breach_name", "")
        if name:
            _add_node(f"breach_{name}", name, "phone", "dataläcka")

    # ── Entities & relationships from sourced_facts ───────────────────
    entity_type_map = {
        "person": "person", "company": "company", "organization": "company",
        "address": "address", "school": "company", "university": "company",
    }
    # Collect all entities from all facts
    for sf in (p.get("sourced_facts") or []):
        for ent in (sf.get("entities") or []):
            if isinstance(ent, str):
                ent_name = ent
                ent_type = "company"
            elif isinstance(ent, dict):
                ent_name = ent.get("name", "")
                ent_type = entity_type_map.get(ent.get("type", "").lower(), "company")
            else:
                continue
            if not ent_name or ent_name.lower() == p.get("namn", "").lower():
                continue
            nid = f"ent_{ent_name}"
            if nid not in seen_ids:
                nodes.append({"id": nid, "name": ent_name, "type": ent_type, "val": 4})
                seen_ids.add(nid)

        # Create links from relationships
        for rel in (sf.get("relationships") or []):
            if not isinstance(rel, dict):
                continue
            src = rel.get("source", "")
            tgt = rel.get("target", "")
            rel_type = rel.get("type", "koppling")
            if not src or not tgt:
                continue
            # Map source/target to node IDs
            src_id = person_node_id if src.lower() == p.get("namn", "").lower() else f"ent_{src}"
            tgt_id = person_node_id if tgt.lower() == p.get("namn", "").lower() else f"ent_{tgt}"
            if src_id in seen_ids and tgt_id in seen_ids:
                links.append({"source": src_id, "target": tgt_id, "label": rel_type})

    return {"nodes": nodes, "links": links, "root_id": person_node_id}


# ── Timeline ─────────────────────────────────────────────────────────────────

@app.get("/api/timeline/{person_id}")
async def get_timeline(person_id: str):
    """Get chronological events for a person."""
    for s in sessions.values():
        if s.person and s.person.id == person_id:
            return _build_timeline(s.person)
    return {"events": []}


@app.get("/api/persons/{person_id}/timeline")
async def get_person_timeline(person_id: str):
    """Alias for /api/timeline/{id} — used by frontend Timeline page."""
    for s in sessions.values():
        if s.person and s.person.id == person_id:
            return _build_timeline(s.person)
    return {"events": []}


_SWEDISH_MONTHS = {
    "jan": 1, "januari": 1, "feb": 2, "februari": 2, "mar": 3, "mars": 3,
    "apr": 4, "april": 4, "maj": 5, "jun": 6, "juni": 6, "jul": 7, "juli": 7,
    "aug": 8, "augusti": 8, "sep": 9, "september": 9, "okt": 10, "oktober": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _extract_date(text: str) -> date_type | None:
    """Try to extract a date from free-text fact content.

    Supports: ISO (2024-05-15), Swedish (15 maj 2024), year-only (2023).
    """
    # ISO date: 2024-05-15
    m = re.search(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', text)
    if m:
        try:
            return date_type(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # Swedish date: 15 maj 2024
    m = re.search(r'\b(\d{1,2})\s+(' + '|'.join(_SWEDISH_MONTHS) + r')\s+(\d{4})\b', text, re.IGNORECASE)
    if m:
        try:
            return date_type(int(m.group(3)), _SWEDISH_MONTHS[m.group(2).lower()], int(m.group(1)))
        except (ValueError, KeyError):
            pass

    # Year-only: (2023) or standalone year in context like "since 2023"
    m = re.search(r'\b(20[12]\d)\b', text)
    if m:
        try:
            return date_type(int(m.group(1)), 1, 1)
        except ValueError:
            pass

    return None


def _build_timeline(person: Person) -> dict:
    """Build a timeline from a Person's data."""
    events: list[dict] = []
    today = date_type.today()

    from src.models import SourceType
    for inc in person.inkomst:
        events.append(TimelineEvent(
            datum=datetime(inc.ar, 12, 31).date(),
            titel=f"Deklarerad inkomst: {inc.belopp:,} kr",
            source=SourceType.RATSIT, category="financial",
        ).model_dump())

    for remark in person.betalningsanmarkningar:
        events.append(TimelineEvent(
            datum=remark.datum or today,
            titel=f"Betalningsanmärkning: {remark.typ}",
            beskrivning=f"Belopp: {remark.belopp:,} kr" if remark.belopp else "",
            source=SourceType.RATSIT, category="financial",
        ).model_dump())

    for news in person.news_mentions:
        events.append(TimelineEvent(
            datum=news.datum or today,
            titel=f"[{news.publication or 'Nyhet'}] {news.title or 'Nyhetsartikel'}",
            beskrivning=news.snippet or "",
            source=SourceType.NEWS, category="news",
            url=news.url,
        ).model_dump())

    for breach in person.breaches:
        events.append(TimelineEvent(
            datum=breach.breach_date or today,
            titel=f"Dataläcka: {breach.breach_name}",
            beskrivning=f"Exponerad data: {', '.join(breach.exposed_data)}",
            source=SourceType.HIBP, category="breach",
        ).model_dump())

    for wm in person.web_mentions:
        events.append(TimelineEvent(
            datum=today,
            titel=wm.title or "Webbomnämnande",
            beskrivning=wm.snippet or "",
            source=SourceType.WEB_SEARCH, category="personal",
            url=wm.url,
        ).model_dump())

    # ── Sourced facts → timeline events ─────────────────────────────────
    for fact in person.sourced_facts:
        extracted = _extract_date(fact.content)
        if not extracted and fact.discovered_at:
            extracted = fact.discovered_at.date()
        if not extracted:
            extracted = today

        # Map source_type string to SourceType enum
        try:
            src = SourceType(fact.source_type) if fact.source_type else SourceType.WEB_SEARCH
        except ValueError:
            src = SourceType.WEB_SEARCH

        events.append(TimelineEvent(
            datum=extracted,
            titel=fact.content[:120],
            beskrivning=f"Källa: {fact.source_title}" if fact.source_title else "",
            source=src,
            category=fact.category or "general",
            url=fact.source_url,
        ).model_dump())

    events.sort(key=lambda e: str(e.get("datum", "")), reverse=True)

    # Transform Swedish field names → English for frontend
    fe_events = []
    for i, ev in enumerate(events):
        fe_events.append({
            "id": f"evt_{i}",
            "date": str(ev.get("datum", "")),
            "title": ev.get("titel", ""),
            "description": ev.get("beskrivning", ""),
            "category": ev.get("category", "personal"),
            "source": ev.get("source", ""),
            "details": {"url": ev["url"]} if ev.get("url") else None,
        })

    return {"events": fe_events, "person_name": person.namn}


# ── Config ────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Return all editable runtime config fields (API keys masked)."""
    return get_runtime_config()


@app.put("/api/config")
async def put_config(body: dict):
    """Partial update of runtime config fields. Persists to disk."""
    updated = update_runtime_config(body)
    return updated


@app.post("/api/test-endpoint")
async def test_endpoint(body: dict):
    """Proxy endpoint test — tries to reach a URL and reports ok/fail.

    Accepts {"url": "http://..."}.  Backend acts as proxy so the frontend
    doesn't hit CORS issues when testing third-party service URLs.
    """
    url = body.get("url", "")
    if not url:
        return {"ok": False, "error": "No URL provided"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return {"ok": resp.status_code < 500, "status": resp.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Agents Info ───────────────────────────────────────────────────────────────

@app.get("/api/agents")
async def list_agents():
    from src.agents.registry import list_agents as _list
    return _list()


# ── Static SPA ────────────────────────────────────────────────────────────────

# Mount frontend static files (built React app)
try:
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
except Exception:
    pass  # No static dir in dev mode


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    import uvicorn
    if len(sys.argv) > 1 and sys.argv[1] == "mcp":
        from src.mcp.server import run_mcp
        run_mcp()
    else:
        uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
