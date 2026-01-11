"""
Case management API routes.

Provides case/investigation management functionality.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from halo.api.deps import AuditRepo, CaseRepo, User, AnalystUser

router = APIRouter()


class CaseCreate(BaseModel):
    """Request model for creating a case."""

    case_number: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=255)
    description: str
    assigned_to: Optional[str] = None
    entity_ids: list[UUID] = Field(default_factory=list)
    alert_ids: list[UUID] = Field(default_factory=list)


class CaseUpdate(BaseModel):
    """Request model for updating a case."""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    entity_ids: Optional[list[UUID]] = None
    alert_ids: Optional[list[UUID]] = None


class CaseResponse(BaseModel):
    """Response model for case."""

    id: UUID
    case_number: str
    title: str
    description: str
    status: str
    priority: Optional[str] = "medium"
    case_type: Optional[str] = "other"
    assigned_to: Optional[str]
    entity_ids: list[UUID]
    alert_ids: list[UUID]
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime]

    class Config:
        from_attributes = True


class PaginatedCasesResponse(BaseModel):
    """Paginated cases response."""

    items: list[CaseResponse]
    total: int
    page: int
    limit: int


@router.get("", response_model=PaginatedCasesResponse)
async def list_cases(
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: User,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=200, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    case_type: Optional[str] = Query(None, description="Filter by case type"),
):
    """List cases with pagination and filters."""
    if status == "open" or status is None:
        cases = await case_repo.list_open(limit=limit * 5)
    else:
        cases = await case_repo.list_open(limit=limit * 5)

    # Filter by priority and case_type if provided
    if priority:
        cases = [c for c in cases if getattr(c, 'priority', None) == priority]
    if case_type:
        cases = [c for c in cases if getattr(c, 'case_type', None) == case_type]

    total = len(cases)

    # Paginate
    start = (page - 1) * limit
    end = start + limit
    page_cases = cases[start:end]

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="case_list",
        details={"status": status, "count": len(page_cases)},
    )

    return PaginatedCasesResponse(
        items=page_cases,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """Get case by ID."""
    case = await case_repo.get_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="case",
        resource_id=case_id,
    )

    return case


@router.post("", response_model=CaseResponse, status_code=201)
async def create_case(
    data: CaseCreate,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """Create a new investigation case."""
    # Check if case number already exists
    existing = await case_repo.get_by_number(data.case_number)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Case number {data.case_number} already exists",
        )

    case = await case_repo.create(
        case_number=data.case_number,
        title=data.title,
        description=data.description,
        assigned_to=data.assigned_to,
        entity_ids=data.entity_ids,
        alert_ids=data.alert_ids,
    )

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="create",
        resource_type="case",
        resource_id=case.id,
        details={"case_number": data.case_number},
    )

    return case


class StatusUpdateRequest(BaseModel):
    """Request model for updating case status."""

    status: str = Field(..., description="New status: open, in_progress, pending_review, closed")
    notes: Optional[str] = Field(None, description="Status change notes")


@router.post("/{case_id}/status", response_model=CaseResponse)
async def update_case_status(
    case_id: UUID,
    request: StatusUpdateRequest,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """Update case status with optional notes."""
    valid_statuses = ["open", "in_progress", "pending_review", "closed"]
    if request.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    case = await case_repo.update_status(case_id, request.status)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="update",
        resource_type="case",
        resource_id=case_id,
        details={"new_status": request.status, "notes": request.notes},
    )

    return case


class AssignRequest(BaseModel):
    """Request model for assigning a case."""

    user_id: str = Field(..., description="User ID to assign to")


@router.post("/{case_id}/assign", response_model=CaseResponse)
async def assign_case(
    case_id: UUID,
    request: AssignRequest,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """Assign a case to a user."""
    case = await case_repo.get_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Update assignment
    from halo.db.orm import Case
    case.assigned_to = request.user_id

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="assign",
        resource_type="case",
        resource_id=case_id,
        details={"assigned_to": request.user_id},
    )

    return case


class NoteCreate(BaseModel):
    """Request model for adding a case note."""

    content: str = Field(..., min_length=1, max_length=10000)


class NoteResponse(BaseModel):
    """Response model for case note."""

    id: UUID
    case_id: UUID
    content: str
    author_id: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/{case_id}/notes", response_model=NoteResponse, status_code=201)
async def add_case_note(
    case_id: UUID,
    data: NoteCreate,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """Add a note to an investigation case."""
    case = await case_repo.get_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    note = await case_repo.add_note(
        case_id=case_id,
        content=data.content,
        author_id=user.user_id,
    )

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="add_note",
        resource_type="case",
        resource_id=case_id,
        details={"note_length": len(data.content)},
    )

    return note


@router.get("/{case_id}/notes", response_model=list[NoteResponse])
async def get_case_notes(
    case_id: UUID,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """Get all notes for a case."""
    case = await case_repo.get_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    notes = await case_repo.get_notes(case_id)

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="case_notes",
        resource_id=case_id,
    )

    return notes


class TimelineEvent(BaseModel):
    """Timeline event model."""

    id: str
    timestamp: datetime
    event_type: str
    title: str
    description: Optional[str] = None
    user_id: Optional[str] = None


@router.get("/{case_id}/timeline", response_model=list[TimelineEvent])
async def get_case_timeline(
    case_id: UUID,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Get timeline of events for a case.

    Returns chronological list of case activities:
    - Status changes
    - Notes added
    - Entities linked/unlinked
    - Evidence collected
    """
    case = await case_repo.get_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="case_timeline",
        resource_id=case_id,
    )

    # In production, aggregate events from multiple sources
    # For now return creation event
    return [
        TimelineEvent(
            id=str(case.id),
            timestamp=case.created_at,
            event_type="case_created",
            title="Case Created",
            description=f"Case {case.case_number} created",
        )
    ]


class Evidence(BaseModel):
    """Evidence item model."""

    id: str
    type: str
    title: str
    description: Optional[str] = None
    source: Optional[str] = None
    collected_at: datetime


@router.get("/{case_id}/evidence", response_model=list[Evidence])
async def get_case_evidence(
    case_id: UUID,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Get evidence items collected for a case.

    Returns list of evidence:
    - Documents
    - Transaction records
    - Entity data snapshots
    - Screenshots/images
    """
    case = await case_repo.get_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="case_evidence",
        resource_id=case_id,
    )

    # In production, fetch from evidence store
    # For now return empty list
    return []


class CaseCloseRequest(BaseModel):
    """Request model for closing a case."""

    outcome: str = Field(
        ...,
        description="Outcome: confirmed, cleared, or inconclusive",
    )
    findings: str = Field(
        ...,
        min_length=10,
        description="Summary of investigation findings",
    )
    recommendations: str = Field(
        default="",
        description="Recommendations for future action",
    )


@router.post("/{case_id}/close", response_model=CaseResponse)
async def close_case(
    case_id: UUID,
    data: CaseCloseRequest,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """
    Close an investigation case with findings.

    Requires outcome (confirmed/cleared/inconclusive) and findings summary.
    """
    valid_outcomes = ["confirmed", "cleared", "inconclusive"]
    if data.outcome not in valid_outcomes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome. Must be one of: {valid_outcomes}",
        )

    case = await case_repo.close(
        case_id=case_id,
        outcome=data.outcome,
        findings=data.findings,
        recommendations=data.recommendations,
        closed_by=user.user_id,
    )

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="close",
        resource_type="case",
        resource_id=case_id,
        details={
            "outcome": data.outcome,
            "findings_length": len(data.findings),
        },
    )

    return case


@router.post("/{case_id}/entities/{entity_id}", status_code=204)
async def link_entity_to_case(
    case_id: UUID,
    entity_id: UUID,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """Link an entity to a case."""
    case = await case_repo.get_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await case_repo.link_entity(case_id, entity_id)

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="link_entity",
        resource_type="case",
        resource_id=case_id,
        details={"entity_id": str(entity_id)},
    )


@router.delete("/{case_id}/entities/{entity_id}", status_code=204)
async def unlink_entity_from_case(
    case_id: UUID,
    entity_id: UUID,
    case_repo: CaseRepo,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """Unlink an entity from a case."""
    case = await case_repo.get_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await case_repo.unlink_entity(case_id, entity_id)

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="unlink_entity",
        resource_type="case",
        resource_id=case_id,
        details={"entity_id": str(entity_id)},
    )
