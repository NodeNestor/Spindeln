"""Facebook agent — discovers Facebook profiles via SearXNG + Crawl4AI."""

from __future__ import annotations

import json
import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SocialProfile, SourceType
from src.scraper import extractors

logger = logging.getLogger(__name__)


@register_agent("facebook")
class FacebookAgent(BaseAgent):
    """Discovers and verifies Facebook profiles for a person."""

    @property
    def name(self) -> str:
        return "facebook"

    @property
    def source_type(self) -> SourceType:
        return SourceType.FACEBOOK

    @property
    def description(self) -> str:
        return "Facebook — profile discovery and verification"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Searching Facebook for {person.namn}")

        # Step 1: Search for Facebook profiles
        query = f'"{person.namn}" site:facebook.com'
        if person.adress and person.adress.ort:
            query += f" {person.adress.ort}"
        results = await self.search(query, max_results=5)

        if not results:
            await self._report_progress("complete", "No Facebook profiles found")
            return person

        # Step 2: Scrape and verify each candidate profile
        facts = 0
        for result in results[:3]:
            if "facebook.com" not in result.url:
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
                platform="facebook",
                url=result.url,
                username=profile_data.get("username", ""),
                display_name=profile_data.get("display_name", ""),
                bio=profile_data.get("bio", ""),
                followers=profile_data.get("followers"),
                verified=profile_data.get("verified", False),
                confidence=confidence,
            ))
            facts += 1

            await self.store_person_fact(
                person,
                f"Facebook profile: {result.url} (confidence: {confidence:.0%})",
                tags=["facebook", "social_media"],
            )
            break  # Stop after first confirmed match

        person.sources.append(self.make_source_ref("https://facebook.com"))
        await self._report_progress("complete", f"Found {facts} profiles", facts_found=facts)
        return person

    @staticmethod
    def _build_person_summary(person: Person) -> str:
        """Build a summary of known person data for identity verification."""
        parts = [f"Name: {person.namn}"]
        if person.fodelsedatum:
            parts.append(f"Born: {person.fodelsedatum}")
        if person.adress:
            parts.append(f"City: {person.adress.ort or person.adress.kommun}")
        if person.arbetsgivare:
            parts.append(f"Employer: {person.arbetsgivare}")
        return "\n".join(parts)
