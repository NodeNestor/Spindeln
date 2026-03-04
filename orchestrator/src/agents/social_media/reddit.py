"""Reddit agent — discovers Reddit activity via SearXNG + Crawl4AI."""

from __future__ import annotations

import json
import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SocialProfile, SourceType, WebMention
from src.scraper import extractors

logger = logging.getLogger(__name__)


@register_agent("reddit")
class RedditAgent(BaseAgent):
    """Discovers Reddit profiles and activity for a person."""

    @property
    def name(self) -> str:
        return "reddit"

    @property
    def source_type(self) -> SourceType:
        return SourceType.REDDIT

    @property
    def description(self) -> str:
        return "Reddit — profile and activity discovery"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Searching Reddit for {person.namn}")

        # Step 1: Build search queries — name + identifiers
        queries = [f'"{person.namn}" site:reddit.com']
        if person.adress and person.adress.ort:
            queries[0] += f" {person.adress.ort}"

        ids = self.get_search_identifiers(person)
        for handle in ids["handles"][:1]:
            queries.append(f'"{handle}" site:reddit.com')

        # Step 2: Search with multiple queries
        all_results = []
        seen_urls = set()
        for q in queries[:3]:
            results = await self.search(q, max_results=10)
            for r in results:
                if "reddit.com" in r.url and r.url not in seen_urls:
                    all_results.append(r)
                    seen_urls.add(r.url)

        if not all_results:
            await self._report_progress("complete", "No Reddit activity found")
            return person

        # Separate profile pages from post/comment pages
        profile_urls = []
        post_urls = []
        for r in all_results:
            if "/user/" in r.url or "/u/" in r.url:
                profile_urls.append(r)
            else:
                post_urls.append(r)

        facts = 0

        # Step 3: Check profile pages (up to 2 confirmed)
        for result in profile_urls[:3]:
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
                platform="reddit",
                url=result.url,
                username=profile_data.get("username", ""),
                display_name=profile_data.get("display_name", ""),
                bio=profile_data.get("bio", ""),
                followers=profile_data.get("followers"),
                confidence=confidence,
            ))
            facts += 1

            await self.store_person_fact(
                person,
                f"Reddit profile: {result.url} (confidence: {confidence:.0%})",
                tags=["reddit", "social_media"],
            )

        # Step 4: Record mentions in posts/comments
        for result in post_urls[:5]:
            person.web_mentions.append(WebMention(
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                source_type="reddit",
            ))
            facts += 1

        person.sources.append(self.make_source_ref("https://reddit.com"))
        await self._report_progress("complete", f"Found {facts} items", facts_found=facts)
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
        return "\n".join(parts)
