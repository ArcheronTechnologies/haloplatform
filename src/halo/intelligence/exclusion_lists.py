"""
Exclusion Lists for Fraud Detection.

Entities that legitimately appear across many companies and should not be
flagged as suspicious formation agents or nominees.

Categories:
1. Audit firms - legitimate auditors of many companies
2. Private equity firms - portfolio company directors
3. Law firms - corporate law, M&A advisory
4. Banks - custody, trust services
5. Corporate service providers - company formation, nominee services (licensed)
"""

import re
from typing import Optional


# ============================================================================
# AUDIT FIRMS
# ============================================================================
# Exclude from serial director detection - they audit many companies legitimately

AUDIT_FIRMS = [
    # Big 4
    "ernst & young",
    "ey",
    "öhrlings pricewaterhousecoopers",
    "pwc",
    "pricewaterhousecoopers",
    "kpmg",
    "deloitte",
    # Major Swedish firms
    "grant thornton",
    "bdo",
    "rsm",
    "mazars",
    "forvis mazars",
    "baker tilly",
    # Mid-size Swedish firms
    "azets",
    "azets revision",
    "frejs revisorer",
    "finnhammars",
    "finnhammars revision",
    "nexia",
    "moore sweden",
    "crowe",
    "pk revision",
    "revisionsbyrån i",
    "revisionsbyrå",
    # Known auditor patterns
    "revision ab",
    "revisorer ab",
    "auktoriserad revisor",
]


# ============================================================================
# PRIVATE EQUITY / VENTURE CAPITAL
# ============================================================================
# Legitimately have directors/board seats across portfolio companies

PE_VC_FIRMS = [
    # Major Swedish PE
    "eqt",
    "eqt partners",
    "nordic capital",
    "investor ab",
    "patricia industries",
    "industrivärden",
    "ratos",
    "kinnevik",
    "melker schörling",
    "lundberg",
    "lundbergföretagen",
    "wallenberg",
    "fam ab",
    "stena",
    "stena sessan",
    "varenne",
    "altor",
    "triton",
    "ica gruppen",
    # Major VC
    "creandum",
    "northzone",
    "atomico",
    "sequoia heritage",
    "general atlantic",
    "balderton",
    "accel",
    "insight partners",
    "verdane",
    # Growth equity
    "summa equity",
    "adelis",
    "axcel",
    "valedo partners",
    # Holding company patterns
    "holding ab",
    "invest ab",
    "förvaltning ab",
    "investment ab",
]


# ============================================================================
# LAW FIRMS
# ============================================================================
# Often serve as board members, signatories for M&A

LAW_FIRMS = [
    # Magic Circle / International
    "freshfields",
    "linklaters",
    "clifford chance",
    "allen & overy",
    "a&o shearman",
    "white & case",
    "baker mckenzie",
    "dla piper",
    "dentons",
    "hogan lovells",
    "latham & watkins",
    # Major Swedish
    "mannheimer swartling",
    "vinge",
    "setterwalls",
    "roschier",
    "lindahl",
    "delphi",
    "cederquist",
    "hamilton",
    "hannes snellman",
    "gernandt & danielsson",
    "wistrand",
    "cirio",
    "advokatbyrå",
    "advokatfirma",
    # Patterns
    "advokat",
    "law firm",
    "attorneys",
    "juridik ab",
]


# ============================================================================
# BANKS / FINANCIAL INSTITUTIONS
# ============================================================================
# Custody services, trust administration

BANKS = [
    # Swedish banks
    "handelsbanken",
    "seb",
    "skandinaviska enskilda banken",
    "nordea",
    "swedbank",
    "danske bank",
    "dnb",
    "länsförsäkringar",
    # International banks
    "hsbc",
    "barclays",
    "deutsche bank",
    "bnp paribas",
    "credit suisse",
    "ubs",
    "jp morgan",
    "goldman sachs",
    "morgan stanley",
    "citibank",
    # Specialized
    "carnegie",
    "pareto",
    "abg sundal collier",
    "avanza",
    "nordnet",
]


# ============================================================================
# CORPORATE SERVICE PROVIDERS
# ============================================================================
# Licensed company formation, nominee directors

CORPORATE_SERVICE_PROVIDERS = [
    # Major providers
    "bolagsplatsen",
    "bolagsverket",
    "startabolag",
    "lagerbolag",
    "bolagsstiftarna",
    "företagsplatsen",
    "snabbstart",
    # Formation agents
    "lagerbolag ab",
    "termino",
    "bolagsjuristen",
    "bolagsservice",
]


# ============================================================================
# GOVERNMENT / PUBLIC SECTOR
# ============================================================================
# State ownership, municipal companies

GOVERNMENT_ENTITIES = [
    # Swedish state
    "regeringskansliet",
    "näringsdepartementet",
    "statens",
    "riksgälden",
    "fortifikationsverket",
    # State-owned companies
    "vattenfall",
    "postnord",
    "sj ab",
    "systembolaget",
    "sveaskog",
    "akademiska hus",
    "specialfastigheter",
    "samhall",
    "svedab",
    # Municipal patterns
    "kommun",
    "region",
    "landsting",
    "kommunalt",
]


# ============================================================================
# LOOKUP FUNCTIONS
# ============================================================================

def _compile_patterns(pattern_list: list[str]) -> list[re.Pattern]:
    """Compile patterns for efficient matching."""
    return [re.compile(re.escape(p), re.IGNORECASE) for p in pattern_list]


# Pre-compiled patterns
_AUDIT_PATTERNS = _compile_patterns(AUDIT_FIRMS)
_PE_PATTERNS = _compile_patterns(PE_VC_FIRMS)
_LAW_PATTERNS = _compile_patterns(LAW_FIRMS)
_BANK_PATTERNS = _compile_patterns(BANKS)
_CSP_PATTERNS = _compile_patterns(CORPORATE_SERVICE_PROVIDERS)
_GOV_PATTERNS = _compile_patterns(GOVERNMENT_ENTITIES)


def is_excluded_entity(name: str) -> Optional[str]:
    """
    Check if an entity name matches an exclusion list.

    Returns:
        Category string if excluded, None if not excluded
    """
    if not name:
        return None

    name_lower = name.lower()

    for pattern in _AUDIT_PATTERNS:
        if pattern.search(name_lower):
            return "audit_firm"

    for pattern in _PE_PATTERNS:
        if pattern.search(name_lower):
            return "pe_vc"

    for pattern in _LAW_PATTERNS:
        if pattern.search(name_lower):
            return "law_firm"

    for pattern in _BANK_PATTERNS:
        if pattern.search(name_lower):
            return "bank"

    for pattern in _CSP_PATTERNS:
        if pattern.search(name_lower):
            return "corporate_service"

    for pattern in _GOV_PATTERNS:
        if pattern.search(name_lower):
            return "government"

    return None


def should_exclude_from_serial_director(name: str) -> bool:
    """Check if entity should be excluded from serial director detection."""
    category = is_excluded_entity(name)
    return category in ("audit_firm", "pe_vc", "law_firm", "bank", "government")


def should_exclude_from_address_cluster(name: str) -> bool:
    """Check if entity should be excluded from address cluster detection."""
    # Corporate service providers legitimately have many companies at same address
    category = is_excluded_entity(name)
    return category in ("corporate_service", "government")


def get_exclusion_stats(names: list[str]) -> dict:
    """Get statistics on excluded entities."""
    from collections import Counter

    categories = Counter()
    excluded = []
    not_excluded = []

    for name in names:
        category = is_excluded_entity(name)
        if category:
            categories[category] += 1
            excluded.append((name, category))
        else:
            not_excluded.append(name)

    return {
        "total": len(names),
        "excluded": len(excluded),
        "not_excluded": len(not_excluded),
        "by_category": dict(categories),
        "excluded_entities": excluded[:20],  # Sample
    }
