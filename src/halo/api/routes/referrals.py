"""
Referral generation API routes.

Provides endpoints for generating referrals to various Swedish authorities:
- EBM (Ekobrottsmyndigheten)
- Skatteverket
- Försäkringskassan
- FIU
- IVO
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from halo.api.deps import AuditRepo, User
from halo.referral import (
    Authority,
    ReferralPipeline,
    AuthorityRouter,
    ReferralResult,
)

router = APIRouter()

# Initialize pipeline (in production, inject via DI)
_pipeline = ReferralPipeline()
_authority_router = AuthorityRouter()


class ReferralRequest(BaseModel):
    """Request to generate a referral."""

    case_id: UUID = Field(..., description="Case to generate referral for")
    target_authority: str = Field(
        ..., description="Target authority code (ebm, skv, fk, fiu, ivo)"
    )
    priority: str = Field(
        default="normal",
        description="Priority level: low, normal, high, urgent"
    )
    include_evidence: bool = Field(
        default=True,
        description="Whether to include evidence package"
    )


class ReferralResponse(BaseModel):
    """Response containing generated referral."""

    id: UUID
    case_id: UUID
    authority: str
    authority_name: str
    status: str
    created_at: datetime
    priority: str
    document_count: int
    total_value_sek: float


class ReferralRoutingResponse(BaseModel):
    """Response from routing analysis."""

    case_id: UUID
    recommended_authorities: list[str]
    reasoning: dict


@router.post("/generate", response_model=ReferralResponse)
async def generate_referral(
    request: ReferralRequest,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Generate a referral package for a case.

    Creates a formatted referral package suitable for submission
    to the specified Swedish authority.
    """
    try:
        authority = Authority(request.target_authority.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid authority: {request.target_authority}. "
            f"Valid options: ebm, skv, fk, fiu, ivo",
        )

    # Generate referral
    package = await _pipeline.generate_referral(
        case_id=request.case_id,
        authority=authority,
        priority=request.priority,
        user_id=str(user.user_id),
    )

    if not package:
        raise HTTPException(
            status_code=400,
            detail="Failed to generate referral. Case may not have sufficient evidence.",
        )

    # Log the referral generation
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="generate_referral",
        resource_type="referral",
        resource_id=package.id,
        details={
            "case_id": str(request.case_id),
            "authority": authority.value,
            "priority": request.priority,
        },
    )

    return ReferralResponse(
        id=package.id,
        case_id=package.case_id,
        authority=package.authority.value,
        authority_name=package.authority.name,
        status=package.status,
        created_at=package.created_at,
        priority=package.priority,
        document_count=len(package.documents),
        total_value_sek=package.total_value_sek,
    )


@router.get("/route/{case_id}", response_model=ReferralRoutingResponse)
async def route_case(
    case_id: UUID,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Analyze which authorities a case should be referred to.

    Returns recommended authorities based on case characteristics,
    evidence types, and threshold analysis.
    """
    routing = await _authority_router.analyze_case(case_id)

    if not routing:
        raise HTTPException(
            status_code=404,
            detail="Case not found or insufficient data for routing",
        )

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="analyze_routing",
        resource_type="case",
        resource_id=case_id,
    )

    return ReferralRoutingResponse(
        case_id=case_id,
        recommended_authorities=routing.recommended_authorities,
        reasoning=routing.reasoning,
    )


@router.get("/{referral_id}", response_model=ReferralResponse)
async def get_referral(
    referral_id: UUID,
    audit_repo: AuditRepo,
    user: User,
):
    """Get details of a generated referral."""
    package = await _pipeline.get_referral(referral_id)

    if not package:
        raise HTTPException(status_code=404, detail="Referral not found")

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="referral",
        resource_id=referral_id,
    )

    return ReferralResponse(
        id=package.id,
        case_id=package.case_id,
        authority=package.authority.value,
        authority_name=package.authority.name,
        status=package.status,
        created_at=package.created_at,
        priority=package.priority,
        document_count=len(package.documents),
        total_value_sek=package.total_value_sek,
    )


@router.get("", response_model=list[ReferralResponse])
async def list_referrals(
    audit_repo: AuditRepo,
    user: User,
    case_id: Optional[UUID] = Query(None, description="Filter by case"),
    authority: Optional[str] = Query(None, description="Filter by authority"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
):
    """List referrals with optional filtering."""
    packages = await _pipeline.list_referrals(
        case_id=case_id,
        authority=Authority(authority) if authority else None,
        status=status,
        limit=limit,
    )

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="list",
        resource_type="referrals",
        details={"count": len(packages)},
    )

    return [
        ReferralResponse(
            id=p.id,
            case_id=p.case_id,
            authority=p.authority.value,
            authority_name=p.authority.name,
            status=p.status,
            created_at=p.created_at,
            priority=p.priority,
            document_count=len(p.documents),
            total_value_sek=p.total_value_sek,
        )
        for p in packages
    ]


@router.post("/{referral_id}/submit")
async def submit_referral(
    referral_id: UUID,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Submit a referral to the target authority.

    This marks the referral as submitted and records the submission
    for impact tracking.
    """
    result = await _pipeline.submit_referral(
        referral_id=referral_id,
        submitted_by=str(user.user_id),
    )

    if not result:
        raise HTTPException(
            status_code=400,
            detail="Failed to submit referral. May already be submitted or invalid.",
        )

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="submit_referral",
        resource_type="referral",
        resource_id=referral_id,
        justification="Referral submitted to authority",
    )

    return {"status": "submitted", "referral_id": str(referral_id)}
