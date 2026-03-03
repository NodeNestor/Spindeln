"""LLM extraction — prompts + structured extraction from scraped content via vLLM."""

from __future__ import annotations

import json
import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=120.0)
    return _client


async def extract_json(content: str, system_prompt: str,
                       user_prompt: str, *, max_tokens: int = 4096) -> dict | list | None:
    """Send content to vLLM and extract structured JSON.

    Returns parsed JSON or None on failure.
    """
    client = await get_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt + "\n\nContent to analyze:\n" + content[:12000]},
    ]

    try:
        resp = await client.post(
            f"{settings.vllm_url}/chat/completions",
            json={
                "model": settings.vllm_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.1,
            },
            headers={"Authorization": f"Bearer {settings.vllm_api_key}"} if settings.vllm_api_key else {},
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]

        # Extract JSON from possible markdown code blocks
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)

    except json.JSONDecodeError as e:
        logger.warning("LLM returned non-JSON: %s", e)
        return None
    except Exception as e:
        logger.error("LLM extraction failed: %s", e)
        return None


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


async def close():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
