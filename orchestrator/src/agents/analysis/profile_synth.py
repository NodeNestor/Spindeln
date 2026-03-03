"""Profile synthesis agent -- generates natural-language profile summary via LLM."""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType

logger = logging.getLogger(__name__)


@register_agent("profile_synth")
class ProfileSynthAgent(BaseAgent):
    """Uses LLM to generate a coherent natural-language profile summary."""

    name = "profile_synth"
    source_type = SourceType.WEB_SEARCH  # meta agent
    description = "LLM-powered profile synthesis"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Synthesizing profile for {person.namn}")

        data_summary = self._build_data_summary(person)
        if not data_summary:
            logger.info("ProfileSynth: Insufficient data for %s", person.namn)
            return person

        result = await self.extract_json(
            data_summary,
            system=PROFILE_SYNTH_SYSTEM,
            user=f"Synthesize a comprehensive profile for {person.namn} "
                 f"based on all the collected data below.",
        )
        if not result:
            logger.warning("ProfileSynth: LLM synthesis failed for %s", person.namn)
            return person

        # Store the full narrative
        narrative = result.get("narrative", "")
        if narrative:
            await self.store_person_fact(
                person, f"PROFILE SUMMARY: {narrative}",
                tags=["profile_synth", "summary", person.namn],
            )

        # Store risk assessment if present
        risk = result.get("risk_assessment", "")
        if risk:
            await self.store_person_fact(
                person, f"RISK ASSESSMENT: {risk}",
                tags=["profile_synth", "risk", person.namn],
            )

        # Store key facts
        for fact in result.get("key_facts", []):
            await self.store_person_fact(
                person, f"KEY FACT: {fact}",
                tags=["profile_synth", "key_fact"],
            )

        person.sources.append(self.make_source_ref("analysis:profile_synth"))
        logger.info("ProfileSynth: Completed synthesis for %s", person.namn)
        return person

    def _build_data_summary(self, person: Person) -> str:
        """Assemble all known data into a text block for the LLM."""
        sections: list[str] = []

        sections.append(f"NAMN: {person.namn}")
        if person.personnummer:
            sections.append(f"PERSONNUMMER: {person.personnummer}")
        if person.fodelsedatum:
            sections.append(f"FÖDELSEDATUM: {person.fodelsedatum}")
        if person.kon.value != "okänt":
            sections.append(f"KÖN: {person.kon.value}")
        if person.adress:
            sections.append(f"ADRESS: {person.adress}")
        if person.arbetsgivare:
            sections.append(f"ARBETSGIVARE: {person.arbetsgivare}")

        if person.inkomst:
            latest = max(person.inkomst, key=lambda i: i.ar)
            sections.append(f"SENASTE INKOMST: {latest.belopp:,} kr ({latest.ar})")

        if person.foretag:
            roles = [f"{r.roll.value} i {r.foretag_namn}" for r in person.foretag]
            sections.append(f"FÖRETAGSROLLER: {'; '.join(roles)}")

        if person.familj:
            fam = [f"{r.person_namn} ({r.relation.value})" for r in person.familj]
            sections.append(f"FAMILJ: {'; '.join(fam)}")

        if person.fastigheter:
            props = [f"{p.beteckning} ({p.kommun})" for p in person.fastigheter]
            sections.append(f"FASTIGHETER: {'; '.join(props)}")

        if person.social_media:
            profiles = [f"{p.platform}: {p.username or p.url}" for p in person.social_media]
            sections.append(f"SOCIALA MEDIER: {'; '.join(profiles)}")

        if person.breaches:
            breaches = [f"{b.breach_name} ({b.severity})" for b in person.breaches]
            sections.append(f"DATALÄCKOR: {'; '.join(breaches)}")

        if person.news_mentions:
            news = [f"{n.title} ({n.publication})" for n in person.news_mentions[:5]]
            sections.append(f"NYHETER: {'; '.join(news)}")

        if person.betalningsanmarkningar:
            sections.append(
                f"BETALNINGSANMÄRKNINGAR: {len(person.betalningsanmarkningar)} st"
            )

        return "\n".join(sections)


PROFILE_SYNTH_SYSTEM = """You are a Swedish intelligence analyst creating a comprehensive person profile.

Based on all collected data, generate a structured profile summary.

Return JSON:
{
  "narrative": "A 3-5 paragraph natural-language profile in Swedish, covering identity, professional life, financial situation, digital presence, and any notable findings.",
  "key_facts": [
    "Most important fact 1",
    "Most important fact 2"
  ],
  "risk_assessment": "Brief assessment of digital exposure risk and any red flags found.",
  "data_quality": "Assessment of data completeness: high|medium|low",
  "connections_summary": "Brief summary of the person's network (family, companies, associates)"
}

Write in a neutral, factual tone. Do not speculate beyond what the data supports."""
