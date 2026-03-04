"""LinkedIn agent — discovers LinkedIn profiles via SearXNG + Crawl4AI."""

from __future__ import annotations

import json
import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SocialProfile, SourceType
from src.scraper import extractors

logger = logging.getLogger(__name__)


@register_agent("linkedin")
class LinkedInAgent(BaseAgent):
    """Discovers and verifies LinkedIn profiles for a person."""

    @property
    def name(self) -> str:
        return "linkedin"

    @property
    def source_type(self) -> SourceType:
        return SourceType.LINKEDIN

    @property
    def description(self) -> str:
        return "LinkedIn — professional profile discovery"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Searching LinkedIn for {person.namn}")

        # Step 1: Build search queries — name + identifiers
        queries = [f'"{person.namn}" site:linkedin.com Sweden']
        if person.arbetsgivare:
            queries[0] += f" {person.arbetsgivare}"

        ids = self.get_search_identifiers(person)
        for email in ids["emails"][:1]:
            queries.append(f'"{email}" site:linkedin.com')
        for company in ids["companies"][:1]:
            queries.append(f'"{person.namn}" "{company}" site:linkedin.com')

        # Step 2: Search with multiple queries
        all_results = []
        seen_urls = set()
        for q in queries[:3]:
            results = await self.search(q, max_results=5)
            for r in results:
                if "linkedin.com" in r.url and r.url not in seen_urls:
                    all_results.append(r)
                    seen_urls.add(r.url)

        if not all_results:
            await self._report_progress("complete", "No LinkedIn profiles found")
            return person

        # Step 3: Scrape and verify (up to 2 confirmed)
        facts = 0
        for result in all_results[:5]:
            if facts >= 2:
                break

            scraped = await self.scrape(result.url)
            if not scraped.get("success") or not scraped.get("markdown"):
                continue

            profile_data = await extractors.extract_social_profile(scraped["markdown"])
            if not profile_data:
                continue

            person_summary = self._build_person_summary(person)
            verification = await extractors.verify_social_match(
                person_summary, json.dumps(profile_data, ensure_ascii=False),
            )
            if not verification or not verification.get("is_match"):
                continue

            confidence = verification.get("confidence", 0.0)
            if confidence < 0.5:
                continue

            person.social_media.append(SocialProfile(
                platform="linkedin",
                url=result.url,
                username=profile_data.get("username", ""),
                display_name=profile_data.get("display_name", ""),
                bio=profile_data.get("bio", ""),
                followers=profile_data.get("followers"),
                verified=profile_data.get("verified", False),
                confidence=confidence,
            ))
            facts += 1

            # LinkedIn often reveals employer info
            if profile_data.get("bio") and not person.arbetsgivare:
                person.arbetsgivare = profile_data["bio"].split("\n")[0][:100]

            self._extract_bio_identifiers(person, profile_data)

            await self.store_person_fact(
                person,
                f"LinkedIn profile: {result.url} (confidence: {confidence:.0%})",
                tags=["linkedin", "social_media", "professional"],
            )

        person.sources.append(self.make_source_ref("https://linkedin.com"))
        await self._report_progress("complete", f"Found {facts} profiles", facts_found=facts)
        return person

    @staticmethod
    def _extract_bio_identifiers(person: Person, profile_data: dict):
        import re
        from src.models import SourcedFact
        bio = profile_data.get("bio", "") or ""
        website = profile_data.get("website", "") or ""
        text = f"{bio} {website}"
        for email in re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', text):
            person.sourced_facts.append(SourcedFact(
                content=f"Email found in LinkedIn bio: {email}",
                confidence=0.7, source_type="linkedin", category="digital",
            ))

    @staticmethod
    def _build_person_summary(person: Person) -> str:
        parts = [f"Name: {person.namn}"]
        if person.fodelsedatum:
            parts.append(f"Born: {person.fodelsedatum}")
        if person.adress:
            parts.append(f"City: {person.adress.ort or person.adress.kommun}")
        if person.arbetsgivare:
            parts.append(f"Employer: {person.arbetsgivare}")
        if person.foretag:
            roles = [f"{r.roll.value} at {r.foretag_namn}" for r in person.foretag[:3]]
            parts.append(f"Company roles: {', '.join(roles)}")
        return "\n".join(parts)
