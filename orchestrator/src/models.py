"""Spindeln data models — person-centric intelligence."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class Kon(str, Enum):
    MAN = "man"
    KVINNA = "kvinna"
    OKANT = "okänt"


class RelationType(str, Enum):
    MAKE_MAKA = "make/maka"
    BARN = "barn"
    FORALDER = "förälder"
    SYSKON = "syskon"
    GRANNE = "granne"
    KOLLEGA = "kollega"
    MEDSTYRELSMEDLEM = "medstyrelsemedlem"


class CompanyRoleType(str, Enum):
    STYRELSELEDAMOT = "styrelseledamot"
    VD = "VD"
    ORDFORANDE = "ordförande"
    SUPPLEANT = "suppleant"
    AGARE = "ägare"
    REVISOR = "revisor"


class InvestigationPhase(str, Enum):
    SEED_RESOLUTION = "seed_resolution"
    PUBLIC_RECORDS = "public_records"
    SOCIAL_MEDIA = "social_media"
    WEB_NEWS = "web_news"
    BREACH_CHECK = "breach_check"
    FACT_VALIDATION = "fact_validation"
    DISCOVERY_LOOP = "discovery_loop"
    GRAPH_CONSTRUCTION = "graph_construction"
    REPORT_SYNTHESIS = "report_synthesis"
    EMBEDDING_GENERATION = "embedding_generation"
    LOOM_BRIDGE = "loom_bridge"
    COMPLETE = "complete"


class InvestigationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class SourceType(str, Enum):
    RATSIT = "ratsit"
    HITTA = "hitta"
    ENIRO = "eniro"
    MERINFO = "merinfo"
    BOLAGSVERKET = "bolagsverket"
    ALLABOLAG = "allabolag"
    RIKSDAG = "riksdag"
    POLISEN = "polisen"
    SCB = "scb"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    GITHUB = "github"
    REDDIT = "reddit"
    FLASHBACK = "flashback"
    HIBP = "hibp"
    INTELX = "intelx"
    HUDSONROCK = "hudsonrock"
    AHMIA = "ahmia"
    PASTEBIN = "pastebin"
    GOOGLE_DORK = "google_dork"
    NEWS = "news"
    WEB_SEARCH = "web_search"
    BROTTSPLATSKARTAN = "brottsplatskartan"
    LOOM = "loom"


# ── Sub-models ────────────────────────────────────────────────────────────────

class Address(BaseModel):
    gatuadress: str = ""
    postnummer: str = ""
    ort: str = ""
    kommun: str = ""
    lan: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def __str__(self) -> str:
        parts = [self.gatuadress, self.postnummer, self.ort]
        return ", ".join(p for p in parts if p)


class Income(BaseModel):
    ar: int
    belopp: int  # SEK
    kommun: str = ""


class Tax(BaseModel):
    ar: int
    belopp: int  # SEK


class PaymentRemark(BaseModel):
    datum: Optional[date] = None
    typ: str = ""
    belopp: Optional[int] = None
    borgensman: str = ""


class CompanyRole(BaseModel):
    foretag_namn: str
    org_nummer: str = ""
    roll: CompanyRoleType
    fran: Optional[date] = None
    till: Optional[date] = None


class Property(BaseModel):
    beteckning: str = ""
    typ: str = ""
    kommun: str = ""
    taxeringsvarde: Optional[int] = None
    adress: Optional[Address] = None


class Vehicle(BaseModel):
    registreringsnummer: str = ""
    marke: str = ""
    modell: str = ""
    arsmodell: Optional[int] = None


class FamilyRelation(BaseModel):
    person_namn: str
    person_id: Optional[str] = None
    relation: RelationType


class SocialProfile(BaseModel):
    platform: str
    url: str
    username: str = ""
    display_name: str = ""
    bio: str = ""
    followers: Optional[int] = None
    verified: bool = False
    confidence: float = 0.0  # how sure we are it's the right person


class WebMention(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    datum: Optional[date] = None
    source_type: str = ""


class NewsMention(BaseModel):
    url: str
    title: str
    publication: str = ""
    datum: Optional[date] = None
    snippet: str = ""


class BreachRecord(BaseModel):
    breach_name: str
    breach_date: Optional[date] = None
    exposed_data: list[str] = Field(default_factory=list)  # email, password, etc.
    source: str = ""  # hibp, intelx, etc.
    severity: str = ""  # low, medium, high, critical


class SourcedFact(BaseModel):
    """A single extracted fact with full provenance — inspired by DeepResearch."""
    content: str
    confidence: float = 0.5  # 0.0-1.0 how confident the extraction is
    source_url: str = ""
    source_title: str = ""
    source_type: str = ""  # web_search, news, ratsit, etc.
    quality_score: int = 5  # 0-10 page quality (0=irrelevant, 10=primary source)
    entities: list[str] = Field(default_factory=list)
    relationships: list[dict] = Field(default_factory=list)
    category: Optional[str] = "general"  # identity, professional, financial, social, legal, digital
    discovered_at: datetime = Field(default_factory=datetime.utcnow)


class SourceReference(BaseModel):
    source_type: SourceType
    url: str = ""
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    raw_data: Optional[dict] = None


class CategoryConfidence(BaseModel):
    identity: float = 0.0
    professional: float = 0.0
    financial: float = 0.0
    social: float = 0.0
    digital: float = 0.0
    behavioral: float = 0.0


class PersonEmbeddings(BaseModel):
    identity: Optional[list[float]] = None
    professional: Optional[list[float]] = None
    financial: Optional[list[float]] = None
    social: Optional[list[float]] = None
    digital: Optional[list[float]] = None
    behavioral: Optional[list[float]] = None
    full_profile: Optional[list[float]] = None


# ── Core Entities ─────────────────────────────────────────────────────────────

class Person(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    namn: str
    personnummer: Optional[str] = None
    fodelsedatum: Optional[date] = None
    kon: Kon = Kon.OKANT

    # Living
    adress: Optional[Address] = None
    adress_historik: list[Address] = Field(default_factory=list)

    # Financial
    inkomst: list[Income] = Field(default_factory=list)
    skatt: list[Tax] = Field(default_factory=list)
    betalningsanmarkningar: list[PaymentRemark] = Field(default_factory=list)

    # Employment / business
    arbetsgivare: Optional[str] = None
    foretag: list[CompanyRole] = Field(default_factory=list)

    # Property
    fastigheter: list[Property] = Field(default_factory=list)
    fordon: list[Vehicle] = Field(default_factory=list)

    # Family / connections
    familj: list[FamilyRelation] = Field(default_factory=list)
    grannar: list[str] = Field(default_factory=list)

    # Digital
    social_media: list[SocialProfile] = Field(default_factory=list)
    web_mentions: list[WebMention] = Field(default_factory=list)
    news_mentions: list[NewsMention] = Field(default_factory=list)

    # Breaches
    breaches: list[BreachRecord] = Field(default_factory=list)

    # Extracted facts (DeepResearch-style with provenance + quality scores)
    sourced_facts: list[SourcedFact] = Field(default_factory=list)

    # Meta
    sources: list[SourceReference] = Field(default_factory=list)
    last_updated: Optional[datetime] = None
    confidence: CategoryConfidence = Field(default_factory=CategoryConfidence)
    embeddings: PersonEmbeddings = Field(default_factory=PersonEmbeddings)


class Company(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    namn: str
    org_nummer: str = ""
    bolagsform: str = ""  # AB, HB, EF, etc.
    status: str = ""  # aktivt, avregistrerat, etc.
    registreringsdatum: Optional[date] = None
    adress: Optional[Address] = None
    bransch: str = ""
    styrelse: list[CompanyRole] = Field(default_factory=list)
    omsattning: Optional[int] = None
    resultat: Optional[int] = None
    anstallda: Optional[int] = None
    kreditvardighet: str = ""
    sources: list[SourceReference] = Field(default_factory=list)


# ── Investigation ─────────────────────────────────────────────────────────────

class AgentProgress(BaseModel):
    agent_name: str
    status: str  # running, complete, failed
    facts_found: int = 0
    message: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class InvestigationSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    query: str
    person: Optional[Person] = None
    status: InvestigationStatus = InvestigationStatus.PENDING
    current_phase: InvestigationPhase = InvestigationPhase.SEED_RESOLUTION
    agent_progress: list[AgentProgress] = Field(default_factory=list)
    facts_discovered: int = 0
    entities_discovered: int = 0
    report: Optional[dict] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None


# ── API Request/Response ──────────────────────────────────────────────────────

class InvestigateRequest(BaseModel):
    query: str  # name, personnummer, email, phone
    location: Optional[str] = None  # city hint


class SearchRequest(BaseModel):
    query: str
    category: Optional[str] = None  # identity, professional, financial, etc.
    limit: int = 20


class SearchResult(BaseModel):
    person: Person
    score: float
    match_source: str = ""


class GraphRequest(BaseModel):
    entity_id: str
    depth: int = 2


class TimelineEvent(BaseModel):
    datum: date
    titel: str
    beskrivning: str = ""
    source: SourceType
    category: str = ""  # financial, social, legal, etc.
    url: str = ""


class ProgressEvent(BaseModel):
    """WebSocket progress event sent to frontend."""
    session_id: str
    phase: InvestigationPhase
    agent_name: str = ""
    status: str = ""
    message: str = ""
    facts_found: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
