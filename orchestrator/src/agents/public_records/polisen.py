"""Polisen agent — queries the Swedish Police public events API.

Searches for police events (crimes, accidents, etc.) near a person's
known address to provide local safety context.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType, WebMention

logger = logging.getLogger(__name__)

POLISEN_API = "https://polisen.se/api/events"


@register_agent("polisen")
class PolisenAgent(BaseAgent):
    """Queries Polisen API for police events near a person's address."""

    @property
    def name(self) -> str:
        return "polisen"

    @property
    def source_type(self) -> SourceType:
        return SourceType.POLISEN

    @property
    def description(self) -> str:
        return "Polisen — police events near person's address"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", "Querying Polisen events API")

        # Need an address to search by location
        location = self._get_location(person)
        if not location:
            await self._report_progress("complete", "No address available for Polisen search")
            return person

        # Step 1: Fetch police events for the location
        events = await self._fetch_events(location)
        if not events:
            await self._report_progress("complete", f"No police events found near {location}")
            return person

        # Step 2: Filter events relevant to person's area
        relevant = self._filter_local_events(events, location)
        facts = 0

        for event in relevant[:10]:  # Cap at 10 most relevant events
            event_date = None
            if event.get("datetime"):
                try:
                    event_date = date.fromisoformat(event["datetime"][:10])
                except (ValueError, TypeError):
                    pass

            person.web_mentions.append(WebMention(
                url=event.get("url", POLISEN_API),
                title=event.get("name", "Polisen event"),
                snippet=event.get("summary", ""),
                datum=event_date,
                source_type="polisen",
            ))
            facts += 1

        person.sources.append(self.make_source_ref(POLISEN_API))
        if facts > 0:
            await self.store_person_fact(
                person,
                f"Polisen: {facts} events found near {location}",
                tags=["polisen", "public_records", "events"],
            )

        await self._report_progress("complete", f"Found {facts} local events", facts_found=facts)
        return person

    @staticmethod
    def _get_location(person: Person) -> str:
        """Extract best location string from person data."""
        if person.adress:
            if person.adress.ort:
                return person.adress.ort
            if person.adress.kommun:
                return person.adress.kommun
        return ""

    async def _fetch_events(self, location: str) -> list[dict]:
        """Fetch events from Polisen API filtered by location name."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(
                    POLISEN_API,
                    params={"locationname": location},
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.warning("Polisen API request failed: %s", e)
                return []

    @staticmethod
    def _filter_local_events(events: list[dict], location: str) -> list[dict]:
        """Filter events that mention the person's location."""
        location_lower = location.lower()
        relevant = []
        for event in events:
            loc = event.get("location", {})
            name = loc.get("name", "").lower() if isinstance(loc, dict) else ""
            summary = event.get("summary", "").lower()
            if location_lower in name or location_lower in summary:
                relevant.append(event)
        return relevant or events[:5]  # Fallback to first 5 if no exact match
