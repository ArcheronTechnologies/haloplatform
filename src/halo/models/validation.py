"""
Validation and resolution configuration ORM models.

For accuracy measurement and resolution threshold configuration.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from halo.models.base import OntologyBase as Base

if TYPE_CHECKING:
    from halo.models.entity import Entity


class GroundTruthType(str, enum.Enum):
    """Types of ground truth data sources."""

    PERSONNUMMER_MATCH = "PERSONNUMMER_MATCH"
    ORGNUMMER_MATCH = "ORGNUMMER_MATCH"
    SYNTHETIC = "SYNTHETIC"
    EKOBROTTSMYNDIGHETEN = "EKOBROTTSMYNDIGHETEN"


class ResolutionConfig(Base):
    """
    Resolution configuration per mention type.

    Defines auto-match, human-review, and auto-reject thresholds.
    """

    __tablename__ = "onto_resolution_config"

    mention_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    auto_match_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    human_review_min: Mapped[float] = mapped_column(Float, nullable=False)
    auto_reject_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            "auto_match_threshold > human_review_min",
            name="check_match_threshold",
        ),
        CheckConstraint(
            "human_review_min >= auto_reject_threshold",
            name="check_review_threshold",
        ),
    )

    def should_auto_match(self, score: float) -> bool:
        """Check if score exceeds auto-match threshold."""
        return score >= self.auto_match_threshold

    def should_auto_reject(self, score: float) -> bool:
        """Check if score is below auto-reject threshold."""
        return score < self.auto_reject_threshold

    def needs_human_review(self, score: float) -> bool:
        """Check if score requires human review."""
        return self.auto_reject_threshold <= score < self.auto_match_threshold


class ValidationGroundTruth(Base):
    """
    Ground truth data for accuracy measurement.

    Stores known same/different entity pairs from various sources.
    """

    __tablename__ = "onto_validation_ground_truth"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    ground_truth_type: Mapped[GroundTruthType] = mapped_column(
        Enum(GroundTruthType, name="ground_truth_type"), nullable=False
    )
    entity_a_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), nullable=False
    )
    entity_b_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), nullable=False
    )
    is_same_entity: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    entity_a: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[entity_a_id]
    )
    entity_b: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[entity_b_id]
    )

    __table_args__ = (
        Index("idx_ground_truth_type", "ground_truth_type"),
    )
