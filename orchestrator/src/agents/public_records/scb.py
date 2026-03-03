"""SCB agent — queries Statistics Sweden (SCB) open data API.

Retrieves area demographics for a person's municipality (population, etc.).
"""

from __future__ import annotations

import logging

import httpx

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType, WebMention

logger = logging.getLogger(__name__)

SCB_API = "https://api.scb.se/OV0104/v1/doris/sv"
SCB_TABLE = f"{SCB_API}/BE/BE0101/BE0101A/BefolkningNy"


@register_agent("scb")
class SCBAgent(BaseAgent):
    """Queries SCB API for area demographics of a person's municipality."""

    @property
    def name(self) -> str:
        return "scb"

    @property
    def source_type(self) -> SourceType:
        return SourceType.SCB

    @property
    def description(self) -> str:
        return "SCB — area demographics for person's municipality"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", "Querying SCB for area demographics")

        kommun = person.adress.kommun or person.adress.ort if person.adress else ""
        if not kommun:
            await self._report_progress("complete", "No municipality for SCB lookup")
            return person

        stats = await self._fetch_stats(kommun)
        if not stats:
            await self._report_progress("complete", f"No SCB data for {kommun}")
            return person

        # Build summary from available fields
        parts = []
        if stats.get("population"):
            parts.append(f"Befolkning: {stats['population']}")
        if stats.get("median_income"):
            parts.append(f"Medianinkomst: {stats['median_income']} kr")

        if parts:
            summary = f"Kommun {kommun}: " + ", ".join(parts)
            person.web_mentions.append(WebMention(
                url=SCB_API, title=f"SCB demografi — {kommun}",
                snippet=summary, source_type="scb",
            ))
            await self.store_person_fact(
                person, summary,
                tags=["scb", "demographics", "public_records", kommun],
            )

        person.sources.append(self.make_source_ref(SCB_API))
        await self._report_progress("complete", f"Retrieved {len(parts)} fields", facts_found=len(parts))
        return person

    async def _fetch_stats(self, kommun: str) -> dict:
        """Fetch municipality statistics from SCB POST-based API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Get table metadata to build query
                resp = await client.get(SCB_TABLE)
                resp.raise_for_status()
                meta = resp.json()

                query_body = self._build_query(meta, kommun)
                if not query_body:
                    return {}

                resp = await client.post(SCB_TABLE, json=query_body)
                resp.raise_for_status()
                return self._parse_response(resp.json())
            except Exception as e:
                logger.warning("SCB API failed: %s", e)
                return {}

    @staticmethod
    def _build_query(meta: dict, kommun: str) -> dict | None:
        """Build SCB JSON-stat query for a municipality."""
        variables = meta.get("variables", [])
        if not variables:
            return None

        query: dict = {"query": [], "response": {"format": "json"}}
        for var in variables:
            code, values, texts = var.get("code", ""), var.get("values", []), var.get("valueTexts", [])
            if code.lower() in ("region", "kommun"):
                idx = next((i for i, t in enumerate(texts) if kommun.lower() in t.lower()), None)
                if idx is not None and idx < len(values):
                    query["query"].append({"code": code, "selection": {"filter": "item", "values": [values[idx]]}})
            elif code.lower() in ("tid", "year", "ar") and values:
                query["query"].append({"code": code, "selection": {"filter": "item", "values": [values[-1]]}})

        return query if query["query"] else None

    @staticmethod
    def _parse_response(data: dict) -> dict:
        """Parse SCB JSON-stat response into a simple dict."""
        result = {}
        for entry in data.get("data", []):
            vals = entry.get("values", [])
            if vals:
                try:
                    result["population"] = int(vals[0])
                except (ValueError, IndexError):
                    pass
        return result
