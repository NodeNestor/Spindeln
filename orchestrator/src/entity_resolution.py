"""Entity resolution — cross-source person matching using fuzzy name matching,
personnummer-based exact match, and address correlation."""

from __future__ import annotations

import logging
import re

import jellyfish

from src.models import Person, Address

logger = logging.getLogger(__name__)

# Thresholds
NAME_SIMILARITY_THRESHOLD = 0.85
ADDRESS_SIMILARITY_THRESHOLD = 0.80


def normalize_name(name: str) -> str:
    """Normalize a Swedish name for comparison."""
    name = name.strip().lower()
    # Remove common titles
    for title in ["dr", "prof", "ing", "fil"]:
        name = re.sub(rf"\b{title}\.?\s*", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def name_similarity(a: str, b: str) -> float:
    """Compute name similarity using Jaro-Winkler distance."""
    a_norm = normalize_name(a)
    b_norm = normalize_name(b)

    if a_norm == b_norm:
        return 1.0

    # Try Jaro-Winkler on full name
    jw = jellyfish.jaro_winkler_similarity(a_norm, b_norm)

    # Also try matching individual name parts
    a_parts = a_norm.split()
    b_parts = b_norm.split()

    if len(a_parts) > 1 and len(b_parts) > 1:
        # Match first and last name separately
        first_sim = jellyfish.jaro_winkler_similarity(a_parts[0], b_parts[0])
        last_sim = jellyfish.jaro_winkler_similarity(a_parts[-1], b_parts[-1])
        parts_sim = (first_sim + last_sim) / 2
        jw = max(jw, parts_sim)

    return jw


def personnummer_match(a: str | None, b: str | None) -> bool:
    """Exact match on personnummer (after normalization)."""
    if not a or not b:
        return False
    a_clean = re.sub(r"[^0-9]", "", a)
    b_clean = re.sub(r"[^0-9]", "", b)
    # Handle both YYYYMMDDXXXX and YYMMDDXXXX formats
    if len(a_clean) == 12:
        a_clean = a_clean[2:]  # Strip century
    if len(b_clean) == 12:
        b_clean = b_clean[2:]
    return len(a_clean) >= 10 and a_clean == b_clean


def address_similarity(a: Address | None, b: Address | None) -> float:
    """Compute similarity between two addresses."""
    if not a or not b:
        return 0.0

    score = 0.0
    weights = 0.0

    if a.gatuadress and b.gatuadress:
        score += jellyfish.jaro_winkler_similarity(
            a.gatuadress.lower(), b.gatuadress.lower()) * 3
        weights += 3

    if a.postnummer and b.postnummer:
        score += (1.0 if a.postnummer.replace(" ", "") == b.postnummer.replace(" ", "") else 0.0) * 2
        weights += 2

    if a.ort and b.ort:
        score += jellyfish.jaro_winkler_similarity(a.ort.lower(), b.ort.lower()) * 1
        weights += 1

    return score / weights if weights > 0 else 0.0


def is_same_person(a: Person, b: Person) -> tuple[bool, float]:
    """Determine if two Person records refer to the same individual.

    Returns (is_match, confidence_score).
    """
    # Exact match on personnummer is definitive
    if personnummer_match(a.personnummer, b.personnummer):
        return True, 1.0

    score = 0.0
    max_score = 0.0

    # Name similarity (weight: 4)
    ns = name_similarity(a.namn, b.namn)
    score += ns * 4
    max_score += 4

    # Birth date match (weight: 3)
    if a.fodelsedatum and b.fodelsedatum:
        if a.fodelsedatum == b.fodelsedatum:
            score += 3
        max_score += 3

    # Address match (weight: 2)
    addr_sim = address_similarity(a.adress, b.adress)
    score += addr_sim * 2
    max_score += 2

    # Gender match (weight: 1)
    if a.kon != "okänt" and b.kon != "okänt":
        score += (1.0 if a.kon == b.kon else 0.0)
        max_score += 1

    confidence = score / max_score if max_score > 0 else 0.0
    return confidence >= 0.75, confidence


def deduplicate_persons(persons: list[Person]) -> list[Person]:
    """Merge duplicate Person records in a list."""
    if len(persons) <= 1:
        return persons

    merged: list[Person] = []
    used = set()

    for i, p in enumerate(persons):
        if i in used:
            continue
        current = p
        for j in range(i + 1, len(persons)):
            if j in used:
                continue
            is_match, conf = is_same_person(current, persons[j])
            if is_match:
                current = _merge(current, persons[j])
                used.add(j)
        merged.append(current)

    return merged


def _merge(base: Person, other: Person) -> Person:
    """Merge two person records into one."""
    from src.investigate import _merge_person
    return _merge_person(base, other)
