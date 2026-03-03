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

        # Step 1: Search for LinkedIn profiles (add Sweden for relevance)
        query = f'"{person.namn}" site:linkedin.com Sweden'
        if person.arbetsgivare:
            query += f" {person.arbetsgivare}"
        results = await self.search(query, max_results=5)

        if not results:
            await self._report_progress("complete", "No LinkedIn profiles found")
            return person

        # Step 2: Scrape and verify each candidate profile
        facts = 0
        for result in results[:3]:
            if "linkedin.com" not in result.url:
                continue

            scraped = await self.scrape(result.url)
            if not scraped.get("success") or not scraped.get("markdown"):
                continue

            # Step 3: Extract profile data via LLM
            profile_data = await extractors.extract_social_profile(scraped["markdown"])
            if not profile_data:
                continue

            # Step 4: Verify identity match
            person_summary = self._build_person_summary(person)
            verification = await extractors.verify_social_match(
                person_summary, json.dumps(profile_data, ensure_ascii=False),
            )
            if not verification or not verification.get("is_match"):
                continue

            confidence = verification.get("confidence", 0.0)
            if confidence < 0.5:
                continue

            # Step 5: Add confirmed profile
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

            await self.store_person_fact(
                person,
                f"LinkedIn profile: {result.url} (confidence: {confidence:.0%})",
                tags=["linkedin", "social_media", "professional"],
            )
            break

        person.sources.append(self.make_source_ref("https://linkedin.com"))
        await self._report_progress("complete", f"Found {facts} profiles", facts_found=facts)
        return person

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
