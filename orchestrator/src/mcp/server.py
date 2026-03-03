"""MCP server — exposes Spindeln tools for Claude Code integration."""

from __future__ import annotations

import asyncio
import json
import logging

from mcp.server import Server
from mcp.server.stdio import run_server
from mcp.types import Tool, TextContent

from src.models import Person, InvestigationSession, InvestigationStatus
from src.investigate import run_investigation
from src.storage.client import HiveMindClient

logger = logging.getLogger(__name__)

server = Server("spindeln")
hivemind = HiveMindClient()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="investigate_person",
            description="Run full investigation swarm on a Swedish person. "
                        "Scrapes public records, social media, news, breach databases.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Person's name or personnummer"},
                    "location": {"type": "string", "description": "City/location hint (optional)"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="quick_lookup",
            description="Fast lookup — scrapes Ratsit/Hitta only for basic person data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Person's name"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="find_connections",
            description="Traverse knowledge graph to find connections to a person.",
            inputSchema={
                "type": "object",
                "properties": {
                    "person_name": {"type": "string", "description": "Person or entity name"},
                    "depth": {"type": "integer", "description": "Graph traversal depth (default 2)"},
                },
                "required": ["person_name"],
            },
        ),
        Tool(
            name="search_people",
            description="Semantic search across all indexed people.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "category": {
                        "type": "string",
                        "description": "Search category: identity, professional, financial, social, digital",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 20)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="check_breaches",
            description="Check if an email has been exposed in data breaches.",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Email address to check"},
                },
                "required": ["email"],
            },
        ),
        Tool(
            name="person_timeline",
            description="Get chronological events for a person.",
            inputSchema={
                "type": "object",
                "properties": {
                    "person_name": {"type": "string", "description": "Person name to look up"},
                },
                "required": ["person_name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "investigate_person":
            return await _investigate(arguments)
        elif name == "quick_lookup":
            return await _quick_lookup(arguments)
        elif name == "find_connections":
            return await _find_connections(arguments)
        elif name == "search_people":
            return await _search_people(arguments)
        elif name == "check_breaches":
            return await _check_breaches(arguments)
        elif name == "person_timeline":
            return await _person_timeline(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _investigate(args: dict) -> list[TextContent]:
    session = InvestigationSession(query=args["name"])
    person = await run_investigation(
        query=args["name"],
        location=args.get("location"),
        session=session,
        progress_callback=None,
        hivemind=hivemind,
    )
    return [TextContent(type="text", text=person.model_dump_json(indent=2))]


async def _quick_lookup(args: dict) -> list[TextContent]:
    from src.agents.registry import get_agent
    person = Person(namn=args["name"])
    try:
        agent = get_agent("ratsit")
        agent.hivemind = hivemind
        person = await agent.safe_run(person)
    except KeyError:
        pass
    try:
        agent = get_agent("hitta")
        agent.hivemind = hivemind
        person = await agent.safe_run(person)
    except KeyError:
        pass
    return [TextContent(type="text", text=person.model_dump_json(indent=2))]


async def _find_connections(args: dict) -> list[TextContent]:
    entity = await hivemind.find_entity(args["person_name"])
    if not entity:
        return [TextContent(type="text", text=f"Entity '{args['person_name']}' not found")]
    depth = args.get("depth", 2)
    nodes = await hivemind.traverse(entity["id"], depth=depth)
    return [TextContent(type="text", text=json.dumps(nodes, indent=2, default=str))]


async def _search_people(args: dict) -> list[TextContent]:
    tags = ["person"]
    if args.get("category"):
        tags.append(args["category"])
    results = await hivemind.search_memories(
        query=args["query"],
        limit=args.get("limit", 20),
        tags=tags,
        include_graph=True,
    )
    return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]


async def _check_breaches(args: dict) -> list[TextContent]:
    from src.agents.registry import get_agent
    person = Person(namn="breach_check")
    try:
        agent = get_agent("hibp")
        agent.hivemind = hivemind
        # Pass email via person metadata
        person = await agent.safe_run(person)
    except KeyError:
        pass
    return [TextContent(type="text", text=json.dumps(
        [b.model_dump() for b in person.breaches], indent=2, default=str
    ))]


async def _person_timeline(args: dict) -> list[TextContent]:
    results = await hivemind.search_memories(
        query=args["person_name"],
        limit=50,
        tags=["person"],
    )
    return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]


def run_mcp():
    """Run MCP server over stdio."""
    asyncio.run(run_server(server))
