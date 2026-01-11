"""
Mention schemas aligned with Archeron Ontology.

Mentions are raw observations before entity resolution.
They represent what was seen in source data before being
resolved to a canonical entity.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from halo.schemas.entity import EntityType


class ResolutionStatus(str, Enum):
    """Status of mention resolution."""

    PENDING = "PENDING"  # Not yet processed
    AUTO_MATCHED = "AUTO_MATCHED"  # Automatically matched to entity
    HUMAN_MATCHED = "HUMAN_MATCHED"  # Manually confirmed match
    AUTO_REJECTED = "AUTO_REJECTED"  # Automatically rejected (new entity)
    HUMAN_REJECTED = "HUMAN_REJECTED"  # Manually rejected match


class MentionCreate(BaseModel):
    """Schema for creating a new mention."""

    mention_type: EntityType

    # What was observed
    surface_form: str  # Exact text as appeared
    normalized_form: str  # Cleaned version

    # Extracted identifiers (if available)
    extracted_personnummer: Optional[str] = None
    extracted_orgnummer: Optional[str] = None

    # Extracted attributes
    extracted_attributes: dict[str, Any] = Field(default_factory=dict)

    # Source
    provenance_id: UUID
    document_location: Optional[str] = None  # XPath, page number, etc.


class Mention(MentionCreate):
    """Full mention model with ID and resolution status."""

    id: UUID

    # Resolution status
    resolution_status: ResolutionStatus = ResolutionStatus.PENDING
    resolved_to: Optional[UUID] = None  # Entity ID if resolved
    resolution_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    resolution_method: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None  # 'system' or user ID

    created_at: datetime

    class Config:
        from_attributes = True

    @property
    def is_resolved(self) -> bool:
        """Check if mention has been resolved."""
        return self.resolution_status in [
            ResolutionStatus.AUTO_MATCHED,
            ResolutionStatus.HUMAN_MATCHED,
        ]


class ResolutionDecision(BaseModel):
    """Record of a resolution decision for audit trail."""

    id: UUID
    mention_id: UUID
    candidate_entity_id: UUID

    # Scores
    overall_score: float = Field(ge=0.0, le=1.0)
    feature_scores: dict[str, float]  # Individual feature breakdown

    # Decision
    decision: str  # AUTO_MATCH, AUTO_REJECT, HUMAN_MATCH, HUMAN_REJECT, PENDING_REVIEW
    decision_reason: Optional[str] = None

    # Human review (if applicable)
    reviewer_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    created_at: datetime

    class Config:
        from_attributes = True


class ReviewQueueItem(BaseModel):
    """An item in the human review queue."""

    mention_id: UUID
    mention_type: str
    surface_form: str
    normalized_form: str
    extracted_identifiers: dict[str, str]

    # Best candidate
    candidate_entity_id: UUID
    candidate_name: str
    candidate_score: float
    candidate_features: dict[str, float]

    # Other candidates
    alternative_count: int

    created_at: datetime


class ReviewQueueResponse(BaseModel):
    """API response for review queue."""

    items: list[ReviewQueueItem]
    total_pending: int
    by_type: dict[str, int]


class ResolutionDecisionRequest(BaseModel):
    """Request to submit a resolution decision."""

    mention_id: UUID
    entity_id: Optional[UUID] = None  # None if creating new entity
    is_match: bool
    notes: Optional[str] = None


class AccuracyMetrics(BaseModel):
    """Resolution accuracy metrics."""

    total: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int

    # Target: >99.5% specificity, >90% sensitivity
    specificity: float
    sensitivity: float

    # Additional metrics
    precision: float
    f1_score: float

    computed_at: datetime
