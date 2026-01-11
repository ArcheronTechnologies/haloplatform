"""
Entity lifecycle API routes.

Provides endpoints for:
- Merging duplicate entities
- Splitting incorrectly merged entities
- GDPR anonymization
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/lifecycle", tags=["lifecycle"])


# ========== Request/Response Models ==========


class MergeRequest(BaseModel):
    """Request to merge two entities."""

    canonical_entity_id: UUID
    secondary_entity_id: UUID
    merge_reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class MergeResponse(BaseModel):
    """Response from merge operation."""

    success: bool
    canonical_entity_id: UUID
    merged_entity_id: UUID
    same_as_fact_id: Optional[UUID] = None
    facts_preserved: int
    error: Optional[str] = None


class SplitRequest(BaseModel):
    """Request to split an entity."""

    source_entity_id: UUID
    fact_ids_to_move: list[UUID]
    identifier_ids_to_move: list[UUID] = []
    new_entity_name: str
    split_reason: str


class SplitResponse(BaseModel):
    """Response from split operation."""

    success: bool
    original_entity_id: UUID
    new_entity_id: Optional[UUID] = None
    facts_moved: int
    error: Optional[str] = None


class AnonymizeRequest(BaseModel):
    """Request to anonymize an entity."""

    entity_id: UUID
    reason: str
    override_legal_hold: bool = False


class AnonymizeResponse(BaseModel):
    """Response from anonymization."""

    success: bool
    entity_id: UUID
    anonymized_name: str = ""
    fields_anonymized: list[str] = []
    error: Optional[str] = None
    legal_hold: bool = False


class LegalHoldRequest(BaseModel):
    """Request to set/release legal hold."""

    entity_id: UUID
    reason: str
    expires_at: Optional[str] = None


class MergeCandidate(BaseModel):
    """A candidate for merging with an entity."""

    entity_id: UUID
    entity_name: str
    entity_type: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    shared_identifiers: list[str]
    reasons: list[str]


# ========== Merge Endpoints ==========


@router.post("/merge", response_model=MergeResponse)
async def merge_entities(request: MergeRequest):
    """
    Merge two duplicate entities.

    The secondary entity is merged INTO the canonical entity.
    Creates a SAME_AS fact and marks secondary as MERGED.
    All facts and identifiers are preserved.
    """
    if request.canonical_entity_id == request.secondary_entity_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot merge entity with itself",
        )

    # Placeholder - would call lifecycle.merge.EntityMerger
    return MergeResponse(
        success=True,
        canonical_entity_id=request.canonical_entity_id,
        merged_entity_id=request.secondary_entity_id,
        same_as_fact_id=None,
        facts_preserved=0,
    )


@router.post("/merge/undo")
async def undo_merge(
    merged_entity_id: UUID,
    reason: str,
):
    """
    Undo a previous merge operation.

    Restores the merged entity to ACTIVE status.
    """
    # Placeholder - would call lifecycle.merge.EntityMerger.undo_merge()
    return {
        "success": True,
        "entity_id": str(merged_entity_id),
        "status": "ACTIVE",
    }


@router.get("/merge/candidates/{entity_id}", response_model=list[MergeCandidate])
async def get_merge_candidates(
    entity_id: UUID,
    min_score: float = Query(0.8, ge=0.0, le=1.0),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Get potential merge candidates for an entity.

    Returns entities that could be duplicates.
    """
    # Placeholder - would call lifecycle.merge.EntityMerger.get_merge_candidates()
    return []


# ========== Split Endpoints ==========


@router.post("/split", response_model=SplitResponse)
async def split_entity(request: SplitRequest):
    """
    Split an entity into two.

    Creates a new entity with the specified facts/identifiers.
    Used to fix incorrect merges.
    """
    if not request.fact_ids_to_move and not request.identifier_ids_to_move:
        raise HTTPException(
            status_code=400,
            detail="Must specify facts or identifiers to move",
        )

    # Placeholder - would call lifecycle.split.EntitySplitter
    return SplitResponse(
        success=True,
        original_entity_id=request.source_entity_id,
        new_entity_id=None,
        facts_moved=len(request.fact_ids_to_move),
    )


@router.get("/split/preview/{entity_id}")
async def preview_split(
    entity_id: UUID,
    fact_ids: list[UUID] = Query([]),
):
    """
    Preview what a split would look like.

    Returns the state of both entities after split.
    """
    # Placeholder - would call lifecycle.split.EntitySplitter.preview_split()
    return {
        "original_entity": {"id": str(entity_id), "remaining_facts": []},
        "new_entity": {"facts": []},
        "warnings": [],
    }


# ========== Anonymization Endpoints ==========


@router.post("/anonymize", response_model=AnonymizeResponse)
async def anonymize_entity(request: AnonymizeRequest):
    """
    Anonymize an entity (GDPR Article 17).

    Removes PII while preserving graph structure.
    Only works on PERSON entities.
    """
    # Placeholder - would call lifecycle.anonymize.EntityAnonymizer
    return AnonymizeResponse(
        success=True,
        entity_id=request.entity_id,
        anonymized_name="ANONYMIZED_PERSON_XXXXXXXX",
        fields_anonymized=["canonical_name", "personnummer", "birth_date", "gender"],
    )


@router.get("/anonymize/check/{entity_id}")
async def check_can_anonymize(entity_id: UUID):
    """
    Check if an entity can be anonymized.

    Returns whether anonymization is possible and any blockers.
    """
    # Placeholder - would call lifecycle.anonymize.EntityAnonymizer.can_anonymize()
    return {
        "entity_id": str(entity_id),
        "can_anonymize": True,
        "blockers": [],
        "warnings": [],
    }


@router.get("/anonymize/retention-candidates")
async def get_retention_candidates(
    retention_years: int = Query(7, ge=1, le=20),
    limit: int = Query(100, ge=1, le=1000),
):
    """
    Get entities eligible for anonymization by retention policy.

    Returns PERSON entities with no activity beyond retention period.
    """
    # Placeholder - would call lifecycle.anonymize.EntityAnonymizer.get_retention_candidates()
    return {
        "candidates": [],
        "total_eligible": 0,
        "retention_years": retention_years,
    }


# ========== Legal Hold Endpoints ==========


@router.post("/legal-hold/set")
async def set_legal_hold(request: LegalHoldRequest):
    """
    Set a legal hold on an entity.

    Prevents anonymization until hold is released.
    """
    # Placeholder - would call lifecycle.anonymize.EntityAnonymizer.set_legal_hold()
    return {
        "success": True,
        "entity_id": str(request.entity_id),
        "hold_active": True,
        "expires_at": request.expires_at,
    }


@router.post("/legal-hold/release")
async def release_legal_hold(request: LegalHoldRequest):
    """
    Release a legal hold on an entity.

    Allows anonymization to proceed.
    """
    # Placeholder - would call lifecycle.anonymize.EntityAnonymizer.release_legal_hold()
    return {
        "success": True,
        "entity_id": str(request.entity_id),
        "hold_active": False,
    }


@router.get("/legal-hold/{entity_id}")
async def get_legal_hold_status(entity_id: UUID):
    """
    Get legal hold status for an entity.
    """
    # Placeholder
    return {
        "entity_id": str(entity_id),
        "has_hold": False,
        "reason": None,
        "set_at": None,
        "expires_at": None,
    }
