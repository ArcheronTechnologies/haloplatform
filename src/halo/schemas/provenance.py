"""
Provenance schemas aligned with Archeron Ontology.

Provenance tracks the source and extraction method for all data.
Every fact must have provenance for audit trail.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Types of data sources."""

    BOLAGSVERKET_HVD = "BOLAGSVERKET_HVD"  # Bolagsverket High-Value Dataset
    BOLAGSVERKET_ANNUAL_REPORT = "BOLAGSVERKET_ANNUAL_REPORT"  # iXBRL annual reports
    ALLABOLAG_SCRAPE = "ALLABOLAG_SCRAPE"  # Allabolag web scraper
    MANUAL_ENTRY = "MANUAL_ENTRY"  # Manual data entry
    DERIVED_COMPUTATION = "DERIVED_COMPUTATION"  # Computed from other facts


class ProvenanceCreate(BaseModel):
    """Schema for creating a provenance record."""

    # Source identification
    source_type: SourceType
    source_id: str  # API response ID, document URL, etc.
    source_url: Optional[str] = None
    source_document_hash: Optional[str] = None  # SHA-256

    # Extraction details
    extraction_method: str
    extraction_timestamp: datetime
    extraction_system_version: str

    # For derived facts
    derived_from: Optional[list[UUID]] = None
    derivation_rule: Optional[str] = None


class Provenance(ProvenanceCreate):
    """Full provenance model with ID."""

    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class SourceAuthority(BaseModel):
    """
    Source authority configuration.

    Determines which source is authoritative for which predicates.
    Lower authority_level = more authoritative.
    """

    source_type: SourceType
    fact_predicate: str
    authority_level: int  # Lower = more authoritative


# Default source authorities per the ontology
DEFAULT_SOURCE_AUTHORITIES = [
    SourceAuthority(
        source_type=SourceType.BOLAGSVERKET_HVD,
        fact_predicate="DIRECTOR_OF",
        authority_level=1,
    ),
    SourceAuthority(
        source_type=SourceType.BOLAGSVERKET_HVD,
        fact_predicate="REGISTERED_AT",
        authority_level=1,
    ),
    SourceAuthority(
        source_type=SourceType.BOLAGSVERKET_HVD,
        fact_predicate="SHAREHOLDER_OF",
        authority_level=2,
    ),
    SourceAuthority(
        source_type=SourceType.BOLAGSVERKET_ANNUAL_REPORT,
        fact_predicate="SHAREHOLDER_OF",
        authority_level=1,
    ),
    SourceAuthority(
        source_type=SourceType.ALLABOLAG_SCRAPE,
        fact_predicate="DIRECTOR_OF",
        authority_level=2,
    ),
    SourceAuthority(
        source_type=SourceType.ALLABOLAG_SCRAPE,
        fact_predicate="SHAREHOLDER_OF",
        authority_level=3,
    ),
]


def get_authority_level(source_type: SourceType, predicate: str) -> int:
    """
    Get authority level for a source/predicate combination.

    Returns 999 if not found (lowest authority).
    """
    for auth in DEFAULT_SOURCE_AUTHORITIES:
        if auth.source_type == source_type and auth.fact_predicate == predicate:
            return auth.authority_level
    return 999


def resolve_conflict(
    fact1_source: SourceType,
    fact1_timestamp: datetime,
    fact2_source: SourceType,
    fact2_timestamp: datetime,
    predicate: str,
) -> int:
    """
    Resolve conflict between two facts.

    Returns:
        1 if fact1 wins
        2 if fact2 wins

    Rules:
    1. Source with lower authority_level wins
    2. If equal authority, most recent extraction_timestamp wins
    """
    auth1 = get_authority_level(fact1_source, predicate)
    auth2 = get_authority_level(fact2_source, predicate)

    if auth1 < auth2:
        return 1
    elif auth2 < auth1:
        return 2
    else:
        # Equal authority - most recent wins
        return 1 if fact1_timestamp >= fact2_timestamp else 2
