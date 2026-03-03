"""Spindeln — FastAPI orchestrator + WebSocket live progress + MCP server."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import settings
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


# ── Profile ──────────────────────────────────────────────────────────────────

@app.get("/api/profile/{person_id}")
async def get_profile(person_id: str):
    """Get assembled person profile from graph."""
    # Check active sessions first
    for s in sessions.values():
        if s.person and s.person.id == person_id:
            return s.person.model_dump()

    # Search HiveMindDB
    entity = await hivemind.find_entity(person_id)
    if entity:
        return entity
    return {"error": "Person not found"}, 404


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


# ── Graph ─────────────────────────────────────────────────────────────────────

@app.post("/api/graph")
async def graph_traverse(req: GraphRequest):
    """Traverse the knowledge graph from an entity."""
    try:
        entity_id = int(req.entity_id)
    except ValueError:
        # Try finding by name
        entity = await hivemind.find_entity(req.entity_id)
        if not entity:
            return {"error": "Entity not found"}, 404
        entity_id = entity["id"]

    nodes = await hivemind.traverse(entity_id, depth=req.depth)
    return {"nodes": nodes, "root_id": entity_id}


# ── Timeline ─────────────────────────────────────────────────────────────────

@app.get("/api/timeline/{person_id}")
async def get_timeline(person_id: str):
    """Get chronological events for a person."""
    # Find person in sessions
    for s in sessions.values():
        if s.person and s.person.id == person_id:
            return _build_timeline(s.person)

    return {"events": []}


def _build_timeline(person: Person) -> dict:
    """Build a timeline from a Person's data."""
    events: list[dict] = []

    for inc in person.inkomst:
        events.append(TimelineEvent(
            datum=datetime(inc.ar, 12, 31).date(),
            titel=f"Deklarerad inkomst: {inc.belopp:,} kr",
            source="ratsit", category="financial",
        ).model_dump())

    for remark in person.betalningsanmarkningar:
        if remark.datum:
            events.append(TimelineEvent(
                datum=remark.datum,
                titel=f"Betalningsanmärkning: {remark.typ}",
                beskrivning=f"Belopp: {remark.belopp:,} kr" if remark.belopp else "",
                source="ratsit", category="financial",
            ).model_dump())

    for news in person.news_mentions:
        if news.datum:
            events.append(TimelineEvent(
                datum=news.datum,
                titel=news.title,
                beskrivning=news.snippet,
                source="news", category="news",
                url=news.url,
            ).model_dump())

    for breach in person.breaches:
        if breach.breach_date:
            events.append(TimelineEvent(
                datum=breach.breach_date,
                titel=f"Dataläcka: {breach.breach_name}",
                beskrivning=f"Exponerad data: {', '.join(breach.exposed_data)}",
                source=breach.source, category="breach",
            ).model_dump())

    events.sort(key=lambda e: e.get("datum", ""), reverse=True)
    return {"events": events}


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
