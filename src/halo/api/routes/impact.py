"""
Impact tracking API routes.

Provides endpoints for:
- Recording referral outcomes
- Viewing impact metrics
- Tracking effectiveness over time
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from halo.api.deps import AuditRepo, User
from halo.impact import (
    ImpactTracker,
    ImpactRecord,
    ImpactType,
    ImpactMetrics,
    MetricsCalculator,
)

router = APIRouter()

# Initialize tracker (in production, inject via DI)
_tracker = ImpactTracker()
_calculator = MetricsCalculator(_tracker)


class RecordImpactRequest(BaseModel):
    """Request to record an impact event."""

    referral_id: Optional[UUID] = Field(None, description="Associated referral")
    case_id: Optional[UUID] = Field(None, description="Associated case")
    impact_type: str = Field(..., description="Type of impact event")
    authority: str = Field(..., description="Authority that reported the outcome")
    description: str = Field(..., description="Description of the impact")
    occurred_at: Optional[datetime] = Field(
        None, description="When the impact occurred"
    )
    value_sek: float = Field(default=0.0, description="Financial value in SEK")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImpactRecordResponse(BaseModel):
    """Response for an impact record."""

    id: UUID
    referral_id: Optional[UUID]
    case_id: Optional[UUID]
    impact_type: str
    occurred_at: datetime
    recorded_at: datetime
    recorded_by: str
    authority: str
    description: str
    value_sek: float


class MetricsSummaryResponse(BaseModel):
    """Response containing metrics summary."""

    period_start: datetime
    period_end: datetime
    investigations_opened: int
    investigations_closed: int
    charges_filed: int
    convictions: int
    acquittals: int
    conviction_rate: float
    total_financial_impact_sek: float


class AuthorityMetricsResponse(BaseModel):
    """Response for authority-specific metrics."""

    authority: str
    outcomes_recorded: int
    convictions: int
    total_value_sek: float


@router.post("/record", response_model=ImpactRecordResponse)
async def record_impact(
    request: RecordImpactRequest,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Record an impact event from a referral or investigation.

    Records outcomes like convictions, assets seized, or fines
    for effectiveness tracking.
    """
    try:
        impact_type = ImpactType(request.impact_type)
    except ValueError:
        valid_types = [t.value for t in ImpactType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid impact type. Valid options: {valid_types}",
        )

    record = _tracker.record(
        impact_type=impact_type,
        authority=request.authority,
        description=request.description,
        recorded_by=str(user.user_id),
        referral_id=request.referral_id,
        case_id=request.case_id,
        occurred_at=request.occurred_at,
        value_sek=request.value_sek,
        metadata=request.metadata,
    )

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="record_impact",
        resource_type="impact",
        resource_id=record.id,
        details={
            "impact_type": impact_type.value,
            "authority": request.authority,
            "value_sek": request.value_sek,
        },
    )

    return ImpactRecordResponse(
        id=record.id,
        referral_id=record.referral_id,
        case_id=record.case_id,
        impact_type=record.impact_type.value,
        occurred_at=record.occurred_at,
        recorded_at=record.recorded_at,
        recorded_by=record.recorded_by,
        authority=record.authority,
        description=record.description,
        value_sek=record.value_sek,
    )


@router.get("/metrics", response_model=MetricsSummaryResponse)
async def get_metrics(
    audit_repo: AuditRepo,
    user: User,
    since: Optional[datetime] = Query(None, description="Start of period"),
    until: Optional[datetime] = Query(None, description="End of period"),
):
    """
    Get aggregated impact metrics.

    Returns summary statistics for the specified period.
    """
    start = since or datetime(2020, 1, 1)
    end = until or datetime.utcnow()

    metrics = _calculator.calculate_period_metrics(start, end)

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view_metrics",
        resource_type="impact_metrics",
    )

    return MetricsSummaryResponse(
        period_start=metrics.period_start,
        period_end=metrics.period_end,
        investigations_opened=metrics.investigations_opened,
        investigations_closed=metrics.investigations_closed,
        charges_filed=metrics.charges_filed,
        convictions=metrics.convictions,
        acquittals=metrics.acquittals,
        conviction_rate=metrics.conviction_rate,
        total_financial_impact_sek=metrics.total_financial_impact_sek,
    )


@router.get("/metrics/authority", response_model=list[AuthorityMetricsResponse])
async def get_authority_metrics(
    audit_repo: AuditRepo,
    user: User,
    since: Optional[datetime] = Query(None, description="Start of period"),
):
    """
    Get impact metrics broken down by authority.

    Shows effectiveness statistics per receiving authority.
    """
    metrics = _calculator.calculate_authority_metrics(since=since)

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view_authority_metrics",
        resource_type="impact_metrics",
    )

    return [
        AuthorityMetricsResponse(
            authority=m.authority,
            outcomes_recorded=m.outcomes_recorded,
            convictions=m.convictions,
            total_value_sek=m.total_value_sek,
        )
        for m in metrics
    ]


@router.get("/referral/{referral_id}", response_model=list[ImpactRecordResponse])
async def get_referral_impacts(
    referral_id: UUID,
    audit_repo: AuditRepo,
    user: User,
):
    """Get all impact records for a referral."""
    records = _tracker.get_by_referral(referral_id)

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view_referral_impacts",
        resource_type="referral",
        resource_id=referral_id,
    )

    return [
        ImpactRecordResponse(
            id=r.id,
            referral_id=r.referral_id,
            case_id=r.case_id,
            impact_type=r.impact_type.value,
            occurred_at=r.occurred_at,
            recorded_at=r.recorded_at,
            recorded_by=r.recorded_by,
            authority=r.authority,
            description=r.description,
            value_sek=r.value_sek,
        )
        for r in records
    ]


@router.get("/case/{case_id}", response_model=list[ImpactRecordResponse])
async def get_case_impacts(
    case_id: UUID,
    audit_repo: AuditRepo,
    user: User,
):
    """Get all impact records for a case."""
    records = _tracker.get_by_case(case_id)

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view_case_impacts",
        resource_type="case",
        resource_id=case_id,
    )

    return [
        ImpactRecordResponse(
            id=r.id,
            referral_id=r.referral_id,
            case_id=r.case_id,
            impact_type=r.impact_type.value,
            occurred_at=r.occurred_at,
            recorded_at=r.recorded_at,
            recorded_by=r.recorded_by,
            authority=r.authority,
            description=r.description,
            value_sek=r.value_sek,
        )
        for r in records
    ]


@router.get("/effectiveness")
async def get_referral_effectiveness(
    audit_repo: AuditRepo,
    user: User,
    since: Optional[datetime] = Query(None, description="Start of period"),
):
    """
    Get referral effectiveness statistics.

    Shows success rates and outcome tracking for referrals.
    """
    effectiveness = _calculator.get_referral_effectiveness(since=since)

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view_effectiveness",
        resource_type="impact_metrics",
    )

    return effectiveness
