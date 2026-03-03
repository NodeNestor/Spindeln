"""HiveMindDB async REST client — stores entities, relationships, facts, and vectors."""

from __future__ import annotations

import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class HiveMindClient:
    """Async client for HiveMindDB REST API.

    Gracefully degrades: returns empty/None on connection errors.
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.hiveminddb_url).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Health ────────────────────────────────────────────────────────────

    async def health(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def status(self) -> dict:
        try:
            client = await self._get_client()
            resp = await client.get("/api/v1/status")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("HiveMindDB status check failed: %s", e)
            return {}

    # ── Memories (Facts) ──────────────────────────────────────────────────

    async def add_memory(self, content: str, agent_id: str = "spindeln",
                         tags: list[str] | None = None,
                         metadata: dict | None = None,
                         memory_type: str = "fact",
                         confidence: float = 1.0) -> dict | None:
        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/memories", json={
                "content": content,
                "memory_type": memory_type,
                "agent_id": agent_id,
                "tags": tags or [],
                "confidence": confidence,
                "metadata": metadata or {},
            })
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Failed to add memory: %s", e)
            return None

    async def add_memories_bulk(self, memories: list[dict]) -> dict | None:
        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/bulk/memories",
                                     json={"memories": memories})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Bulk memory add failed: %s", e)
            return None

    async def search_memories(self, query: str, limit: int = 20,
                              tags: list[str] | None = None,
                              include_graph: bool = False) -> list[dict]:
        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/search", json={
                "query": query,
                "limit": limit,
                "tags": tags or [],
                "include_graph": include_graph,
            })
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Memory search failed: %s", e)
            return []

    # ── Entities ──────────────────────────────────────────────────────────

    async def add_entity(self, name: str, entity_type: str,
                         description: str = "",
                         agent_id: str = "spindeln",
                         metadata: dict | None = None) -> int | None:
        """Create an entity, return its ID."""
        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/entities", json={
                "name": name,
                "entity_type": entity_type,
                "description": description,
                "agent_id": agent_id,
                "metadata": metadata or {},
            })
            resp.raise_for_status()
            data = resp.json()
            return data.get("id")
        except Exception as e:
            logger.warning("Failed to add entity '%s': %s", name, e)
            return None

    async def find_entity(self, name: str) -> dict | None:
        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/entities/find", json={"name": name})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Entity lookup failed for '%s': %s", name, e)
            return None

    async def get_entity(self, entity_id: int) -> dict | None:
        try:
            client = await self._get_client()
            resp = await client.get(f"/api/v1/entities/{entity_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Get entity failed: %s", e)
            return None

    async def get_entity_relationships(self, entity_id: int) -> list[dict]:
        try:
            client = await self._get_client()
            resp = await client.get(f"/api/v1/entities/{entity_id}/relationships")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Get relationships failed: %s", e)
            return []

    # ── Relationships ─────────────────────────────────────────────────────

    async def add_relationship(self, source_entity_id: int, target_entity_id: int,
                               relation_type: str, created_by: str = "spindeln",
                               description: str = "", weight: float = 1.0,
                               metadata: dict | None = None) -> dict | None:
        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/relationships", json={
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "relation_type": relation_type,
                "weight": weight,
                "description": description,
                "created_by": created_by,
                "metadata": metadata or {},
            })
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Failed to add relationship: %s", e)
            return None

    # ── Graph Traversal ───────────────────────────────────────────────────

    async def traverse(self, entity_id: int, depth: int = 2) -> list[dict]:
        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/graph/traverse", json={
                "entity_id": entity_id,
                "depth": depth,
            })
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Graph traversal failed: %s", e)
            return []

    # ── Bulk Search ───────────────────────────────────────────────────────

    async def search_bulk(self, queries: list[dict],
                          max_concurrent: int = 10) -> dict | None:
        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/search/bulk", json={
                "queries": queries,
                "max_concurrent": max_concurrent,
            })
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Bulk search failed: %s", e)
            return None
