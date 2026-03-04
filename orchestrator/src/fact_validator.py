"""Fact validation — synthesis-model identity verification + verification branches.

Three-pass validation:
1. Rate facts as CONFIRMED / PLAUSIBLE / WRONG_PERSON / CONTRADICTS / VERIFY
2. For VERIFY facts: search for the specific claim, scrape context, compare with target
3. Contradiction detection via regex (conflicting DOBs, ages)
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime

from src.models import Person, SourcedFact
from src.scraper.extractors import extract_json_synthesis

logger = logging.getLogger(__name__)


# ── Synthesis-based Fact Validation ───────────────────────────────────────────

FACT_VALIDATION_SYSTEM = """You are a fact validator for a person intelligence system.
You receive extracted facts and CONFIRMED identity data about a target person.
Your job: determine whether each fact belongs to the TARGET person or someone else.

IMPORTANT — AGE-AWARE PLAUSIBILITY:
- The target's current age is provided. Use it to reject implausible claims.
- A 20-year-old cannot be a CEO, chairman, or senior executive of a major company.
- A teenager cannot have decades of professional experience.
- If a fact implies an age/career inconsistent with the target, mark WRONG_PERSON.

IMPORTANT — CROSS-REFERENCE WITH CONFIRMED FACTS:
- You will see confirmed facts about the target. Use these to verify new facts.
- If a new fact contradicts confirmed facts, mark CONTRADICTS.
- If a new fact is about a clearly different person (different city, age, profession), mark WRONG_PERSON.

For each fact, assign one rating:
- CONFIRMED: clearly matches the target person's known identity
- PLAUSIBLE: could be this person, no contradicting evidence
- WRONG_PERSON: clearly about a different person with a similar name
- CONTRADICTS: conflicts with confirmed/known facts about the target
- VERIFY: uncertain — this is a specific professional/organizational claim that COULD be true but seems unlikely given the target's profile. Needs verification research.

Return JSON:
{
  "ratings": [
    {"index": 0, "rating": "CONFIRMED|PLAUSIBLE|WRONG_PERSON|CONTRADICTS|VERIFY", "reason": "brief explanation", "verify_query": "search query to verify this claim (only for VERIFY)"}
  ]
}

Be STRICT about WRONG_PERSON:
- Different birth year, different city, different age → WRONG_PERSON
- Template data from website tutorials → WRONG_PERSON
- Professional claims implausible for the target's age → WRONG_PERSON

Use VERIFY sparingly — only for specific verifiable claims where you genuinely aren't sure:
- "Oscar Nyblom is chairman of Eniro" → VERIFY with query "Eniro chairman ordförande"
- "Oscar Nyblom works at Company X" → VERIFY with query "Company X employee Oscar Nyblom"
Do NOT use VERIFY for generic web mentions or news snippets."""


VERIFICATION_SYSTEM = """You are verifying whether a specific claim belongs to the right person.

You will receive:
1. A CLAIM about a person (extracted from a web page)
2. VERIFICATION RESULTS — web search results about the specific claim
3. The TARGET person's confirmed identity (name, age, address, etc.)

Your job: determine if the person described in the verification results is the SAME person as the target.

Compare:
- Age/birth year: do they match?
- Location: same city/region?
- Professional level: plausible for the target's age?
- Any distinguishing details that confirm or deny it's the same person?

Return JSON:
{
  "is_same_person": true/false,
  "confidence": 0.0-1.0,
  "reason": "explanation of why this is or isn't the same person",
  "found_person_details": "brief description of who the claim actually refers to"
}"""


def _compute_age(dob: date | str | None) -> int | None:
    """Compute current age from date of birth."""
    if not dob:
        return None
    if isinstance(dob, str):
        try:
            dob = datetime.strptime(dob, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    today = date.today()
    age = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1
    return age


def _build_identity_summary(person: Person, confirmed_facts: list[SourcedFact] | None = None) -> str:
    """Build a comprehensive identity summary including confirmed facts."""
    parts = [f"Name: {person.namn}"]

    age = _compute_age(person.fodelsedatum)
    if person.fodelsedatum:
        parts.append(f"Born: {person.fodelsedatum}")
    if age is not None:
        parts.append(f"Current age: {age} years old (as of {date.today()})")
    if person.personnummer:
        parts.append(f"Personnummer: {person.personnummer}")
    if person.adress:
        addr_parts = []
        if person.adress.gatuadress:
            addr_parts.append(person.adress.gatuadress)
        if person.adress.ort:
            addr_parts.append(person.adress.ort)
        if addr_parts:
            parts.append(f"Address: {', '.join(addr_parts)}")
    if person.arbetsgivare:
        parts.append(f"Employer: {person.arbetsgivare}")

    # Add confirmed facts for cross-referencing
    if confirmed_facts:
        parts.append("\nCONFIRMED FACTS (use these to cross-reference new facts):")
        for f in confirmed_facts[:20]:  # Cap at 20 to avoid token explosion
            parts.append(f"  - {f.content[:150]}")

    return "\n".join(parts)


async def _verify_claim(fact: SourcedFact, verify_query: str,
                        identity_summary: str, person_name: str) -> bool:
    """Verification branch: search for the claim, compare with target identity.

    Returns True if the fact should be KEPT (same person), False if rejected.
    """
    from src.scraper import searxng_client, crawl4ai_client

    logger.info("Verification branch: searching '%s' for fact: %.60s",
                verify_query, fact.content)

    # Search for the specific claim
    try:
        results = await searxng_client.search(
            verify_query, max_results=5, language="sv-SE",
        )
    except Exception as e:
        logger.warning("Verification search failed: %s — keeping fact as plausible", e)
        return True  # Can't verify → keep with lower confidence

    if not results:
        logger.info("Verification search returned 0 results — keeping fact as plausible")
        return True

    # Scrape the top 2 results for context
    verification_texts = []
    for result in results[:2]:
        try:
            scrape_result = await crawl4ai_client.scrape(result.url)
            if scrape_result.get("success") and scrape_result.get("markdown"):
                # Take first 2000 chars — enough context to identify the person
                text = scrape_result["markdown"][:2000]
                verification_texts.append(
                    f"Source: {result.url}\nTitle: {result.title}\n{text}"
                )
        except Exception:
            # If scraping fails, use the search snippet
            verification_texts.append(
                f"Source: {result.url}\nTitle: {result.title}\nSnippet: {result.snippet}"
            )

    if not verification_texts:
        return True

    # Ask synthesis model to compare
    verification_content = (
        f"CLAIM TO VERIFY:\n{fact.content}\n"
        f"(Source: {fact.source_url})\n\n"
        f"TARGET PERSON IDENTITY:\n{identity_summary}\n\n"
        f"VERIFICATION RESULTS:\n" + "\n---\n".join(verification_texts)
    )

    try:
        result = await extract_json_synthesis(
            verification_content, VERIFICATION_SYSTEM,
            f"Is the person described in the claim the same as {person_name}? "
            f"Compare age, location, professional level, and any other details.",
            max_tokens=1024,
        )
    except Exception as e:
        logger.warning("Verification synthesis failed: %s — keeping fact", e)
        return True

    if not result or not isinstance(result, dict):
        return True

    is_same = result.get("is_same_person", True)
    confidence = result.get("confidence", 0.5)
    reason = result.get("reason", "")
    found_details = result.get("found_person_details", "")

    if is_same:
        logger.info("Verification CONFIRMED: %.60s (confidence: %.1f, reason: %s)",
                    fact.content, confidence, reason)
    else:
        logger.info("Verification REJECTED: %.60s → actually about: %s (reason: %s)",
                    fact.content, found_details, reason)

    return is_same


async def validate_facts(facts: list[SourcedFact], person: Person) -> list[SourcedFact]:
    """Validate facts in two passes:
    1. Rate all facts (CONFIRMED/PLAUSIBLE/WRONG_PERSON/CONTRADICTS/VERIFY)
    2. For VERIFY facts: run verification branches in parallel

    Returns filtered list with adjusted confidences.
    """
    if not facts:
        return facts

    identity_summary = _build_identity_summary(person)

    # ── Pass 1: Rate all facts ───────────────────────────────────────────
    confirmed: list[SourcedFact] = []
    plausible: list[SourcedFact] = []
    needs_verification: list[tuple[SourcedFact, str]] = []  # (fact, search_query)
    batch_size = 30

    for batch_start in range(0, len(facts), batch_size):
        batch = facts[batch_start:batch_start + batch_size]
        facts_text = "\n".join(
            f"[{i}] {f.content} (source: {f.source_type}, confidence: {f.confidence})"
            for i, f in enumerate(batch)
        )

        # Rebuild identity summary with confirmed facts from earlier batches
        current_identity = _build_identity_summary(person, confirmed)

        content = f"Known identity:\n{current_identity}\n\nFacts to validate:\n{facts_text}"
        user_prompt = (
            f"Rate each fact — does it belong to {person.namn}? "
            f"Check for wrong-person data, age-implausible claims, template data, "
            f"and contradictions with confirmed facts."
        )

        try:
            result = await extract_json_synthesis(
                content, FACT_VALIDATION_SYSTEM, user_prompt,
                max_tokens=4096,
            )
        except Exception as e:
            logger.warning("Fact validation failed, keeping all facts: %s", e)
            plausible.extend(batch)
            continue

        if not result or not isinstance(result, dict) or "ratings" not in result:
            logger.warning("Fact validation returned invalid response, keeping batch")
            plausible.extend(batch)
            continue

        # Apply ratings
        ratings_by_idx = {}
        for r in result["ratings"]:
            if isinstance(r, dict) and "index" in r:
                ratings_by_idx[r["index"]] = r

        for i, fact in enumerate(batch):
            rating_info = ratings_by_idx.get(i)
            if not rating_info:
                plausible.append(fact)
                continue

            rating = rating_info.get("rating", "PLAUSIBLE").upper()

            if rating == "WRONG_PERSON":
                logger.info("Removing wrong-person fact: %.80s (reason: %s)",
                           fact.content, rating_info.get("reason", ""))
                continue
            elif rating == "CONTRADICTS":
                fact.confidence = min(fact.confidence, 0.3)
                logger.info("Flagged contradicting fact (lowered confidence): %.80s",
                           fact.content)
                plausible.append(fact)
            elif rating == "CONFIRMED":
                fact.confidence = max(fact.confidence, 0.8)
                confirmed.append(fact)
            elif rating == "VERIFY":
                query = rating_info.get("verify_query", "")
                if query:
                    needs_verification.append((fact, query))
                    logger.info("Queued for verification: %.60s (query: %s)",
                               fact.content, query)
                else:
                    plausible.append(fact)
            else:
                plausible.append(fact)

    # ── Pass 2: Verification branches ────────────────────────────────────
    verified: list[SourcedFact] = []

    if needs_verification:
        logger.info("Running %d verification branches...", len(needs_verification))

        # Rebuild identity with all confirmed facts
        full_identity = _build_identity_summary(person, confirmed)

        # Run verifications in parallel (bounded concurrency)
        sem = asyncio.Semaphore(3)  # Max 3 concurrent verification searches

        async def _verify_one(fact: SourcedFact, query: str) -> SourcedFact | None:
            async with sem:
                keep = await _verify_claim(fact, query, full_identity, person.namn)
                if keep:
                    fact.confidence = max(fact.confidence, 0.7)
                    return fact
                return None

        tasks = [_verify_one(f, q) for f, q in needs_verification]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, SourcedFact):
                verified.append(r)
            elif isinstance(r, Exception):
                logger.warning("Verification task failed: %s", r)

        logger.info("Verification complete: %d/%d claims confirmed",
                    len(verified), len(needs_verification))

    # ── Combine results ──────────────────────────────────────────────────
    all_validated = confirmed + plausible + verified

    removed = len(facts) - len(all_validated)
    if removed:
        logger.info("Fact validation: removed %d wrong-person facts (kept %d/%d)",
                    removed, len(all_validated), len(facts))

    return all_validated


# ── Regex-based Contradiction Detection ───────────────────────────────────────

_DATE_RE = re.compile(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b')
_BORN_RE = re.compile(r'(?:born|född)\s+(\d{4}[-/]\d{1,2}[-/]\d{1,2})', re.IGNORECASE)
_AGE_RE = re.compile(r'(\d{1,3})\s+(?:years?\s+old|år\s+gammal|år)', re.IGNORECASE)


def detect_contradictions(facts: list[SourcedFact], person: Person | None = None) -> list[dict]:
    """Contradiction detection with age-awareness.

    If person has a known DOB, uses it to validate age claims.
    Returns list of contradiction descriptions. Lowers confidence on weaker facts.
    """
    contradictions: list[dict] = []

    # Collect birth dates and ages from facts
    birth_dates: list[tuple[str, SourcedFact]] = []
    ages: list[tuple[int, SourcedFact]] = []

    known_age = _compute_age(person.fodelsedatum) if person else None

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

    # Cross-check ages against known DOB
    if known_age is not None and ages:
        for age_val, fact in ages:
            if abs(age_val - known_age) > 2:
                contradictions.append({
                    "type": "age_mismatch",
                    "known_age": known_age,
                    "claimed_age": age_val,
                    "fact": fact.content[:80],
                })
                fact.confidence = min(fact.confidence, 0.2)
                logger.info("Age mismatch: known age %d, fact claims %d — %.60s",
                           known_age, age_val, fact.content)

    if contradictions:
        logger.info("Detected %d contradictions in %d facts", len(contradictions), len(facts))

    return contradictions


# ── Structured Fields Validation ─────────────────────────────────────────────

STRUCTURED_VALIDATION_SYSTEM = """You are validating structured data fields extracted from web pages.
These fields were extracted by a small model and may contain data from the WRONG person.

You will receive:
1. The TARGET person's confirmed identity (name, age, address)
2. A list of structured data items (company roles, family relations, social profiles)

For each item, determine if it plausibly belongs to the TARGET person.
Consider:
- Age plausibility: Can a person of this age hold this role?
- Location consistency: Does this match their known location?
- Name matching: Is this clearly about the target or someone else?

Return JSON:
{
  "items": [
    {"index": 0, "keep": true/false, "reason": "brief explanation"}
  ]
}

Be strict: a 20-year-old is unlikely to be chairman/ordförande of a major public company.
Board roles at small family companies or local organizations ARE plausible for young people."""


async def validate_structured_fields(person: Person) -> Person:
    """Validate structured Person fields (foretag, familj, social_media) against identity.

    Removes items that clearly belong to a different person.
    """
    age = _compute_age(person.fodelsedatum)
    identity_summary = _build_identity_summary(person)

    # Collect items to validate
    items: list[dict] = []
    item_sources: list[tuple[str, int]] = []  # (field_name, original_index)

    for i, role in enumerate(person.foretag):
        items.append({
            "type": "company_role",
            "company": role.foretag_namn,
            "role": role.roll if isinstance(role.roll, str) else role.roll.value,
            "org_number": role.org_nummer,
        })
        item_sources.append(("foretag", i))

    for i, profile in enumerate(person.social_media):
        items.append({
            "type": "social_profile",
            "platform": profile.platform,
            "username": profile.username,
            "display_name": profile.display_name,
            "bio": profile.bio[:200] if profile.bio else "",
        })
        item_sources.append(("social_media", i))

    if not items:
        return person

    # Build validation prompt
    items_text = "\n".join(
        f"[{i}] {item}" for i, item in enumerate(items)
    )

    content = (
        f"Target person identity:\n{identity_summary}\n\n"
        f"Structured data to validate:\n{items_text}"
    )
    user_prompt = (
        f"For each item, determine if it plausibly belongs to {person.namn} "
        f"(age {age}). Check age plausibility, location, and name consistency."
    )

    try:
        result = await extract_json_synthesis(
            content, STRUCTURED_VALIDATION_SYSTEM, user_prompt,
            max_tokens=2048,
        )
    except Exception as e:
        logger.warning("Structured validation failed, keeping all: %s", e)
        return person

    if not result or not isinstance(result, dict) or "items" not in result:
        logger.warning("Structured validation returned invalid response, keeping all")
        return person

    # Collect indices to remove (process in reverse order to not shift indices)
    remove_foretag: set[int] = set()
    remove_social: set[int] = set()

    for item_result in result["items"]:
        if not isinstance(item_result, dict):
            continue
        idx = item_result.get("index")
        keep = item_result.get("keep", True)
        reason = item_result.get("reason", "")

        if idx is None or idx >= len(item_sources):
            continue

        if not keep:
            field, orig_idx = item_sources[idx]
            if field == "foretag":
                remove_foretag.add(orig_idx)
                logger.info("Removing wrong-person company role: %s at %s (reason: %s)",
                           person.foretag[orig_idx].foretag_namn,
                           person.foretag[orig_idx].roll, reason)
            elif field == "social_media":
                remove_social.add(orig_idx)
                logger.info("Removing wrong-person social profile: %s @%s (reason: %s)",
                           person.social_media[orig_idx].platform,
                           person.social_media[orig_idx].username, reason)

    # Remove in reverse order
    if remove_foretag:
        person.foretag = [r for i, r in enumerate(person.foretag) if i not in remove_foretag]
    if remove_social:
        person.social_media = [p for i, p in enumerate(person.social_media) if i not in remove_social]

    total_removed = len(remove_foretag) + len(remove_social)
    if total_removed:
        logger.info("Structured validation: removed %d items (%d companies, %d social profiles)",
                    total_removed, len(remove_foretag), len(remove_social))

    return person
