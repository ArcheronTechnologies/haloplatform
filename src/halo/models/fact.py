"""
Fact ORM model aligned with Archeron Ontology.

Facts are assertions about entities:
- Attributes (single entity properties)
- Relationships (connections between entities)

All facts have temporality (valid_from/valid_to) and provenance.
"""

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from halo.models.base import OntologyBase as Base

if TYPE_CHECKING:
    from halo.models.entity import Entity
    from halo.models.provenance import Provenance


class FactType(str, enum.Enum):
    """Types of facts."""

    ATTRIBUTE = "ATTRIBUTE"
    RELATIONSHIP = "RELATIONSHIP"


class Predicate(str, enum.Enum):
    """Valid predicates for facts (MVP)."""

    # Relationship predicates
    DIRECTOR_OF = "DIRECTOR_OF"
    SHAREHOLDER_OF = "SHAREHOLDER_OF"
    REGISTERED_AT = "REGISTERED_AT"
    SAME_AS = "SAME_AS"

    # Attribute predicates (for derived facts)
    RISK_SCORE = "RISK_SCORE"
    SHELL_INDICATOR = "SHELL_INDICATOR"
    DIRECTOR_VELOCITY = "DIRECTOR_VELOCITY"
    NETWORK_CLUSTER = "NETWORK_CLUSTER"


class Fact(Base):
    """
    Fact table.

    All assertions about entities and relationships.
    Each fact has temporality (valid_from/valid_to) and full provenance.
    """

    __tablename__ = "onto_facts"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    fact_type: Mapped[FactType] = mapped_column(
        Enum(FactType, name="fact_type_enum"), nullable=False
    )

    # Subject (always required)
    subject_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), nullable=False
    )

    # Predicate
    predicate: Mapped[str] = mapped_column(Text, nullable=False)

    # For ATTRIBUTE facts - value columns
    value_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_int: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    value_float: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    value_bool: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    value_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # For RELATIONSHIP facts
    object_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), nullable=True
    )
    relationship_attributes: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )

    # Temporality (day-level)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Confidence and provenance
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    provenance_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_provenances.id"), nullable=False
    )

    # Lifecycle
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    superseded_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_facts.id"), nullable=True
    )
    superseded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # For derived facts
    is_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    derivation_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    derived_from: Mapped[Optional[list]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )

    # Relationships
    subject: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[subject_id], back_populates="subject_facts"
    )
    object: Mapped[Optional["Entity"]] = relationship(
        "Entity", foreign_keys=[object_id], back_populates="object_facts"
    )
    provenance: Mapped["Provenance"] = relationship("Provenance")

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="check_fact_confidence"
        ),
        # Relationship facts must have object_id
        CheckConstraint(
            "(fact_type != 'RELATIONSHIP') OR (object_id IS NOT NULL)",
            name="check_relationship_has_object",
        ),
        # MVP relationship predicate constraint
        CheckConstraint(
            "(fact_type != 'RELATIONSHIP') OR (predicate IN ('DIRECTOR_OF', 'SHAREHOLDER_OF', 'REGISTERED_AT', 'SAME_AS'))",
            name="check_valid_relationship_predicate",
        ),
        Index(
            "idx_facts_subject",
            "subject_id",
            "predicate",
            postgresql_where="superseded_by IS NULL",
        ),
        Index(
            "idx_facts_object",
            "object_id",
            "predicate",
            postgresql_where="superseded_by IS NULL AND object_id IS NOT NULL",
        ),
        Index(
            "idx_facts_temporal",
            "valid_from",
            "valid_to",
            postgresql_where="superseded_by IS NULL",
        ),
        Index(
            "idx_facts_derived",
            "is_derived",
            "derivation_rule",
            postgresql_where="is_derived = TRUE",
        ),
    )

    @property
    def is_current(self) -> bool:
        """Check if this fact is currently valid."""
        return self.superseded_by is None and (
            self.valid_to is None or self.valid_to >= date.today()
        )

    @property
    def value(self):
        """Get the fact's value (whichever is set)."""
        if self.value_text is not None:
            return self.value_text
        if self.value_int is not None:
            return self.value_int
        if self.value_float is not None:
            return self.value_float
        if self.value_date is not None:
            return self.value_date
        if self.value_bool is not None:
            return self.value_bool
        if self.value_json is not None:
            return self.value_json
        return None
