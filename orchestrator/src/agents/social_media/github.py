"""GitHub agent — discovers GitHub profiles via SearXNG + GitHub API."""

from __future__ import annotations

import json
import logging

import httpx

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SocialProfile, SourceType
from src.scraper import extractors

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


@register_agent("github")
class GitHubAgent(BaseAgent):
    """Discovers and verifies GitHub profiles for a person."""

    @property
    def name(self) -> str:
        return "github"

    @property
    def source_type(self) -> SourceType:
        return SourceType.GITHUB

    @property
    def description(self) -> str:
        return "GitHub — developer profile discovery"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Searching GitHub for {person.namn}")

        # Step 1: Search via both SearXNG and GitHub API
        candidates = await self._find_candidates(person)
        if not candidates:
            await self._report_progress("complete", "No GitHub profiles found")
            return person

        # Step 2: Scrape and verify each candidate profile
        facts = 0
        for url in candidates[:3]:
            scraped = await self.scrape(url)
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
                platform="github",
                url=url,
                username=profile_data.get("username", ""),
                display_name=profile_data.get("display_name", ""),
                bio=profile_data.get("bio", ""),
                followers=profile_data.get("followers"),
                verified=False,
                confidence=confidence,
            ))
            facts += 1

            await self.store_person_fact(
                person,
                f"GitHub profile: {url} (confidence: {confidence:.0%})",
                tags=["github", "social_media", "developer"],
            )
            break

        person.sources.append(self.make_source_ref("https://github.com"))
        await self._report_progress("complete", f"Found {facts} profiles", facts_found=facts)
        return person

    async def _find_candidates(self, person: Person) -> list[str]:
        """Find candidate GitHub profile URLs from multiple sources."""
        urls: list[str] = []

        # SearXNG search
        query = f'"{person.namn}" site:github.com'
        results = await self.search(query, max_results=5)
        for r in results:
            if "github.com" in r.url and r.url not in urls:
                urls.append(r.url)

        # GitHub API user search (free, unauthenticated)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{GITHUB_API}/search/users",
                    params={"q": f"fullname:{person.namn}", "per_page": 3},
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if resp.status_code == 200:
                    for user in resp.json().get("items", []):
                        profile_url = user.get("html_url", "")
                        if profile_url and profile_url not in urls:
                            urls.append(profile_url)
        except Exception as e:
            logger.debug("GitHub API search failed: %s", e)

        return urls

    @staticmethod
    def _build_person_summary(person: Person) -> str:
        parts = [f"Name: {person.namn}"]
        if person.fodelsedatum:
            parts.append(f"Born: {person.fodelsedatum}")
        if person.adress:
            parts.append(f"City: {person.adress.ort or person.adress.kommun}")
        if person.arbetsgivare:
            parts.append(f"Employer: {person.arbetsgivare}")
        return "\n".join(parts)
