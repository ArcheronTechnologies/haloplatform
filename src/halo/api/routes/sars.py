"""
SAR (Suspicious Activity Report) API routes.

Provides CRUD operations for SARs:
- List/filter SARs
- Get SAR details
- Create/update SAR
- Approve and submit SARs
"""

from typing import Optional
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from halo.api.deps import get_db_session, User, AuditRepo, AnalystUser

router = APIRouter()


# Models
class SARBase(BaseModel):
    """Base SAR fields."""

    sar_type: str = Field(default="sar", description="Type: str, ctr, sar, tfar")
    priority: str = Field(default="medium", description="Priority: low, medium, high, urgent")
    summary: Optional[str] = None
    total_amount: Optional[float] = None
    currency: str = "SEK"


class SARCreate(SARBase):
    """SAR creation request."""

    subject_entity_id: str
    trigger_reason: str
    alert_ids: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class SARUpdate(BaseModel):
    """SAR update request."""

    summary: Optional[str] = None
    priority: Optional[str] = None
    total_amount: Optional[float] = None
    notes: Optional[str] = None


class SARResponse(SARBase):
    """SAR response."""

    id: str
    status: str
    subject_entity_id: str
    subject_name: Optional[str] = None
    trigger_reason: Optional[str] = None
    created_at: datetime
    submitted_at: Optional[datetime] = None
    external_reference: Optional[str] = None


class PaginatedSARResponse(BaseModel):
    """Paginated SAR list response."""

    items: list[SARResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# In-memory storage for SARs (in production, use database)
_sars_store: dict[str, dict] = {}


@router.get("", response_model=PaginatedSARResponse)
async def list_sars(
    user: User,
    audit_repo: AuditRepo,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """
    List SARs with pagination and filtering.
    """
    # Filter SARs
    filtered = list(_sars_store.values())
    if status:
        filtered = [s for s in filtered if s.get("status") == status]

    total = len(filtered)
    total_pages = (total + limit - 1) // limit

    # Paginate
    start = (page - 1) * limit
    end = start + limit
    items = filtered[start:end]

    await audit_repo.log(
        user_id=user.id,
        user_name=user.username,
        action="list",
        resource_type="sar",
        resource_id="all",
    )

    return PaginatedSARResponse(
        items=[SARResponse(**s) for s in items],
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages,
    )


@router.get("/{sar_id}", response_model=SARResponse)
async def get_sar(
    sar_id: str,
    user: User,
    audit_repo: AuditRepo,
):
    """
    Get SAR details by ID.
    """
    if sar_id not in _sars_store:
        raise HTTPException(status_code=404, detail="SAR not found")

    await audit_repo.log(
        user_id=user.id,
        user_name=user.username,
        action="view",
        resource_type="sar",
        resource_id=sar_id,
    )

    return SARResponse(**_sars_store[sar_id])


@router.post("", response_model=SARResponse)
async def create_sar(
    data: SARCreate,
    user: AnalystUser,
    audit_repo: AuditRepo,
):
    """
    Create a new SAR.

    Requires analyst role.
    """
    sar_id = str(uuid4())
    now = datetime.utcnow()

    sar = {
        "id": sar_id,
        "sar_type": data.sar_type,
        "status": "draft",
        "priority": data.priority,
        "summary": data.summary,
        "total_amount": data.total_amount,
        "currency": data.currency,
        "subject_entity_id": data.subject_entity_id,
        "subject_name": None,  # Would be fetched from entity
        "trigger_reason": data.trigger_reason,
        "created_at": now,
        "submitted_at": None,
        "external_reference": None,
    }

    _sars_store[sar_id] = sar

    await audit_repo.log(
        user_id=user.id,
        user_name=user.username,
        action="create",
        resource_type="sar",
        resource_id=sar_id,
        details={"subject_entity_id": data.subject_entity_id},
    )

    return SARResponse(**sar)


@router.patch("/{sar_id}", response_model=SARResponse)
async def update_sar(
    sar_id: str,
    data: SARUpdate,
    user: AnalystUser,
    audit_repo: AuditRepo,
):
    """
    Update a SAR.

    Only draft SARs can be updated.
    """
    if sar_id not in _sars_store:
        raise HTTPException(status_code=404, detail="SAR not found")

    sar = _sars_store[sar_id]

    if sar["status"] != "draft":
        raise HTTPException(
            status_code=400,
            detail="Only draft SARs can be updated"
        )

    # Update fields
    if data.summary is not None:
        sar["summary"] = data.summary
    if data.priority is not None:
        sar["priority"] = data.priority
    if data.total_amount is not None:
        sar["total_amount"] = data.total_amount

    await audit_repo.log(
        user_id=user.id,
        user_name=user.username,
        action="update",
        resource_type="sar",
        resource_id=sar_id,
    )

    return SARResponse(**sar)


@router.post("/{sar_id}/approve", response_model=SARResponse)
async def approve_sar(
    sar_id: str,
    user: AnalystUser,
    audit_repo: AuditRepo,
):
    """
    Approve a SAR for submission.

    Moves status from 'draft' to 'approved'.
    """
    if sar_id not in _sars_store:
        raise HTTPException(status_code=404, detail="SAR not found")

    sar = _sars_store[sar_id]

    if sar["status"] not in ("draft", "pending_review"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve SAR in {sar['status']} status"
        )

    sar["status"] = "approved"

    await audit_repo.log(
        user_id=user.id,
        user_name=user.username,
        action="approve",
        resource_type="sar",
        resource_id=sar_id,
    )

    return SARResponse(**sar)


@router.post("/{sar_id}/submit", response_model=SARResponse)
async def submit_sar(
    sar_id: str,
    user: AnalystUser,
    audit_repo: AuditRepo,
):
    """
    Submit a SAR to authorities.

    Moves status from 'approved' to 'submitted'.
    """
    if sar_id not in _sars_store:
        raise HTTPException(status_code=404, detail="SAR not found")

    sar = _sars_store[sar_id]

    if sar["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail="SAR must be approved before submission"
        )

    sar["status"] = "submitted"
    sar["submitted_at"] = datetime.utcnow()
    sar["external_reference"] = f"FIU-{uuid4().hex[:8].upper()}"

    await audit_repo.log(
        user_id=user.id,
        user_name=user.username,
        action="submit",
        resource_type="sar",
        resource_id=sar_id,
        details={"external_reference": sar["external_reference"]},
    )

    return SARResponse(**sar)
