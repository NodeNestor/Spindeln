"""Have I Been Pwned agent — checks email breach exposure via HIBP API."""

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

HIBP_API = "https://haveibeenpwned.com/api/v3"
RATE_LIMIT_SECONDS = 1.5


def _get_email(person: Person) -> str | None:
    """Extract email from social profiles or web mentions."""
    import re
    for profile in person.social_media:
        if "@" in profile.username:
            return profile.username
    for mention in person.web_mentions:
        m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", mention.snippet)
        if m:
            return m.group(0)
    return None


@register_agent("hibp")
class HIBPAgent(BaseAgent):
    """Queries Have I Been Pwned for email breach exposure."""

    name = "hibp"
    source_type = SourceType.HIBP
    description = "Have I Been Pwned breach lookup"

    async def run(self, person: Person) -> Person:
        email = _get_email(person)
        if not email:
            logger.info("HIBP: No email found for %s, skipping", person.namn)
            return person

        if not settings.hibp_api_key:
            logger.warning("HIBP: No API key configured, skipping")
            return person

        await self._report_progress("running", f"Checking breaches for {email}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            await asyncio.sleep(RATE_LIMIT_SECONDS)
            try:
                resp = await client.get(
                    f"{HIBP_API}/breachedaccount/{email}",
                    params={"truncateResponse": "false"},
                    headers={
                        "hibp-api-key": settings.hibp_api_key,
                        "user-agent": "Spindeln-OSINT-Agent",
                    },
                )
            except httpx.HTTPError as exc:
                logger.error("HIBP request failed: %s", exc)
                return person

            if resp.status_code == 404:
                logger.info("HIBP: No breaches found for %s", email)
                await self.store_person_fact(
                    person, f"No known breaches for email {email}",
                    tags=["hibp", "breach", "clean"],
                )
                return person

            if resp.status_code == 429:
                logger.warning("HIBP: Rate limited, retry later")
                return person

            if resp.status_code != 200:
                logger.warning("HIBP: Unexpected status %d", resp.status_code)
                return person

            breaches_data = resp.json()

        for b in breaches_data:
            record = BreachRecord(
                breach_name=b.get("Name", ""),
                breach_date=_parse_date(b.get("BreachDate")),
                exposed_data=b.get("DataClasses", []),
                source="hibp",
                severity=_severity(b.get("DataClasses", [])),
            )
            person.breaches.append(record)
            await self.store_person_fact(
                person,
                f"Email {email} exposed in breach '{record.breach_name}' "
                f"({record.breach_date}): {', '.join(record.exposed_data)}",
                tags=["hibp", "breach", record.severity],
            )

        person.sources.append(self.make_source_ref(
            f"{HIBP_API}/breachedaccount/{email}",
        ))
        logger.info("HIBP: Found %d breaches for %s", len(breaches_data), email)
        return person


def _parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return None


def _severity(data_classes: list[str]) -> str:
    critical = {"Passwords", "Credit cards", "Bank account numbers", "Social security numbers"}
    high = {"Phone numbers", "IP addresses", "Physical addresses", "Passport numbers"}
    if critical & set(data_classes):
        return "critical"
    if high & set(data_classes):
        return "high"
    if len(data_classes) > 3:
        return "medium"
    return "low"
