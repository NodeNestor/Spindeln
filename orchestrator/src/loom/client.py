"""Loom bridge — read-only SQLite client for querying Loom's temporal event store."""

from __future__ import annotations

import logging
import os

import aiosqlite

from src.config import settings
from src.models import Person, WebMention

logger = logging.getLogger(__name__)


class LoomBridge:
    """Read-only bridge to Loom's 71GB SQLite event database.

    Queries events matching a person's name, company names, or address.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.loom_db_path

    async def _connect(self) -> aiosqlite.Connection | None:
        if not os.path.exists(self.db_path):
            logger.warning("Loom DB not found at %s", self.db_path)
            return None
        conn = await aiosqlite.connect(self.db_path)
        await conn.execute("PRAGMA query_only = ON")
        return conn

    async def search_text(self, query: str, limit: int = 50) -> list[dict]:
        """Full-text search across Loom events."""
        conn = await self._connect()
        if not conn:
            return []

        try:
            rows = await conn.execute_fetchall(
                """
                SELECT id, timestamp, source, text
                FROM events
                WHERE text LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (f"%{query}%", limit),
            )
            return [
                {
                    "id": r[0],
                    "timestamp": r[1],
                    "source": r[2],
                    "text": r[3],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Loom text search failed: %s", e)
            return []
        finally:
            await conn.close()

    async def search_person(self, person: Person, limit: int = 100) -> list[dict]:
        """Search Loom for events related to a person.

        Searches by name, company names, and address.
        """
        queries = [person.namn]

        # Add company names
        for role in person.foretag:
            queries.append(role.foretag_namn)

        # Add city
        if person.adress and person.adress.ort:
            queries.append(f"{person.namn} {person.adress.ort}")

        all_events: list[dict] = []
        seen_ids: set[int] = set()

        for q in queries:
            events = await self.search_text(q, limit=limit // len(queries))
            for e in events:
                if e["id"] not in seen_ids:
                    all_events.append(e)
                    seen_ids.add(e["id"])

        # Sort by timestamp
        all_events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return all_events[:limit]

    async def get_time_range(self) -> tuple[str, str] | None:
        """Get the time range covered by the Loom database."""
        conn = await self._connect()
        if not conn:
            return None

        try:
            row = await conn.execute_fetchall(
                "SELECT MIN(timestamp), MAX(timestamp) FROM events"
            )
            if row and row[0][0]:
                return (row[0][0], row[0][1])
            return None
        except Exception as e:
            logger.error("Loom time range query failed: %s", e)
            return None
        finally:
            await conn.close()

    async def count(self) -> int:
        """Count total events in Loom."""
        conn = await self._connect()
        if not conn:
            return 0

        try:
            row = await conn.execute_fetchall("SELECT COUNT(*) FROM events")
            return row[0][0] if row else 0
        except Exception:
            return 0
        finally:
            await conn.close()
