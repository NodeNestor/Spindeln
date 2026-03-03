"""Hudson Rock agent — checks infostealer malware exposure via Cavalier API."""

from __future__ import annotations

import logging
from datetime import date

import httpx

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import BreachRecord, Person, SourceType

logger = logging.getLogger(__name__)

CAVALIER_API = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email"


def _get_email(person: Person) -> str | None:
    """Extract email from social profiles or web mentions."""
    for profile in person.social_media:
        if "@" in profile.username:
            return profile.username
    for mention in person.web_mentions:
        if "@" in mention.snippet:
            import re
            match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", mention.snippet)
            if match:
                return match.group(0)
    return None


@register_agent("hudsonrock")
class HudsonRockAgent(BaseAgent):
    """Checks infostealer malware exposure via Hudson Rock Cavalier API."""

    name = "hudsonrock"
    source_type = SourceType.HUDSONROCK
    description = "Hudson Rock infostealer exposure check"

    async def run(self, person: Person) -> Person:
        email = _get_email(person)
        if not email:
            logger.info("HudsonRock: No email found for %s, skipping", person.namn)
            return person

        await self._report_progress("running", f"Checking infostealer exposure for {email}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(
                    CAVALIER_API,
                    params={"email": email},
                )
            except httpx.HTTPError as exc:
                logger.error("HudsonRock request failed: %s", exc)
                return person

            if resp.status_code != 200:
                logger.warning("HudsonRock: status %d for %s", resp.status_code, email)
                return person

            data = resp.json()

        stealers = data.get("stealers", [])
        if not stealers:
            logger.info("HudsonRock: No infostealer exposure for %s", email)
            await self.store_person_fact(
                person, f"No infostealer exposure found for {email}",
                tags=["hudsonrock", "infostealer", "clean"],
            )
            person.sources.append(self.make_source_ref(CAVALIER_API))
            return person

        for stealer in stealers:
            exposed = _extract_exposed_data(stealer)
            record = BreachRecord(
                breach_name=f"Infostealer: {stealer.get('malware_name', 'unknown')}",
                breach_date=_parse_date(stealer.get("date_compromised")),
                exposed_data=exposed,
                source="hudsonrock",
                severity="critical",  # infostealers are always critical
            )
            person.breaches.append(record)

            computer = stealer.get("computer_name", "unknown")
            os_info = stealer.get("operating_system", "unknown")
            await self.store_person_fact(
                person,
                f"Infostealer '{stealer.get('malware_name', '?')}' compromised "
                f"{email} on {computer} ({os_info}). "
                f"Exposed: {', '.join(exposed)}",
                tags=["hudsonrock", "infostealer", "critical"],
            )

        person.sources.append(self.make_source_ref(
            f"{CAVALIER_API}?email={email}",
        ))
        logger.info("HudsonRock: Found %d infostealers for %s", len(stealers), email)
        return person


def _extract_exposed_data(stealer: dict) -> list[str]:
    """Determine what data types were exposed by the infostealer."""
    exposed: list[str] = []
    if stealer.get("credentials"):
        exposed.append("credentials")
    if stealer.get("cookies"):
        exposed.append("session_cookies")
    if stealer.get("autofills"):
        exposed.append("autofill_data")
    if stealer.get("credit_cards"):
        exposed.append("credit_cards")
    if stealer.get("crypto_wallets"):
        exposed.append("crypto_wallets")
    if stealer.get("screenshots"):
        exposed.append("screenshots")
    return exposed or ["unknown"]


def _parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str[:10])
    except (ValueError, IndexError):
        return None
