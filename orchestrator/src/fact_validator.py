"""Fact validation — synthesis-model identity verification + contradiction detection."""

from __future__ import annotations

import logging
import re
from datetime import date

from src.models import Person, SourcedFact
from src.scraper.extractors import extract_json_synthesis

logger = logging.getLogger(__name__)


# ── Synthesis-based Fact Validation ───────────────────────────────────────────

FACT_VALIDATION_SYSTEM = """You are a fact validator for a person intelligence system.
You will receive a list of extracted facts and known identity data about a person.
Your job is to rate each fact based on whether it belongs to the TARGET person.

For each fact, assign one rating:
- CONFIRMED: clearly matches the target person's known identity
- PLAUSIBLE: could be this person, no contradicting evidence
- WRONG_PERSON: clearly about a different person with a similar name
- CONTRADICTS: conflicts with confirmed/known facts about the target

Return JSON:
{
  "ratings": [
    {"index": 0, "rating": "CONFIRMED|PLAUSIBLE|WRONG_PERSON|CONTRADICTS", "reason": "brief explanation"}
  ]
}

Be strict about WRONG_PERSON — if a fact mentions a different birth year, different city,
different age, or different profession than what is known, mark it WRONG_PERSON.
Template data (example values from website tutorials) should be marked WRONG_PERSON."""


async def validate_facts(facts: list[SourcedFact], person: Person) -> list[SourcedFact]:
    """Use synthesis model to validate facts against known identity.

    Removes facts rated WRONG_PERSON, lowers confidence on CONTRADICTS.
    Returns filtered list.
    """
    if not facts:
        return facts

    # Build known identity summary
    identity_parts = [f"Name: {person.namn}"]
    if person.fodelsedatum:
        identity_parts.append(f"Born: {person.fodelsedatum}")
    if person.personnummer:
        identity_parts.append(f"Personnummer: {person.personnummer}")
    if person.adress:
        addr_parts = []
        if person.adress.gatuadress:
            addr_parts.append(person.adress.gatuadress)
        if person.adress.ort:
            addr_parts.append(person.adress.ort)
        if addr_parts:
            identity_parts.append(f"Address: {', '.join(addr_parts)}")
    if person.arbetsgivare:
        identity_parts.append(f"Employer: {person.arbetsgivare}")

    identity_summary = "\n".join(identity_parts)

    # Build facts list for validation (batch in chunks of 30 to avoid token limits)
    validated: list[SourcedFact] = []
    batch_size = 30

    for batch_start in range(0, len(facts), batch_size):
        batch = facts[batch_start:batch_start + batch_size]
        facts_text = "\n".join(
            f"[{i}] {f.content} (source: {f.source_type}, confidence: {f.confidence})"
            for i, f in enumerate(batch)
        )

        content = f"Known identity:\n{identity_summary}\n\nFacts to validate:\n{facts_text}"
        user_prompt = (
            f"Rate each fact — does it belong to {person.namn}? "
            f"Check for wrong-person data, template data, and contradictions."
        )

        try:
            result = await extract_json_synthesis(
                content, FACT_VALIDATION_SYSTEM, user_prompt,
                max_tokens=4096,
            )
        except Exception as e:
            logger.warning("Fact validation failed, keeping all facts: %s", e)
            validated.extend(batch)
            continue

        if not result or not isinstance(result, dict) or "ratings" not in result:
            logger.warning("Fact validation returned invalid response, keeping batch")
            validated.extend(batch)
            continue

        # Apply ratings
        ratings_by_idx = {}
        for r in result["ratings"]:
            if isinstance(r, dict) and "index" in r:
                ratings_by_idx[r["index"]] = r

        for i, fact in enumerate(batch):
            rating_info = ratings_by_idx.get(i)
            if not rating_info:
                validated.append(fact)
                continue

            rating = rating_info.get("rating", "PLAUSIBLE").upper()
            if rating == "WRONG_PERSON":
                logger.info("Removing wrong-person fact: %.80s (reason: %s)",
                           fact.content, rating_info.get("reason", ""))
                continue
            elif rating == "CONTRADICTS":
                fact.confidence = min(fact.confidence, 0.3)
                logger.info("Flagged contradicting fact (lowered confidence): %.80s", fact.content)
            elif rating == "CONFIRMED":
                fact.confidence = max(fact.confidence, 0.8)

            validated.append(fact)

    removed = len(facts) - len(validated)
    if removed:
        logger.info("Fact validation: removed %d wrong-person facts (kept %d/%d)",
                    removed, len(validated), len(facts))

    return validated


# ── Regex-based Contradiction Detection ───────────────────────────────────────

_DATE_RE = re.compile(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b')
_BORN_RE = re.compile(r'(?:born|född)\s+(\d{4}[-/]\d{1,2}[-/]\d{1,2})', re.IGNORECASE)
_AGE_RE = re.compile(r'(\d{1,3})\s+(?:years?\s+old|år\s+gammal|år)', re.IGNORECASE)


def detect_contradictions(facts: list[SourcedFact]) -> list[dict]:
    """Fast regex-based check for conflicting claims among facts.

    Returns list of contradiction descriptions. Also lowers confidence
    on the weaker fact in each contradicting pair.
    """
    contradictions: list[dict] = []

    # Collect birth dates
    birth_dates: list[tuple[str, SourcedFact]] = []
    ages: list[tuple[int, SourcedFact]] = []

    for fact in facts:
        text = fact.content.lower()

        # Check for birth dates
        m = _BORN_RE.search(fact.content)
        if m:
            birth_dates.append((m.group(1), fact))
        elif "född" in text or "born" in text:
            dm = _DATE_RE.search(fact.content)
            if dm:
                birth_dates.append((f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}", fact))

        # Check for ages
        am = _AGE_RE.search(fact.content)
        if am:
            ages.append((int(am.group(1)), fact))

    # Detect conflicting birth dates
    if len(birth_dates) > 1:
        unique_dates = set(d for d, _ in birth_dates)
        if len(unique_dates) > 1:
            contradictions.append({
                "type": "conflicting_birth_dates",
                "values": list(unique_dates),
                "facts": [f.content[:80] for _, f in birth_dates],
            })
            # Lower confidence of all but the highest-quality source
            sorted_facts = sorted(birth_dates, key=lambda x: x[1].quality_score, reverse=True)
            for _, fact in sorted_facts[1:]:
                fact.confidence = min(fact.confidence, 0.3)

    # Detect conflicting ages (more than 2 years apart)
    if len(ages) > 1:
        age_values = [a for a, _ in ages]
        if max(age_values) - min(age_values) > 2:
            contradictions.append({
                "type": "conflicting_ages",
                "values": age_values,
                "facts": [f.content[:80] for _, f in ages],
            })
            sorted_facts = sorted(ages, key=lambda x: x[1].quality_score, reverse=True)
            for _, fact in sorted_facts[1:]:
                fact.confidence = min(fact.confidence, 0.3)

    if contradictions:
        logger.info("Detected %d contradictions in %d facts", len(contradictions), len(facts))

    return contradictions
