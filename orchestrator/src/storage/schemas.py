"""Graph entity and relation type definitions for HiveMindDB.

Defines the schema/vocabulary used when storing Spindeln data
in HiveMindDB's knowledge graph.
"""

# ── Entity Types ──────────────────────────────────────────────────────────────

ENTITY_PERSON = "Person"
ENTITY_COMPANY = "Company"
ENTITY_ADDRESS = "Address"
ENTITY_PROPERTY = "Property"
ENTITY_SOCIAL_PROFILE = "SocialProfile"
ENTITY_NEWS_ARTICLE = "NewsArticle"
ENTITY_BREACH = "BreachRecord"
ENTITY_VEHICLE = "Vehicle"
ENTITY_LOOM_EVENT = "LoomEvent"

ALL_ENTITY_TYPES = [
    ENTITY_PERSON, ENTITY_COMPANY, ENTITY_ADDRESS, ENTITY_PROPERTY,
    ENTITY_SOCIAL_PROFILE, ENTITY_NEWS_ARTICLE, ENTITY_BREACH,
    ENTITY_VEHICLE, ENTITY_LOOM_EVENT,
]

# ── Relation Types ────────────────────────────────────────────────────────────

# Person → X
REL_LIVES_AT = "lives_at"
REL_LIVED_AT = "lived_at"
REL_WORKS_AT = "works_at"
REL_OWNS = "owns"
REL_DRIVES = "drives"
REL_HAS_PROFILE = "has_profile"
REL_MENTIONED_IN = "mentioned_in"
REL_EXPOSED_IN = "exposed_in"

# Person → Person
REL_FAMILY = "family"
REL_SPOUSE = "spouse"
REL_PARENT = "parent"
REL_CHILD = "child"
REL_SIBLING = "sibling"
REL_NEIGHBOR = "neighbor"
REL_CO_DIRECTOR = "co_director"

# Person → Company (roles)
REL_BOARD_MEMBER = "board_member"
REL_CEO = "ceo"
REL_CHAIRMAN = "chairman"
REL_OWNER = "owner"
REL_EMPLOYEE = "employee"

# Company → X
REL_REGISTERED_AT = "registered_at"
REL_SAME_ADDRESS = "same_address"
REL_SHARED_DIRECTOR = "shared_director"

# News
REL_MENTIONS_PERSON = "mentions_person"
REL_MENTIONS_COMPANY = "mentions_company"

ALL_RELATION_TYPES = [
    REL_LIVES_AT, REL_LIVED_AT, REL_WORKS_AT, REL_OWNS, REL_DRIVES,
    REL_HAS_PROFILE, REL_MENTIONED_IN, REL_EXPOSED_IN,
    REL_FAMILY, REL_SPOUSE, REL_PARENT, REL_CHILD, REL_SIBLING,
    REL_NEIGHBOR, REL_CO_DIRECTOR,
    REL_BOARD_MEMBER, REL_CEO, REL_CHAIRMAN, REL_OWNER, REL_EMPLOYEE,
    REL_REGISTERED_AT, REL_SAME_ADDRESS, REL_SHARED_DIRECTOR,
    REL_MENTIONS_PERSON, REL_MENTIONS_COMPANY,
]


# ── Tag Vocabulary ────────────────────────────────────────────────────────────

TAG_PERSON = "person"
TAG_COMPANY = "company"
TAG_FINANCIAL = "financial"
TAG_PROPERTY = "property"
TAG_FAMILY = "family"
TAG_SOCIAL = "social"
TAG_NEWS = "news"
TAG_BREACH = "breach"
TAG_ADDRESS = "address"
TAG_VEHICLE = "vehicle"
TAG_POLITICAL = "political"
TAG_CRIMINAL = "criminal"


def role_to_relation(role: str) -> str:
    """Map a Swedish company role to a HiveMindDB relation type."""
    mapping = {
        "styrelseledamot": REL_BOARD_MEMBER,
        "VD": REL_CEO,
        "ordförande": REL_CHAIRMAN,
        "suppleant": REL_BOARD_MEMBER,
        "ägare": REL_OWNER,
        "revisor": REL_BOARD_MEMBER,
    }
    return mapping.get(role, REL_EMPLOYEE)


def family_to_relation(relation: str) -> str:
    """Map a Swedish family relation to a HiveMindDB relation type."""
    mapping = {
        "make/maka": REL_SPOUSE,
        "barn": REL_CHILD,
        "förälder": REL_PARENT,
        "syskon": REL_SIBLING,
        "granne": REL_NEIGHBOR,
    }
    return mapping.get(relation, REL_FAMILY)
