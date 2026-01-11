"""
Alert review API routes.

Implements human-in-loop compliance for Brottsdatalagen 2 kap. 19 §.
All Tier 2/3 alerts require human review before export/action.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from halo.api.deps import AlertRepo, AuditRepo, User, AnalystUser, SeniorAnalystUser

router = APIRouter()


class AlertResponse(BaseModel):
    """Response model for alert."""

    id: UUID
    alert_type: str
    severity: str
    title: str
    description: str
    confidence: float
    tier: int
    affects_person: bool
    status: str
    review_status: str
    can_export: bool
    is_rubber_stamp: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AcknowledgeRequest(BaseModel):
    """Request to acknowledge a Tier 2 alert."""

    displayed_at: datetime = Field(
        ...,
        description="When the alert was first displayed to the user",
    )


class ApprovalRequest(BaseModel):
    """Request to approve/reject a Tier 3 alert."""

    decision: str = Field(
        ...,
        description="Decision: approved, rejected, or escalated",
    )
    justification: str = Field(
        ...,
        min_length=10,
        description="Justification for the decision (min 10 chars)",
    )
    displayed_at: datetime = Field(
        ...,
        description="When the alert was first displayed to the user",
    )

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        valid = ["approved", "rejected", "escalated"]
        if v not in valid:
            raise ValueError(f"Decision must be one of: {valid}")
        return v

    @field_validator("justification")
    @classmethod
    def validate_justification(cls, v: str) -> str:
        # Reject garbage justifications
        garbage = ["ok", "fine", "approved", "yes", ".", "x", "asdf", "123", "test"]
        if v.lower().strip() in garbage:
            raise ValueError("Ange en faktisk motivering / Please provide a real justification")
        return v


class BatchAcknowledgeRequest(BaseModel):
    """Request to acknowledge multiple Tier 2 alerts."""

    alert_ids: list[UUID]
    displayed_at: datetime


class ReviewStatsResponse(BaseModel):
    """Response with review statistics for rubber-stamp detection."""

    user_id: str
    total_reviews: int
    approval_rate: float
    avg_review_seconds: float
    is_suspicious: bool


class PaginatedAlertsResponse(BaseModel):
    """Paginated alerts response."""

    items: list[AlertResponse]
    total: int
    page: int
    limit: int


@router.get("", response_model=PaginatedAlertsResponse)
async def list_alerts(
    alert_repo: AlertRepo,
    audit_repo: AuditRepo,
    user: User,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=200, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level"),
    tier: Optional[int] = Query(None, ge=1, le=3, description="Filter by tier"),
):
    """
    List alerts with pagination.

    Supports filtering by status, risk_level, and tier.
    """
    alerts = await alert_repo.get_pending_review(tier=tier, limit=limit * 5)  # Get more for filtering

    # Filter by status and risk_level if provided
    if status:
        alerts = [a for a in alerts if a.status == status]
    if risk_level:
        alerts = [a for a in alerts if a.severity == risk_level]

    total = len(alerts)

    # Paginate
    start = (page - 1) * limit
    end = start + limit
    page_alerts = alerts[start:end]

    # Log access
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="alert_list",
        details={"status": status, "risk_level": risk_level, "tier": tier, "count": len(page_alerts)},
    )

    return PaginatedAlertsResponse(
        items=[
            AlertResponse(
                id=a.id,
                alert_type=a.alert_type,
                severity=a.severity,
                title=a.title,
                description=a.description,
                confidence=a.confidence,
                tier=a.tier,
                affects_person=a.affects_person,
                status=a.status,
                review_status=a.review_status,
                can_export=a.can_export,
                is_rubber_stamp=a.is_rubber_stamp,
                created_at=a.created_at,
            )
            for a in page_alerts
        ],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: UUID,
    alert_repo: AlertRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """Get alert details."""
    alert = await alert_repo.get_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="alert",
        resource_id=alert_id,
    )

    return AlertResponse(
        id=alert.id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        title=alert.title,
        description=alert.description,
        confidence=alert.confidence,
        tier=alert.tier,
        affects_person=alert.affects_person,
        status=alert.status,
        review_status=alert.review_status,
        can_export=alert.can_export,
        is_rubber_stamp=alert.is_rubber_stamp,
        created_at=alert.created_at,
    )


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    request: AcknowledgeRequest,
    alert_repo: AlertRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """
    Acknowledge a Tier 2 alert.

    This creates an audit record that the human saw and acknowledged
    the alert. After acknowledgment, the alert can be exported.
    """
    alert = await alert_repo.acknowledge(
        alert_id=alert_id,
        user_id=user.user_id,
        displayed_at=request.displayed_at,
    )

    if not alert:
        raise HTTPException(
            status_code=400,
            detail="Alert not found or not a Tier 2 alert",
        )

    # Log the acknowledgment
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="acknowledge",
        resource_type="alert",
        resource_id=alert_id,
        details={
            "review_duration_seconds": alert.review_duration_seconds,
            "is_rubber_stamp": alert.is_rubber_stamp,
        },
    )

    return AlertResponse(
        id=alert.id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        title=alert.title,
        description=alert.description,
        confidence=alert.confidence,
        tier=alert.tier,
        affects_person=alert.affects_person,
        status=alert.status,
        review_status=alert.review_status,
        can_export=alert.can_export,
        is_rubber_stamp=alert.is_rubber_stamp,
        created_at=alert.created_at,
    )


@router.post("/{alert_id}/approve", response_model=AlertResponse)
async def approve_alert(
    alert_id: UUID,
    request: ApprovalRequest,
    alert_repo: AlertRepo,
    audit_repo: AuditRepo,
    user: SeniorAnalystUser,
):
    """
    Approve, reject, or escalate a Tier 3 alert.

    Tier 3 alerts require explicit approval with justification before
    any action can be taken. This is required by Brottsdatalagen.
    """
    alert = await alert_repo.approve(
        alert_id=alert_id,
        user_id=user.user_id,
        decision=request.decision,
        justification=request.justification,
        displayed_at=request.displayed_at,
    )

    if not alert:
        raise HTTPException(
            status_code=400,
            detail="Alert not found or not a Tier 3 alert",
        )

    # Log the approval decision
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="approve",
        resource_type="alert",
        resource_id=alert_id,
        justification=request.justification,
        details={
            "decision": request.decision,
            "review_duration_seconds": alert.review_duration_seconds,
            "is_rubber_stamp": alert.is_rubber_stamp,
        },
    )

    return AlertResponse(
        id=alert.id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        title=alert.title,
        description=alert.description,
        confidence=alert.confidence,
        tier=alert.tier,
        affects_person=alert.affects_person,
        status=alert.status,
        review_status=alert.review_status,
        can_export=alert.can_export,
        is_rubber_stamp=alert.is_rubber_stamp,
        created_at=alert.created_at,
    )


@router.post("/batch-acknowledge")
async def batch_acknowledge_alerts(
    request: BatchAcknowledgeRequest,
    alert_repo: AlertRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """
    Acknowledge multiple Tier 2 alerts at once.

    Batch acknowledgment is permitted for Tier 2 alerts only.
    Each alert is still individually logged.
    """
    acknowledged = []
    failed = []

    for alert_id in request.alert_ids:
        alert = await alert_repo.acknowledge(
            alert_id=alert_id,
            user_id=user.user_id,
            displayed_at=request.displayed_at,
        )

        if alert:
            acknowledged.append(str(alert_id))
            await audit_repo.log(
                user_id=user.user_id,
                user_name=user.user_name,
                action="acknowledge",
                resource_type="alert",
                resource_id=alert_id,
                details={
                    "batch": True,
                    "review_duration_seconds": alert.review_duration_seconds,
                },
            )
        else:
            failed.append(str(alert_id))

    return {
        "acknowledged": acknowledged,
        "failed": failed,
        "total_acknowledged": len(acknowledged),
    }


class ResolveRequest(BaseModel):
    """Request to resolve an alert."""

    outcome: str = Field(..., description="Outcome: approved or rejected")
    notes: Optional[str] = Field(None, description="Resolution notes")


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: UUID,
    request: ResolveRequest,
    alert_repo: AlertRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """
    Resolve an alert with outcome.

    This is an alias for approve that matches frontend expectations.
    """
    alert = await alert_repo.approve(
        alert_id=alert_id,
        user_id=user.user_id,
        decision=request.outcome,
        justification=request.notes or "Resolved",
        displayed_at=datetime.utcnow(),
    )

    if not alert:
        raise HTTPException(
            status_code=400,
            detail="Alert not found or cannot be resolved",
        )

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="resolve",
        resource_type="alert",
        resource_id=alert_id,
        details={"outcome": request.outcome},
    )

    return AlertResponse(
        id=alert.id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        title=alert.title,
        description=alert.description,
        confidence=alert.confidence,
        tier=alert.tier,
        affects_person=alert.affects_person,
        status=alert.status,
        review_status=alert.review_status,
        can_export=alert.can_export,
        is_rubber_stamp=alert.is_rubber_stamp,
        created_at=alert.created_at,
    )


class DismissRequest(BaseModel):
    """Request to dismiss an alert."""

    reason: str = Field(..., min_length=10, description="Reason for dismissal")


@router.post("/{alert_id}/dismiss", response_model=AlertResponse)
async def dismiss_alert(
    alert_id: UUID,
    request: DismissRequest,
    alert_repo: AlertRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """
    Dismiss an alert as false positive or not requiring action.
    """
    alert = await alert_repo.dismiss(
        alert_id=alert_id,
        user_id=user.user_id,
        reason=request.reason,
    )

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="dismiss",
        resource_type="alert",
        resource_id=alert_id,
        details={"reason": request.reason},
    )

    return AlertResponse(
        id=alert.id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        title=alert.title,
        description=alert.description,
        confidence=alert.confidence,
        tier=alert.tier,
        affects_person=alert.affects_person,
        status=alert.status,
        review_status=alert.review_status,
        can_export=alert.can_export,
        is_rubber_stamp=alert.is_rubber_stamp,
        created_at=alert.created_at,
    )


class CaseResponse(BaseModel):
    """Response model for case."""

    id: UUID
    case_number: str
    title: str
    description: str
    status: str


@router.post("/{alert_id}/create-case", response_model=CaseResponse)
async def create_case_from_alert(
    alert_id: UUID,
    alert_repo: AlertRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """
    Create an investigation case from an alert.
    """
    alert = await alert_repo.get_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Create case from alert
    from halo.api.deps import CaseRepo
    from halo.api.deps import get_case_repo

    case_repo = get_case_repo()

    import uuid
    case_number = f"CASE-{uuid.uuid4().hex[:8].upper()}"

    case = await case_repo.create(
        case_number=case_number,
        title=f"Investigation: {alert.title}",
        description=alert.description,
        assigned_to=user.user_id,
        entity_ids=[],
        alert_ids=[alert_id],
    )

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="create_case",
        resource_type="alert",
        resource_id=alert_id,
        details={"case_id": str(case.id), "case_number": case_number},
    )

    return CaseResponse(
        id=case.id,
        case_number=case.case_number,
        title=case.title,
        description=case.description,
        status=case.status,
    )
