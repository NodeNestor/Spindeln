"""Google Dork agent — advanced search queries for exposed data via SearXNG."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import BreachRecord, Person, SourceType, WebMention
from src.scraper import extractors

logger = logging.getLogger(__name__)


@register_agent("google_dorks")
class GoogleDorkAgent(BaseAgent):
    """Runs Google-style dork queries through SearXNG to find exposed data."""

    name = "google_dorks"
    source_type = SourceType.GOOGLE_DORK
    description = "Google dork exposure search"

    async def run(self, person: Person) -> Person:
        dorks = self._build_dorks(person)
        if not dorks:
            return person

        await self._report_progress("running", f"Running dork queries for {person.namn}")

        total_found = 0
        for label, query in dorks:
            results = await self.search(query)
            if not results:
                continue

            for result in results[:5]:  # Top 5 per dork
                scraped = await self.scrape(result.url)
                if not scraped.get("success") or not scraped.get("markdown"):
                    continue

                extracted = await extractors.extract_breach_data(
                    scraped["markdown"],
                    person_context=f"Person: {person.namn}. Dork: {label}",
                )
                if not extracted:
                    # Still record as a web mention
                    person.web_mentions.append(WebMention(
                        url=result.url,
                        title=result.title,
                        snippet=result.snippet[:300],
                        source_type="google_dork",
                    ))
                    continue

                for breach in extracted.get("breaches", []):
                    record = BreachRecord(
                        breach_name=breach.get("breach_name", f"Dork: {label}"),
                        exposed_data=breach.get("exposed_data", []),
                        source="google_dork",
                        severity=breach.get("severity", "medium"),
                    )
                    person.breaches.append(record)
                    total_found += 1

                    await self.store_person_fact(
                        person,
                        f"Google dork '{label}' found exposure at {result.url}: "
                        f"{', '.join(record.exposed_data)}",
                        tags=["google_dork", "breach", record.severity],
                    )

        person.sources.append(self.make_source_ref("searxng:google_dorks"))
        logger.info("GoogleDork: Found %d exposures for %s", total_found, person.namn)
        return person

    def _build_dorks(self, person: Person) -> list[tuple[str, str]]:
        """Build (label, query) dork pairs from person data."""
        dorks: list[tuple[str, str]] = []
        name = person.namn
        email = self._get_email(person)

        if email:
            dorks.append((
                "email_in_files",
                f'"{email}" filetype:txt OR filetype:csv OR filetype:sql',
            ))
            dorks.append((
                "email_paste",
                f'"{email}" site:pastebin.com',
            ))

        if name:
            dorks.append((
                "name_leak_dump",
                f'"{name}" inurl:leak OR inurl:dump OR inurl:breach',
            ))
            dorks.append((
                "name_paste",
                f'"{name}" site:pastebin.com',
            ))
            dorks.append((
                "name_in_files",
                f'"{name}" filetype:txt OR filetype:csv OR filetype:xlsx',
            ))

        return dorks

    @staticmethod
    def _get_email(person: Person) -> str | None:
        for profile in person.social_media:
            if "@" in profile.username:
                return profile.username
        return None
