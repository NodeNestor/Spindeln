"""Multi-category embedding generation for Person entities.

Creates 7 category-specific embeddings per person by:
1. Generating a natural-language summary per category
2. Embedding each summary with SentenceTransformer
"""

from __future__ import annotations

import logging

import numpy as np

from src.models import Person, PersonEmbeddings

logger = logging.getLogger(__name__)

# Lazy-loaded embedder
_embedder = None
_use_local = True


def _get_embedder():
    global _embedder, _use_local
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer("all-mpnet-base-v2", device="cuda")
        except ImportError:
            logger.warning("sentence-transformers not installed, embeddings disabled")
            _use_local = False
            return None
    return _embedder


def _embed(text: str) -> list[float] | None:
    """Embed a single text, return as list of floats (or None if unavailable)."""
    if not _use_local:
        return None
    model = _get_embedder()
    if model is None:
        return None
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


# ── Category Summaries ────────────────────────────────────────────────────────

def _identity_summary(p: Person) -> str:
    parts = [f"Name: {p.namn}"]
    if p.fodelsedatum:
        parts.append(f"Born: {p.fodelsedatum}")
    if p.kon != "okänt":
        parts.append(f"Gender: {p.kon}")
    if p.adress:
        parts.append(f"Lives in: {p.adress}")
    if p.personnummer:
        parts.append(f"Has personnummer on file")
    return ". ".join(parts)


def _professional_summary(p: Person) -> str:
    parts = []
    if p.arbetsgivare:
        parts.append(f"Employer: {p.arbetsgivare}")
    for role in p.foretag:
        parts.append(f"{role.roll.value} at {role.foretag_namn}")
    if not parts:
        parts.append(f"{p.namn} — no known company affiliations")
    return ". ".join(parts)


def _financial_summary(p: Person) -> str:
    parts = []
    for inc in sorted(p.inkomst, key=lambda x: x.ar, reverse=True)[:3]:
        parts.append(f"Income {inc.ar}: {inc.belopp:,} SEK")
    for tax in sorted(p.skatt, key=lambda x: x.ar, reverse=True)[:3]:
        parts.append(f"Tax {tax.ar}: {tax.belopp:,} SEK")
    if p.betalningsanmarkningar:
        parts.append(f"{len(p.betalningsanmarkningar)} payment remark(s)")
    for prop in p.fastigheter:
        if prop.taxeringsvarde:
            parts.append(f"Property {prop.beteckning}: {prop.taxeringsvarde:,} SEK")
    if not parts:
        parts.append(f"{p.namn} — no financial data available")
    return ". ".join(parts)


def _social_summary(p: Person) -> str:
    parts = []
    for rel in p.familj:
        parts.append(f"{rel.relation.value}: {rel.person_namn}")
    if p.grannar:
        parts.append(f"Neighbors: {', '.join(p.grannar[:5])}")
    if not parts:
        parts.append(f"{p.namn} — no known social connections")
    return ". ".join(parts)


def _digital_summary(p: Person) -> str:
    parts = []
    for profile in p.social_media:
        parts.append(f"{profile.platform}: @{profile.username or profile.display_name}")
    if p.breaches:
        parts.append(f"Found in {len(p.breaches)} data breach(es)")
    if not parts:
        parts.append(f"{p.namn} — no known digital presence")
    return ". ".join(parts)


def _behavioral_summary(p: Person) -> str:
    parts = []
    if p.news_mentions:
        parts.append(f"Mentioned in {len(p.news_mentions)} news article(s)")
        for nm in p.news_mentions[:3]:
            parts.append(f"  - {nm.title}")
    if p.web_mentions:
        parts.append(f"Found in {len(p.web_mentions)} web mention(s)")
    if not parts:
        parts.append(f"{p.namn} — no public activity detected")
    return ". ".join(parts)


def _full_summary(p: Person) -> str:
    """Combine all category summaries."""
    return " | ".join([
        _identity_summary(p),
        _professional_summary(p),
        _financial_summary(p),
        _social_summary(p),
        _digital_summary(p),
    ])


# ── Main Function ─────────────────────────────────────────────────────────────

async def generate_embeddings(person: Person) -> Person:
    """Generate all 7 category embeddings for a person."""
    try:
        person.embeddings = PersonEmbeddings(
            identity=_embed(_identity_summary(person)),
            professional=_embed(_professional_summary(person)),
            financial=_embed(_financial_summary(person)),
            social=_embed(_social_summary(person)),
            digital=_embed(_digital_summary(person)),
            behavioral=_embed(_behavioral_summary(person)),
            full_profile=_embed(_full_summary(person)),
        )
        logger.info("Generated 7 embeddings for %s", person.namn)
    except Exception as e:
        logger.error("Embedding generation failed for %s: %s", person.namn, e)

    return person
