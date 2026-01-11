"""
Provenance ORM models aligned with Archeron Ontology.

Provenance tracks the source and extraction method for all data.
Every fact must have provenance for audit trail.
"""

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from halo.models.base import OntologyBase as Base


class SourceType(str, enum.Enum):
    """Types of data sources."""

    BOLAGSVERKET_HVD = "BOLAGSVERKET_HVD"
    BOLAGSVERKET_ANNUAL_REPORT = "BOLAGSVERKET_ANNUAL_REPORT"
    ALLABOLAG_SCRAPE = "ALLABOLAG_SCRAPE"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    DERIVED_COMPUTATION = "DERIVED_COMPUTATION"


class Provenance(Base):
    """
    Provenance table.

    Tracks source and extraction details for all data.
    """

    __tablename__ = "onto_provenances"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Source identification
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_document_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Extraction details
    extraction_method: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    extraction_system_version: Mapped[str] = mapped_column(Text, nullable=False)

    # For derived facts
    derived_from: Mapped[Optional[list]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    derivation_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_provenance_source", "source_type", "source_id"),
    )


class SourceAuthority(Base):
    """
    Source authority configuration.

    Determines which source is authoritative for which predicates.
    Lower authority_level = more authoritative.
    """

    __tablename__ = "onto_source_authority"

    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum", create_type=False),
        primary_key=True,
    )
    fact_predicate: Mapped[str] = mapped_column(Text, primary_key=True)
    authority_level: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("authority_level > 0", name="check_authority_level_positive"),
    )


# Default source authorities as defined in the ontology
DEFAULT_SOURCE_AUTHORITIES = [
    # Bolagsverket HVD is authoritative for company registration data
    {"source_type": SourceType.BOLAGSVERKET_HVD, "fact_predicate": "DIRECTOR_OF", "authority_level": 1},
    {"source_type": SourceType.BOLAGSVERKET_HVD, "fact_predicate": "REGISTERED_AT", "authority_level": 1},
    {"source_type": SourceType.BOLAGSVERKET_HVD, "fact_predicate": "SHAREHOLDER_OF", "authority_level": 2},
    # Annual reports are authoritative for shareholdings
    {"source_type": SourceType.BOLAGSVERKET_ANNUAL_REPORT, "fact_predicate": "SHAREHOLDER_OF", "authority_level": 1},
    # Allabolag scrape is secondary source
    {"source_type": SourceType.ALLABOLAG_SCRAPE, "fact_predicate": "DIRECTOR_OF", "authority_level": 2},
    {"source_type": SourceType.ALLABOLAG_SCRAPE, "fact_predicate": "SHAREHOLDER_OF", "authority_level": 3},
]
