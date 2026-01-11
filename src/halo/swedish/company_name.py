"""
Swedish company name normalization utilities.

Normalizes company names for matching and deduplication:
- Legal form standardization (Aktiebolag -> AB)
- Status indicator removal (I LIKVIDATION, I KONKURS)
- Noise removal (punctuation, extra whitespace)
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class NormalizedCompanyName:
    """Result of company name normalization."""

    original: str
    normalized: str
    legal_form: Optional[str] = None
    legal_form_full: Optional[str] = None
    status_indicator: Optional[str] = None
    base_name: str = ""

    @property
    def matching_key(self) -> str:
        """Return key suitable for fuzzy matching."""
        return self.normalized.lower()


# Legal form mappings
LEGAL_FORMS = {
    "AKTIEBOLAG": "AB",
    "AKTIEBOLAGET": "AB",
    "HANDELSBOLAG": "HB",
    "HANDELSBOLAGET": "HB",
    "KOMMANDITBOLAG": "KB",
    "KOMMANDITBOLAGET": "KB",
    "ENSKILD FIRMA": "EF",
    "EKONOMISK FÖRENING": "EK FÖR",
    "EKONOMISKA FÖRENINGEN": "EK FÖR",
    "BOSTADSRÄTTSFÖRENING": "BRF",
    "BOSTADSRÄTTSFÖRENINGEN": "BRF",
    "IDEELL FÖRENING": "IDEELL FÖR",
    "STIFTELSE": "STIFT",
    "STIFTELSEN": "STIFT",
}

# Reverse mapping for display
LEGAL_FORM_FULL_NAMES = {
    "AB": "Aktiebolag",
    "HB": "Handelsbolag",
    "KB": "Kommanditbolag",
    "EF": "Enskild Firma",
    "EK FÖR": "Ekonomisk Förening",
    "BRF": "Bostadsrättsförening",
    "IDEELL FÖR": "Ideell Förening",
    "STIFT": "Stiftelse",
}

# Status indicators to remove
STATUS_INDICATORS = [
    r"\bI LIKVIDATION\b",
    r"\bI KONKURS\b",
    r"\bUNDER REKONSTRUKTION\b",
    r"\bUNDER AVVECKLING\b",
    r"\bAVVECKLAD\b",
    r"\bUPPLÖST\b",
    r"\bSTRUKEN\b",
]

# Common noise patterns
NOISE_PATTERNS = [
    r"\bSVERIGE\b",
    r"\bSVENSK\b",
    r"\bSVENSKA\b",
    r"\bNORDIC\b",
    r"\bSCANDINAVIA\b",
    r"\bINTERNATIONAL\b",
    r"\bGLOBAL\b",
]


def normalize_company_name(name: str) -> NormalizedCompanyName:
    """
    Normalize a Swedish company name for matching.

    Args:
        name: Raw company name

    Returns:
        NormalizedCompanyName with normalized form and extracted metadata
    """
    if not name:
        return NormalizedCompanyName(
            original="",
            normalized="",
            base_name="",
        )

    original = name
    working = name.upper().strip()

    # Extract status indicator
    status_indicator = None
    for pattern in STATUS_INDICATORS:
        match = re.search(pattern, working)
        if match:
            status_indicator = match.group(0).strip()
            working = re.sub(pattern, "", working)
            break

    # Extract and normalize legal form
    legal_form = None
    legal_form_full = None

    # First check for full legal form names
    for full_name, abbrev in LEGAL_FORMS.items():
        pattern = rf"\b{re.escape(full_name)}\b"
        if re.search(pattern, working):
            legal_form = abbrev
            legal_form_full = LEGAL_FORM_FULL_NAMES.get(abbrev)
            working = re.sub(pattern, "", working)
            break

    # Then check for abbreviations at end of name
    if not legal_form:
        for abbrev in ["AB", "HB", "KB", "EF"]:
            # Match at end or followed by status indicators
            if re.search(rf"\b{abbrev}\b\s*$", working):
                legal_form = abbrev
                legal_form_full = LEGAL_FORM_FULL_NAMES.get(abbrev)
                working = re.sub(rf"\b{abbrev}\b\s*$", "", working)
                break

    # Remove punctuation except apostrophes in names
    working = re.sub(r"[^\w\s']", " ", working)

    # Normalize whitespace
    working = re.sub(r"\s+", " ", working).strip()

    # Remove trailing/leading articles
    working = re.sub(r"^(THE|DEN|DET|DE)\s+", "", working)
    working = re.sub(r"\s+(THE|DEN|DET|DE)$", "", working)

    base_name = working

    # Create final normalized form
    if legal_form:
        normalized = f"{working} {legal_form}".strip()
    else:
        normalized = working

    return NormalizedCompanyName(
        original=original,
        normalized=normalized,
        legal_form=legal_form,
        legal_form_full=legal_form_full,
        status_indicator=status_indicator,
        base_name=base_name,
    )


def company_names_match(
    name1: str,
    name2: str,
    fuzzy_threshold: float = 0.85,
) -> tuple[bool, float]:
    """
    Check if two company names refer to the same company.

    Args:
        name1: First company name
        name2: Second company name
        fuzzy_threshold: Minimum similarity for fuzzy match

    Returns:
        Tuple of (is_match, similarity_score)
    """
    norm1 = normalize_company_name(name1)
    norm2 = normalize_company_name(name2)

    # Exact match on normalized form
    if norm1.matching_key == norm2.matching_key:
        return True, 1.0

    # Base names must match for legal form variants to match
    if norm1.base_name.lower() == norm2.base_name.lower():
        # Same base name, different legal forms is NOT a match
        # (e.g., "Acme AB" != "Acme HB")
        if norm1.legal_form and norm2.legal_form and norm1.legal_form != norm2.legal_form:
            return False, 0.5

        # One has legal form, other doesn't - likely same company
        return True, 0.95

    # Fuzzy matching for typos/variations
    try:
        from difflib import SequenceMatcher

        similarity = SequenceMatcher(
            None,
            norm1.matching_key,
            norm2.matching_key,
        ).ratio()

        if similarity >= fuzzy_threshold:
            return True, similarity
    except ImportError:
        pass

    return False, 0.0


def extract_legal_form(name: str) -> Optional[str]:
    """
    Extract legal form abbreviation from company name.

    Args:
        name: Company name

    Returns:
        Legal form abbreviation (AB, HB, KB, etc.) or None
    """
    result = normalize_company_name(name)
    return result.legal_form


def format_company_name(name: str, include_legal_form: bool = True) -> str:
    """
    Format a company name for display.

    Args:
        name: Raw company name
        include_legal_form: Whether to include legal form

    Returns:
        Formatted company name
    """
    result = normalize_company_name(name)

    # Title case the base name
    formatted = result.base_name.title()

    if include_legal_form and result.legal_form:
        formatted = f"{formatted} {result.legal_form}"

    return formatted


def is_holding_company(name: str) -> bool:
    """
    Check if company name suggests a holding company.

    Holding companies are often shell-like and used for ownership structures.

    Args:
        name: Company name

    Returns:
        True if name suggests holding company
    """
    upper = name.upper()

    holding_patterns = [
        r"\bHOLDING\b",
        r"\bHOLDINGS\b",
        r"\bINVEST\b",
        r"\bINVESTMENT\b",
        r"\bINVESTMENTS\b",
        r"\bFÖRVALTNING\b",
        r"\bKAPITAL\b",
        r"\bCAPITAL\b",
        r"\bGROUP\b",
        r"\bGRUPP\b",
        r"\bKONCERN\b",
    ]

    return any(re.search(pattern, upper) for pattern in holding_patterns)


def is_consulting_company(name: str) -> bool:
    """
    Check if company name suggests a consulting company.

    Consulting is a common SNI code for shell companies.

    Args:
        name: Company name

    Returns:
        True if name suggests consulting company
    """
    upper = name.upper()

    consulting_patterns = [
        r"\bCONSULT\b",
        r"\bCONSULTING\b",
        r"\bKONSULT\b",
        r"\bRÅDGIVNING\b",
        r"\bADVISORY\b",
        r"\bMANAGEMENT\b",
    ]

    return any(re.search(pattern, upper) for pattern in consulting_patterns)
