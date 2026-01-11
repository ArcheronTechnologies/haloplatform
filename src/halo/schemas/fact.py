"""
Fact schemas aligned with Archeron Ontology.

Facts are assertions about entities:
- Attributes (single entity properties)
- Relationships (connections between entities)

All facts have temporality (valid_from/valid_to) and provenance.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field


class FactType(str, Enum):
    """Types of facts."""

    ATTRIBUTE = "ATTRIBUTE"  # Property of a single entity
    RELATIONSHIP = "RELATIONSHIP"  # Connection between two entities


class Predicate(str, Enum):
    """Valid predicates for facts (MVP)."""

    # Relationship predicates
    DIRECTOR_OF = "DIRECTOR_OF"  # Person directs company
    SHAREHOLDER_OF = "SHAREHOLDER_OF"  # Person/company owns company
    REGISTERED_AT = "REGISTERED_AT"  # Company registered at address
    SAME_AS = "SAME_AS"  # Entity merge (same-as link)

    # Attribute predicates (for derived facts)
    RISK_SCORE = "RISK_SCORE"  # Computed risk score
    SHELL_INDICATOR = "SHELL_INDICATOR"  # Shell company indicator
    DIRECTOR_VELOCITY = "DIRECTOR_VELOCITY"  # Director change rate
    NETWORK_CLUSTER = "NETWORK_CLUSTER"  # Network cluster assignment


class FactCreate(BaseModel):
    """Schema for creating a new fact."""

    fact_type: FactType
    subject_id: UUID
    predicate: Predicate

    # Value columns (use appropriate one based on predicate)
    value_text: Optional[str] = None
    value_int: Optional[int] = None
    value_float: Optional[float] = None
    value_date: Optional[date] = None
    value_bool: Optional[bool] = None
    value_json: Optional[dict[str, Any]] = None

    # For RELATIONSHIP facts
    object_id: Optional[UUID] = None
    relationship_attributes: Optional[dict[str, Any]] = None

    # Temporality (day-level)
    valid_from: date
    valid_to: Optional[date] = None  # NULL = current

    # Confidence and provenance
    confidence: float = Field(ge=0.0, le=1.0)
    provenance_id: UUID

    # For derived facts
    is_derived: bool = False
    derivation_rule: Optional[str] = None
    derived_from: Optional[list[UUID]] = None


class FactUpdate(BaseModel):
    """Schema for updating a fact (superseding)."""

    # New values
    value_text: Optional[str] = None
    value_int: Optional[int] = None
    value_float: Optional[float] = None
    value_date: Optional[date] = None
    value_bool: Optional[bool] = None
    value_json: Optional[dict[str, Any]] = None

    # New temporality
    valid_to: Optional[date] = None

    # Supersession
    superseded_by: Optional[UUID] = None


class Fact(FactCreate):
    """Full fact model with ID and timestamps."""

    id: UUID
    created_at: datetime

    # Lifecycle
    superseded_by: Optional[UUID] = None
    superseded_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @property
    def is_current(self) -> bool:
        """Check if this fact is currently valid."""
        return self.superseded_by is None and (
            self.valid_to is None or self.valid_to >= date.today()
        )

    @property
    def value(self) -> Union[str, int, float, date, bool, dict, None]:
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


class DirectorshipFact(BaseModel):
    """Convenience schema for DIRECTOR_OF facts."""

    person_id: UUID
    company_id: UUID
    role: str = "director"  # director, board_member, ceo, etc.
    valid_from: date
    valid_to: Optional[date] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_id: UUID


class ShareholdingFact(BaseModel):
    """Convenience schema for SHAREHOLDER_OF facts."""

    owner_id: UUID  # Person or company
    company_id: UUID
    ownership_percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    share_count: Optional[int] = None
    valid_from: date
    valid_to: Optional[date] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_id: UUID


class RegistrationFact(BaseModel):
    """Convenience schema for REGISTERED_AT facts."""

    company_id: UUID
    address_id: UUID
    registration_type: str = "registered"  # registered, postal, visiting
    valid_from: date
    valid_to: Optional[date] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_id: UUID


class SameAsFact(BaseModel):
    """Convenience schema for SAME_AS facts (entity merge)."""

    secondary_entity_id: UUID  # Entity being merged
    canonical_entity_id: UUID  # Entity merged into
    merge_reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    provenance_id: UUID
