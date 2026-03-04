"""LLM extraction — prompts + structured extraction from scraped content via vLLM."""

from __future__ import annotations

import json
import logging
import re

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=120.0)
    return _client


def _repair_json(text: str) -> dict | list | None:
    """Try to parse JSON, repairing common LLM output issues.

    Handles truncated JSON (from token limits), trailing commas, markdown
    fences, and mixed text/JSON output.
    """
    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first { or [
    start = -1
    for i, c in enumerate(text):
        if c in "{[":
            start = i
            break
    if start == -1:
        return None

    text = text[start:]

    # Track bracket stack for proper closing of truncated JSON
    stack: list[str] = []
    in_string = False
    escape = False
    end = len(text)
    complete = False

    for i, c in enumerate(text):
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c in "{[":
            stack.append("}" if c == "{" else "]")
        elif c in "}]":
            if stack:
                stack.pop()
            if not stack:
                end = i + 1
                complete = True
                break

    candidate = text[:end]

    # Try parsing the complete candidate
    if complete:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # Remove trailing commas before } or ]
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # If truncated (stack not empty), try to close open structures
    if stack:
        fixed = candidate
        # Close any open string
        if in_string:
            fixed += '"'
        # Remove any trailing partial key/value (truncated mid-token)
        # Strip back to the last complete value
        fixed = re.sub(r',\s*"[^"]*$', '', fixed)  # trailing incomplete key
        fixed = re.sub(r':\s*"[^"]*$', ': ""', fixed)  # trailing incomplete string value
        fixed = re.sub(r':\s*$', ': null', fixed)  # trailing incomplete value
        # Remove trailing commas
        fixed = re.sub(r',\s*$', '', fixed)
        # Close remaining brackets in reverse order
        fixed += "".join(reversed(stack))
        # Remove trailing commas before closers
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # More aggressive: find the last complete item in the top-level array/object
        # and truncate there
        try:
            # Find the last successful parse point by progressively removing trailing content
            for trim_re in [
                r',\s*\{[^{}]*$',       # remove last incomplete object in array
                r',\s*\[[^\[\]]*$',      # remove last incomplete array element
                r',\s*"[^"]*"\s*:\s*\{[^{}]*$',  # remove last incomplete key:object
            ]:
                trimmed = re.sub(trim_re, '', fixed)
                if trimmed != fixed:
                    # Re-close brackets
                    trimmed_stack = []
                    in_str = False
                    esc = False
                    for c in trimmed:
                        if esc:
                            esc = False
                            continue
                        if c == '\\':
                            esc = True
                            continue
                        if c == '"' and not esc:
                            in_str = not in_str
                            continue
                        if in_str:
                            continue
                        if c in '{[':
                            trimmed_stack.append('}' if c == '{' else ']')
                        elif c in '}]' and trimmed_stack:
                            trimmed_stack.pop()
                    trimmed += "".join(reversed(trimmed_stack))
                    trimmed = re.sub(r',\s*([}\]])', r'\1', trimmed)
                    result = json.loads(trimmed)
                    return result
        except (json.JSONDecodeError, Exception):
            pass

    return None


async def _call_llm(api_url: str, model: str, api_key: str,
                    messages: list[dict], max_tokens: int,
                    temperature: float = 0.1,
                    timeout: float = 120.0,
                    extra_body: dict | None = None) -> dict | list | None:
    """Low-level LLM call shared by bulk and synthesis paths."""
    client = await get_client()
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if extra_body:
        body.update(extra_body)
    try:
        resp = await client.post(
            f"{api_url}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        text = msg.get("content") or msg.get("reasoning_content") or ""
        if not text:
            logger.warning("LLM returned empty content (model=%s)", model)
            return None

        result = _repair_json(text)
        if result is None:
            logger.warning("LLM returned unparseable response (model=%s, len=%d): %.300s", model, len(text), text)
        return result

    except Exception as e:
        logger.error("LLM call failed (%s): [%s] %s", model, type(e).__name__, e)
        return None


def _build_messages(content: str, system_prompt: str, user_prompt: str,
                    max_content: int = 12000) -> list[dict]:
    if not isinstance(content, str):
        content = str(content)
    # Reinforce JSON-only output for small models
    system = system_prompt + "\n\nIMPORTANT: Output ONLY valid JSON. No commentary, no explanation, no markdown fences."
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt + "\n\nContent to analyze:\n" + content[:max_content]},
    ]


async def extract_json(content: str, system_prompt: str,
                       user_prompt: str, *, max_tokens: int = 4096) -> dict | list | None:
    """Send content to bulk extraction model and extract structured JSON."""
    messages = _build_messages(content, system_prompt, user_prompt)
    return await _call_llm(
        api_url=settings.bulk_api_url,
        model=settings.bulk_model,
        api_key=settings.bulk_api_key,
        messages=messages,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


async def extract_json_synthesis(content: str, system_prompt: str,
                                 user_prompt: str, *, max_tokens: int = 0) -> dict | list | None:
    """Send content to synthesis model (bigger/smarter) and extract structured JSON."""
    if max_tokens <= 0:
        max_tokens = settings.synthesis_max_tokens
    messages = _build_messages(content, system_prompt, user_prompt, max_content=30000)
    return await _call_llm(
        api_url=settings.synthesis_api_url,
        model=settings.synthesis_model,
        api_key=settings.synthesis_api_key,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.3,
        timeout=600.0,  # synthesis can take much longer (reasoning models)
    )


# ── Domain-Specific Extraction Prompts ────────────────────────────────────────

PERSON_EXTRACT_SYSTEM = """You are a Swedish data extraction specialist. Extract structured person data from the provided webpage content.

Return a JSON object with these fields (omit fields with no data):
{
  "namn": "Full Name",
  "personnummer": "YYYYMMDD-XXXX",
  "fodelsedatum": "YYYY-MM-DD",
  "kon": "man|kvinna",
  "adress": {"gatuadress": "", "postnummer": "", "ort": "", "kommun": ""},
  "adress_historik": [{"gatuadress": "", "postnummer": "", "ort": ""}],
  "inkomst": [{"ar": 2023, "belopp": 450000, "kommun": "Stockholm"}],
  "skatt": [{"ar": 2023, "belopp": 150000}],
  "betalningsanmarkningar": [{"datum": "2023-01-15", "typ": "Kronofogden", "belopp": 50000}],
  "arbetsgivare": "Company Name",
  "foretag": [{"foretag_namn": "", "org_nummer": "", "roll": "styrelseledamot|VD|ordförande|suppleant|ägare|revisor"}],
  "fastigheter": [{"beteckning": "", "typ": "", "kommun": "", "taxeringsvarde": 0}],
  "familj": [{"person_namn": "Name", "relation": "make/maka|barn|förälder|syskon"}],
  "grannar": ["Name 1", "Name 2"],
  "telefon": "070-XXXXXXX"
}

Only include data you can clearly extract. Do not invent or guess."""


SOCIAL_PROFILE_EXTRACT_SYSTEM = """You are analyzing a social media profile page. Extract the profile information.

Return JSON:
{
  "username": "",
  "display_name": "",
  "bio": "",
  "followers": null,
  "following": null,
  "posts_count": null,
  "location": "",
  "website": "",
  "verified": false,
  "recent_posts": ["brief summary of recent posts"]
}

Only include data clearly present on the page."""


SOCIAL_VERIFY_SYSTEM = """You are verifying if a social media profile belongs to a specific person.

Given:
- Person's known data (name, age, city, occupation)
- Social media profile data

Return JSON:
{
  "is_match": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of why this is/isn't the same person"
}

Consider: name similarity, location match, age consistency, occupation match, mutual connections."""


NEWS_EXTRACT_SYSTEM = """You are extracting mentions of a specific person from a news article.

Return JSON:
{
  "mentions_person": true/false,
  "person_role": "What role does the person play in the article?",
  "summary": "Brief summary of the article relevant to this person",
  "other_people_mentioned": ["Name 1", "Name 2"],
  "companies_mentioned": ["Company 1"],
  "dates_mentioned": ["YYYY-MM-DD"],
  "sentiment": "positive|negative|neutral"
}"""


COMPANY_EXTRACT_SYSTEM = """You are extracting Swedish company data from a webpage.

Return JSON:
{
  "namn": "Company Name",
  "org_nummer": "XXXXXX-XXXX",
  "bolagsform": "AB|HB|EF|etc",
  "status": "aktivt|avregistrerat",
  "registreringsdatum": "YYYY-MM-DD",
  "adress": {"gatuadress": "", "postnummer": "", "ort": ""},
  "bransch": "",
  "styrelse": [{"person_namn": "", "roll": "styrelseledamot|VD|ordförande"}],
  "omsattning": null,
  "resultat": null,
  "anstallda": null,
  "kreditvardighet": ""
}"""


BREACH_EXTRACT_SYSTEM = """You are analyzing breach/leak data related to a person.

Return JSON:
{
  "breaches": [
    {
      "breach_name": "",
      "breach_date": "YYYY-MM-DD",
      "exposed_data": ["email", "password", "phone"],
      "severity": "low|medium|high|critical"
    }
  ],
  "paste_mentions": [
    {
      "source": "pastebin/ghostbin/etc",
      "date": "YYYY-MM-DD",
      "content_summary": ""
    }
  ]
}"""


async def extract_person_data(content: str, query_context: str = "") -> dict | None:
    """Extract person data from scraped page content."""
    return await extract_json(
        content,
        PERSON_EXTRACT_SYSTEM,
        f"Extract all person data from this Swedish public records page.{f' Looking for: {query_context}' if query_context else ''}",
    )


async def extract_social_profile(content: str) -> dict | None:
    """Extract social media profile data."""
    return await extract_json(content, SOCIAL_PROFILE_EXTRACT_SYSTEM,
                              "Extract the social media profile information.")


async def verify_social_match(person_summary: str, profile_data: str) -> dict | None:
    """Verify if a social profile matches a known person."""
    return await extract_json(
        profile_data,
        SOCIAL_VERIFY_SYSTEM,
        f"Known person data:\n{person_summary}\n\nDoes this profile belong to them?",
    )


async def extract_news_mention(content: str, person_name: str) -> dict | None:
    """Extract person mentions from a news article."""
    return await extract_json(
        content,
        NEWS_EXTRACT_SYSTEM,
        f"Find mentions of '{person_name}' in this news article.",
    )


async def extract_company_data(content: str) -> dict | None:
    """Extract company data from a business registry page."""
    return await extract_json(content, COMPANY_EXTRACT_SYSTEM,
                              "Extract company data from this page.")


async def extract_breach_data(content: str, person_context: str = "") -> dict | None:
    """Extract breach/leak data."""
    return await extract_json(
        content,
        BREACH_EXTRACT_SYSTEM,
        f"Analyze breach/leak data.{f' Person context: {person_context}' if person_context else ''}",
    )


# ── DeepResearch-Style Per-Page Fact Extraction ──────────────────────────────

PAGE_FACT_EXTRACT_SYSTEM = """You extract ALL useful knowledge about a specific person from web pages. Output JSON only.

CRITICAL — IDENTITY VERIFICATION:
- This page may contain data about MULTIPLE people with similar names.
- ONLY extract facts clearly about the TARGET person (identified in the user prompt).
- If the page shows a list of search results with multiple people, only extract data for the matching person.
- Do NOT extract template data, example data, or "how to use this site" content.
- Do NOT extract data from page sidebars, ads, or sections about other people.
- If unsure whether data belongs to the target person, set confidence to 0.3 or lower.
- Use the IDENTITY ANCHORS provided (birth date, address, personnummer) to verify which data belongs to the target.

GOOD facts (specific, verifiable, about the TARGET person):
- "Zephyr Moonstone is 35 years old, born 1990-03-22"
- "Lives at Storgatan 12, Kalmar"
- "Board member of Moonstone AB (org 556123-4567) since 2021"
- "Deklarerad inkomst: 380,000 SEK (2023)"
- "Mentioned in Aftonbladet article about tech startups, 2024-05-15"
- "Instagram profile: @zephyr.m, 1200 followers, bio says entrepreneur"
- "Neighbor: Erik Johansson at same address"

BAD facts (do NOT extract):
- "The page discusses someone" (meta, not knowledge)
- "No information found" (absence is not knowledge)
- "Someone with a similar name" (uncertain identity)
- Template/example data shown in site tutorials
- Data from page headers/footers about other people
- Generic site statistics or visitor counts

Return JSON:
{
  "quality": 0-10,
  "relevant": true/false,
  "facts": [
    {"fact": "Specific statement", "confidence": 0.9, "category": "identity"}
  ],
  "entities": [
    {"name": "Entity Name", "type": "person|company|address|organization"}
  ],
  "relationships": [
    {"source": "entity1", "target": "entity2", "type": "works_at|lives_in|family"}
  ],
  "summary": "Brief summary"
}

Categories: identity, professional, financial, social, legal, digital, personal, general
Quality: 0=not about this person, 5=some info, 10=primary source

Extract EVERY fact you can find about the TARGET person. Be thorough — include names, numbers, dates, amounts, addresses, relationships, roles, everything. But ONLY for the target person."""


async def extract_page_facts(content: str, person_name: str,
                              person_context: str = "", source_url: str = "",
                              source_title: str = "",
                              identity_anchors: dict | None = None) -> dict | None:
    """DeepResearch-style per-page fact extraction with quality scoring.

    Returns structured facts, entities, and relationships from a single page.
    Uses a smaller content window and token limit to avoid truncation with small models.
    """
    user_prompt = (
        f"Extract ALL facts about '{person_name}' from this page.\n"
    )

    # Add identity anchors for disambiguation
    if identity_anchors:
        user_prompt += "\nTARGET PERSON IDENTITY (use to verify data belongs to them):\n"
        user_prompt += f"- Name: {person_name}\n"
        if identity_anchors.get("birth_date"):
            user_prompt += f"- Born: {identity_anchors['birth_date']}\n"
        if identity_anchors.get("address"):
            user_prompt += f"- Address: {identity_anchors['address']}\n"
        if identity_anchors.get("personnummer"):
            user_prompt += f"- Personnummer: {identity_anchors['personnummer']}\n"
        if identity_anchors.get("age"):
            user_prompt += f"- Age: {identity_anchors['age']}\n"
        user_prompt += "Use these to determine if page content refers to THIS person or someone else.\n"

    if person_context:
        user_prompt += f"Known context: {person_context}\n"
    if source_url:
        user_prompt += f"Source URL: {source_url}\n"

    result = await extract_json(
        content, PAGE_FACT_EXTRACT_SYSTEM, user_prompt,
        max_tokens=4096,
    )

    if result and isinstance(result, dict):
        # Inject source metadata into each fact
        for fact in result.get("facts", []):
            fact["source_url"] = source_url
            fact["source_title"] = source_title
        return result
    return None


# ── Fact Deduplication ────────────────────────────────────────────────────────

def normalize_fact(text: str) -> str:
    """Normalize fact text for deduplication — lowercase, strip, remove trailing punct."""
    t = text.strip().lower().rstrip(".")
    return " ".join(t.split())


def is_duplicate_fact(key: str, seen: set) -> bool:
    """Check if a normalized fact is a duplicate — exact match OR substring of existing."""
    if key in seen:
        return True
    for existing in seen:
        shorter, longer = (key, existing) if len(key) <= len(existing) else (existing, key)
        if shorter in longer:
            return True
    return False


def deduplicate_facts(facts: list) -> list:
    """Deduplicate a list of SourcedFact objects by normalized content."""
    seen: set[str] = set()
    unique = []
    for f in facts:
        key = normalize_fact(f.content if hasattr(f, 'content') else str(f))
        if not key or is_duplicate_fact(key, seen):
            continue
        seen.add(key)
        unique.append(f)
    return unique


# ── Temporal Scoring ─────────────────────────────────────────────────────────

def score_fact_recency(discovered_at) -> float:
    """Score a fact by recency — exponential decay with 6-month half-life.

    Returns 0.0 (very old) to 1.0 (very recent). None dates get 0.5.
    """
    from datetime import datetime, timezone
    if not discovered_at:
        return 0.5
    try:
        now = datetime.utcnow()
        if hasattr(discovered_at, 'timestamp'):
            age_days = (now - discovered_at).days
        else:
            return 0.5
        if age_days < 0:
            return 1.0
        return 0.5 ** (age_days / 180)  # 6-month half-life
    except Exception:
        return 0.5


async def close():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
