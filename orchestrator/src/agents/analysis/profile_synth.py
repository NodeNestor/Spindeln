"""Profile synthesis agent — generates comprehensive report via synthesis LLM.

Inspired by DeepResearch: feeds all extracted facts with source citations,
quality scores, and temporal weighting to produce a structured report
with sections, inline citations, and confidence ratings.
"""

from __future__ import annotations

import logging

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType
from src.scraper.extractors import score_fact_recency

logger = logging.getLogger(__name__)


@register_agent("profile_synth")
class ProfileSynthAgent(BaseAgent):
    """Uses synthesis LLM to generate a comprehensive intelligence report."""

    name = "profile_synth"
    source_type = SourceType.WEB_SEARCH  # meta agent
    description = "LLM-powered profile synthesis"
    use_synthesis_model = True

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Synthesizing report for {person.namn}")

        data_input = self._build_synthesis_input(person)
        if not data_input:
            logger.info("ProfileSynth: Insufficient data for %s", person.namn)
            return person

        result = await self.extract_json(
            data_input,
            system=SYNTHESIS_SYSTEM,
            user=f"Create a comprehensive intelligence report for '{person.namn}'. "
                 f"Use the numbered sources for inline citations [n].",
        )

        if not result:
            logger.warning("ProfileSynth: LLM synthesis failed for %s", person.namn)
            return person

        # Store the synthesis result for the pipeline to capture
        person._synth_report = result

        # Store narrative and key findings in HiveMindDB
        if result.get("summary"):
            await self.store_person_fact(
                person, f"EXECUTIVE SUMMARY: {result['summary']}",
                tags=["profile_synth", "summary", person.namn],
            )

        for section in result.get("sections", []):
            heading = section.get("heading", "")
            body = section.get("body", "")
            if body:
                await self.store_person_fact(
                    person, f"[{heading}] {body[:500]}",
                    tags=["profile_synth", "section", heading.lower()],
                )

        person.sources.append(self.make_source_ref("analysis:profile_synth"))
        logger.info("ProfileSynth: Completed synthesis for %s (%d sections)",
                     person.namn, len(result.get("sections", [])))
        return person

    _MAX_INPUT_CHARS = 30_000

    def _build_synthesis_input(self, person: Person) -> str:
        """Build the synthesis input: all facts with sources, scored by recency.

        Format matches DeepResearch: numbered facts with recency scores and source URLs.
        """
        parts: list[str] = []

        # ── Identity Block ──────────────────────────────────────────────
        parts.append("=== PERSON IDENTITY ===")
        parts.append(f"Name: {person.namn}")
        if person.personnummer:
            parts.append(f"Personnummer: {person.personnummer}")
        if person.fodelsedatum:
            parts.append(f"Date of Birth: {person.fodelsedatum}")
        if person.kon.value != "okänt":
            parts.append(f"Gender: {person.kon.value}")
        if person.adress:
            parts.append(f"Address: {person.adress}")
        if person.arbetsgivare:
            parts.append(f"Employer: {person.arbetsgivare}")

        # ── Structured Data ──────────────────────────────────────────────
        if person.inkomst:
            parts.append("\n=== INCOME HISTORY ===")
            for i in sorted(person.inkomst, key=lambda x: x.ar, reverse=True):
                parts.append(f"  {i.ar}: {i.belopp:,} SEK")

        if person.foretag:
            parts.append("\n=== COMPANY ROLES ===")
            for c in person.foretag:
                line = f"  {c.roll.value} in {c.foretag_namn}"
                if c.org_nummer:
                    line += f" ({c.org_nummer})"
                parts.append(line)

        if person.familj:
            parts.append("\n=== FAMILY ===")
            for f in person.familj:
                parts.append(f"  {f.person_namn} ({f.relation.value})")

        if person.betalningsanmarkningar:
            parts.append(f"\n=== PAYMENT REMARKS ({len(person.betalningsanmarkningar)}) ===")
            for ba in person.betalningsanmarkningar:
                parts.append(f"  {ba.datum}: {ba.typ} — {ba.belopp:,} SEK" if ba.belopp else f"  {ba.datum}: {ba.typ}")

        if person.fastigheter:
            parts.append("\n=== PROPERTIES ===")
            for p in person.fastigheter:
                parts.append(f"  {p.beteckning} in {p.kommun}")

        if person.social_media:
            parts.append("\n=== SOCIAL MEDIA PROFILES ===")
            for s in person.social_media:
                line = f"  {s.platform}: {s.username or 'N/A'} ({s.url})"
                if s.verified:
                    line += " [VERIFIED]"
                parts.append(line)

        if person.breaches:
            parts.append(f"\n=== DATA BREACHES ({len(person.breaches)}) ===")
            for b in person.breaches:
                parts.append(f"  {b.breach_name} ({b.severity}) — exposed: {', '.join(b.exposed_data)}")

        # ── Extracted Facts (DeepResearch-style with recency scores) ─────
        if person.sourced_facts:
            # Score and sort by recency
            scored = [
                (f, score_fact_recency(f.discovered_at))
                for f in person.sourced_facts
            ]
            scored.sort(key=lambda x: (-x[0].quality_score, -x[1]))

            parts.append(f"\n=== EXTRACTED FACTS ({len(scored)} total, scored by quality + recency) ===")
            source_index: dict[str, int] = {}
            source_list: list[str] = []

            for i, (fact, recency) in enumerate(scored[:100]):
                # Build source reference index
                src_url = fact.source_url
                if src_url and src_url not in source_index:
                    source_index[src_url] = len(source_list) + 1
                    source_list.append(f"[{len(source_list) + 1}] {fact.source_title or src_url} — {src_url}")

                src_ref = f"[{source_index.get(src_url, '?')}]" if src_url else ""
                parts.append(
                    f"  [{i+1}] (quality={fact.quality_score}/10, recency={recency:.2f}, "
                    f"confidence={fact.confidence:.1f}) {fact.content} {src_ref}"
                )

            # Append source reference list
            if source_list:
                parts.append("\n=== SOURCES ===")
                for src in source_list:
                    parts.append(f"  {src}")

        # ── Raw News/Web Mentions (if no sourced_facts) ──────────────────
        elif person.news_mentions or person.web_mentions:
            parts.append("\n=== NEWS MENTIONS ===")
            for n in person.news_mentions:
                parts.append(f"  [{n.publication or 'news'}] {n.title}")
                if n.snippet:
                    parts.append(f"    {n.snippet[:300]}")
                if n.url:
                    parts.append(f"    URL: {n.url}")

            if person.web_mentions:
                parts.append("\n=== WEB MENTIONS ===")
                for w in person.web_mentions:
                    parts.append(f"  {w.title or 'N/A'}: {w.snippet[:200] if w.snippet else ''}")
                    if w.url:
                        parts.append(f"    URL: {w.url}")

        full_text = "\n".join(parts)
        if len(full_text) > self._MAX_INPUT_CHARS:
            full_text = full_text[:self._MAX_INPUT_CHARS] + "\n\n[... truncated]"

        return full_text


SYNTHESIS_SYSTEM = """You are an intelligence analyst creating a comprehensive person profile report.

Based on ALL collected data and extracted facts, generate a structured report with sections.
Use inline citations [n] referencing the numbered sources provided.

Return JSON:
{
  "title": "Intelligence Report: Person Name",
  "summary": "2-3 sentence executive summary of key findings",
  "sections": [
    {
      "heading": "Section title (e.g. 'Identity & Background', 'Professional Profile', 'Financial Overview', 'Digital Presence', 'Media Coverage', 'Risk Assessment')",
      "body": "Detailed paragraph(s) with inline citations [1][2]. Write in flowing prose, not bullet points. Cross-reference facts from multiple sources where possible.",
      "confidence": 0.0-1.0,
      "citations": ["url1", "url2"]
    }
  ],
  "key_findings": [
    "Most significant finding 1",
    "Most significant finding 2"
  ],
  "risk_assessment": "Overall assessment of digital exposure, financial risk, and any red flags. Rate as LOW/MEDIUM/HIGH with explanation.",
  "data_quality": "high|medium|low",
  "confidence_overall": 0.0-1.0,
  "connections_summary": "Brief summary of the person's network and relationships",
  "gaps": ["What information is missing or could not be verified"]
}

Guidelines:
- Write in neutral, factual Swedish or English (match the data language)
- Every claim should have a citation [n] from the sources
- Flag contradictions between sources
- Rate confidence per section based on source quality and corroboration
- Include at least 4 sections covering different aspects
- The risk_assessment should synthesize breach data, financial issues, and digital exposure
- Be specific — use actual numbers, dates, and names from the data"""
