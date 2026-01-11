"""
Audit log API routes.

Provides read-only access to audit logs for compliance and investigation.
CRITICAL: Audit logs are immutable - no update/delete operations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel

from halo.api.deps import AuditRepo, User

router = APIRouter()


class AuditLogResponse(BaseModel):
    """Response model for audit log entry."""

    id: UUID
    user_id: str
    user_name: str
    action: str
    resource_type: str
    resource_id: Optional[UUID]
    details: dict
    case_id: Optional[UUID]
    justification: Optional[str]
    timestamp: datetime
    ip_address: Optional[str]

    class Config:
        from_attributes = True


@router.get("/resource/{resource_type}/{resource_id}", response_model=list[AuditLogResponse])
async def get_audit_for_resource(
    resource_type: str,
    resource_id: UUID,
    audit_repo: AuditRepo,
    user: User,
    limit: int = Query(100, ge=1, le=1000),
):
    """
    Get audit logs for a specific resource.

    Shows who accessed what and when - critical for compliance audits.
    """
    logs = await audit_repo.get_for_resource(
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
    )

    # Meta-log: record that someone viewed the audit trail
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="audit_log",
        details={
            "viewed_resource_type": resource_type,
            "viewed_resource_id": str(resource_id),
        },
    )

    return logs


@router.get("/user/{user_id}", response_model=list[AuditLogResponse])
async def get_audit_for_user(
    user_id: str,
    audit_repo: AuditRepo,
    user: User,
    since: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """
    Get audit logs for a specific user.

    Used for reviewing user activity and investigating potential misuse.
    """
    logs = await audit_repo.get_for_user(
        user_id=user_id,
        since=since,
        limit=limit,
    )

    # Meta-log: record that someone viewed another user's audit trail
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="audit_log",
        details={
            "viewed_user_id": user_id,
            "since": since.isoformat() if since else None,
        },
    )

    return logs
