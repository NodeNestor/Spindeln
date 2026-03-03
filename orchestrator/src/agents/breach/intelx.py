"""Intelligence X agent — searches dark web, paste sites, and leaked databases."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

import httpx

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.config import settings
from src.models import BreachRecord, Person, SourceType

logger = logging.getLogger(__name__)

INTELX_API = "https://2.intelx.io"
POLL_INTERVAL = 3
MAX_POLL_ATTEMPTS = 10


@register_agent("intelx")
class IntelXAgent(BaseAgent):
    """Searches Intelligence X for dark web / paste / leak exposure."""

    name = "intelx"
    source_type = SourceType.INTELX
    description = "Intelligence X dark web / leak search"

    async def run(self, person: Person) -> Person:
        if not settings.intelx_api_key:
            logger.warning("IntelX: No API key configured, skipping")
            return person

        # Build search terms from person data
        terms = self._build_search_terms(person)
        if not terms:
            logger.info("IntelX: No useful search terms for %s", person.namn)
            return person

        await self._report_progress("running", f"Searching IntelX for {person.namn}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"x-key": settings.intelx_api_key}

            for term in terms:
                records = await self._search_term(client, headers, term)
                for rec in records:
                    person.breaches.append(rec)
                    await self.store_person_fact(
                        person,
                        f"IntelX: '{term}' found in {rec.breach_name} "
                        f"({rec.source}): {', '.join(rec.exposed_data)}",
                        tags=["intelx", "breach", "darkweb"],
                    )

        person.sources.append(self.make_source_ref(INTELX_API))
        return person

    def _build_search_terms(self, person: Person) -> list[str]:
        """Build search terms from person data."""
        terms: list[str] = []
        # Extract email if available
        for profile in person.social_media:
            if "@" in profile.username:
                terms.append(profile.username)
        # Always search for the name
        if person.namn:
            terms.append(person.namn)
        return terms[:3]  # Limit to 3 terms on free tier

    async def _search_term(self, client: httpx.AsyncClient,
                           headers: dict, term: str) -> list[BreachRecord]:
        """Run a single IntelX search and poll for results."""
        records: list[BreachRecord] = []
        try:
            # Start search
            payload = {
                "term": term, "buckets": [], "lookuplevel": 0,
                "maxresults": 20, "timeout": 10, "datefrom": "",
                "dateto": "", "sort": 2, "media": 0, "terminate": [],
            }
            resp = await client.post(
                f"{INTELX_API}/intelligent/search",
                headers=headers, json=payload,
            )
            resp.raise_for_status()
            search_id = resp.json().get("id")
            if not search_id:
                return records

            # Poll for results
            for _ in range(MAX_POLL_ATTEMPTS):
                await asyncio.sleep(POLL_INTERVAL)
                result_resp = await client.get(
                    f"{INTELX_API}/intelligent/search/result",
                    headers=headers,
                    params={"id": search_id, "limit": 20, "offset": 0},
                )
                result_resp.raise_for_status()
                data = result_resp.json()

                for item in data.get("records", []):
                    records.append(BreachRecord(
                        breach_name=item.get("name", item.get("systemid", "unknown")),
                        breach_date=_parse_intelx_date(item.get("date")),
                        exposed_data=_categorize_bucket(item.get("bucket", "")),
                        source="intelx",
                        severity="high" if "darknet" in item.get("bucket", "") else "medium",
                    ))

                if data.get("status", 0) in (1, 2):  # finished or no more results
                    break

        except httpx.HTTPError as exc:
            logger.error("IntelX search for '%s' failed: %s", term, exc)

        return records


def _parse_intelx_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str[:10])
    except (ValueError, IndexError):
        return None


def _categorize_bucket(bucket: str) -> list[str]:
    mapping = {"pastes": ["email", "text_content"], "leaks": ["email", "password"],
               "darknet": ["credentials", "personal_data"], "documents": ["documents"],
               "whois": ["domain_registration"]}
    return mapping.get(bucket.lower(), ["unknown"])
