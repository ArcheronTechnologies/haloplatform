"""
Entity resolution API routes.

Provides endpoints for:
- Reviewing pending mentions
- Submitting resolution decisions
- Getting resolution accuracy metrics
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/resolution", tags=["resolution"])


# ========== Request/Response Models ==========


class ResolutionCandidate(BaseModel):
    """A candidate entity for resolution."""

    entity_id: UUID
    entity_name: str
    entity_type: str
    score: float = Field(ge=0.0, le=1.0)
    feature_scores: dict[str, float]
    identifiers: list[str]


class MentionForReview(BaseModel):
    """A mention pending human review."""

    mention_id: UUID
    mention_type: str
    surface_form: str
    normalized_form: str
    extracted_identifiers: dict[str, str]
    source: str
    created_at: str
    candidates: list[ResolutionCandidate]


class ReviewQueueResponse(BaseModel):
    """Response for review queue endpoint."""

    items: list[MentionForReview]
    total_pending: int
    by_type: dict[str, int]


class ResolutionDecisionRequest(BaseModel):
    """Request to submit a resolution decision."""

    mention_id: UUID
    entity_id: Optional[UUID] = None  # None = create new entity
    is_match: bool
    notes: Optional[str] = None


class ResolutionDecisionResponse(BaseModel):
    """Response after submitting decision."""

    mention_id: UUID
    decision: str
    entity_id: UUID
    created_new_entity: bool


class AccuracyMetricsResponse(BaseModel):
    """Resolution accuracy metrics."""

    total_resolved: int
    auto_matched: int
    human_matched: int
    auto_rejected: int
    human_rejected: int
    pending: int
    specificity: float
    sensitivity: float
    precision: float
    f1_score: float


# ========== Endpoints ==========


@router.get("/queue", response_model=ReviewQueueResponse)
async def get_review_queue(
    mention_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Get mentions pending human review.

    Returns mentions where automatic resolution was uncertain
    and human review is needed.
    """
    # Placeholder - would query database for pending mentions
    return ReviewQueueResponse(
        items=[],
        total_pending=0,
        by_type={"PERSON": 0, "COMPANY": 0, "ADDRESS": 0},
    )


@router.post("/decide", response_model=ResolutionDecisionResponse)
async def submit_decision(request: ResolutionDecisionRequest):
    """
    Submit a human resolution decision.

    Either matches a mention to an existing entity or creates a new one.
    """
    # Placeholder - would call resolution.resolver.submit_human_decision()
    if request.is_match and request.entity_id is None:
        raise HTTPException(
            status_code=400,
            detail="entity_id required when is_match=True",
        )

    return ResolutionDecisionResponse(
        mention_id=request.mention_id,
        decision="HUMAN_MATCHED" if request.is_match else "HUMAN_REJECTED",
        entity_id=request.entity_id or UUID("00000000-0000-0000-0000-000000000000"),
        created_new_entity=not request.is_match,
    )


@router.get("/metrics", response_model=AccuracyMetricsResponse)
async def get_accuracy_metrics(
    since: Optional[str] = Query(None, description="Start date (ISO format)"),
):
    """
    Get resolution accuracy metrics.

    Target: >99.5% specificity, >90% sensitivity.
    """
    # Placeholder - would calculate actual metrics
    return AccuracyMetricsResponse(
        total_resolved=0,
        auto_matched=0,
        human_matched=0,
        auto_rejected=0,
        human_rejected=0,
        pending=0,
        specificity=0.0,
        sensitivity=0.0,
        precision=0.0,
        f1_score=0.0,
    )


@router.get("/candidates/{mention_id}", response_model=list[ResolutionCandidate])
async def get_candidates(
    mention_id: UUID,
    min_score: float = Query(0.5, ge=0.0, le=1.0),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Get resolution candidates for a specific mention.

    Returns entities that could potentially match this mention,
    ranked by similarity score.
    """
    # Placeholder - would call resolution.resolver.find_candidates()
    return []


@router.post("/resolve-batch")
async def resolve_batch(
    mention_ids: list[UUID],
    auto_threshold: float = Query(0.95, ge=0.0, le=1.0),
):
    """
    Trigger batch resolution for multiple mentions.

    Mentions above auto_threshold are auto-resolved.
    Others are queued for human review.
    """
    # Placeholder - would call resolution.resolver.resolve_batch()
    return {
        "processed": len(mention_ids),
        "auto_matched": 0,
        "auto_rejected": 0,
        "pending_review": 0,
    }
