"""
Mention ORM models aligned with Archeron Ontology.

Mentions are raw observations before entity resolution.
They represent what was seen in source data before being
resolved to a canonical entity.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from halo.models.base import OntologyBase as Base

if TYPE_CHECKING:
    from halo.models.entity import Entity, EntityType
    from halo.models.provenance import Provenance


class ResolutionStatus(str, enum.Enum):
    """Status of mention resolution."""

    PENDING = "PENDING"
    AUTO_MATCHED = "AUTO_MATCHED"
    HUMAN_MATCHED = "HUMAN_MATCHED"
    AUTO_REJECTED = "AUTO_REJECTED"
    HUMAN_REJECTED = "HUMAN_REJECTED"


class Mention(Base):
    """
    Mention table.

    Raw observations before entity resolution.
    """

    __tablename__ = "onto_mentions"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    mention_type: Mapped[str] = mapped_column(Text, nullable=False)

    # What was observed
    surface_form: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_form: Mapped[str] = mapped_column(Text, nullable=False)

    # Extracted identifiers (if available)
    extracted_personnummer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_orgnummer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Extracted attributes
    extracted_attributes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    # Source
    provenance_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_provenances.id"), nullable=False
    )
    document_location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Resolution status
    resolution_status: Mapped[ResolutionStatus] = mapped_column(
        Enum(ResolutionStatus, name="resolution_status_enum"),
        nullable=False,
        default=ResolutionStatus.PENDING,
    )
    resolved_to: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), nullable=True
    )
    resolution_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolution_method: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    provenance: Mapped["Provenance"] = relationship("Provenance")
    entity: Mapped[Optional["Entity"]] = relationship("Entity")

    __table_args__ = (
        CheckConstraint(
            "mention_type IN ('PERSON', 'COMPANY', 'ADDRESS')",
            name="check_mention_type",
        ),
        CheckConstraint(
            "(resolution_confidence IS NULL) OR (resolution_confidence >= 0 AND resolution_confidence <= 1)",
            name="check_resolution_confidence",
        ),
        Index(
            "idx_mentions_pending",
            "mention_type",
            postgresql_where="resolution_status = 'PENDING'",
        ),
        Index(
            "idx_mentions_resolved",
            "resolved_to",
            postgresql_where="resolved_to IS NOT NULL",
        ),
    )

    @property
    def is_resolved(self) -> bool:
        """Check if mention has been resolved."""
        return self.resolution_status in [
            ResolutionStatus.AUTO_MATCHED,
            ResolutionStatus.HUMAN_MATCHED,
        ]


class ResolutionDecision(Base):
    """
    Resolution decision log.

    For audit trail and accuracy measurement.
    """

    __tablename__ = "onto_resolution_decisions"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    mention_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_mentions.id"), nullable=False
    )
    candidate_entity_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), nullable=False
    )

    # Scores
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    feature_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Decision
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Human review (if applicable)
    reviewer_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    mention: Mapped["Mention"] = relationship("Mention")
    candidate_entity: Mapped["Entity"] = relationship("Entity")

    __table_args__ = (
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 1",
            name="check_overall_score",
        ),
        CheckConstraint(
            "decision IN ('AUTO_MATCH', 'AUTO_REJECT', 'HUMAN_MATCH', 'HUMAN_REJECT', 'PENDING_REVIEW')",
            name="check_decision_value",
        ),
        Index(
            "idx_resolution_pending",
            "decision",
            postgresql_where="decision = 'PENDING_REVIEW'",
        ),
    )
