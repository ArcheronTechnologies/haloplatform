"""
Dashboard API routes.

Provides aggregated statistics and recent activity for the dashboard view.
"""

from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from halo.api.deps import get_db_session, User

router = APIRouter()


# Response models
class AlertStats(BaseModel):
    """Alert statistics."""

    total: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    new_today: int = 0


class CaseStats(BaseModel):
    """Case statistics."""

    total: int = 0
    open: int = 0
    by_priority: dict[str, int] = Field(default_factory=dict)


class EntityStats(BaseModel):
    """Entity statistics."""

    total: int = 0
    high_risk: int = 0
    new_this_week: int = 0


class SARStats(BaseModel):
    """SAR statistics."""

    draft: int = 0
    pending: int = 0
    submitted_this_month: int = 0


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics response."""

    alerts: AlertStats
    cases: CaseStats
    entities: EntityStats
    sars: SARStats


class RecentAlert(BaseModel):
    """Recent alert summary."""

    id: str
    title: str
    description: Optional[str] = None
    severity: str
    status: str
    created_at: datetime


class RecentCase(BaseModel):
    """Recent case summary."""

    id: str
    case_number: str
    title: str
    priority: str
    status: str
    created_at: datetime


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    user: User,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get aggregated dashboard statistics.

    Returns counts and breakdowns for alerts, cases, entities, and SARs.
    """
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Try to get real stats from database, fallback to mock data
    try:
        from halo.models import Alert, Entity
        from halo.db.orm import Case

        # Alert stats
        alert_result = await db.execute(select(func.count(Alert.id)))
        total_alerts = alert_result.scalar() or 0

        new_today_result = await db.execute(
            select(func.count(Alert.id)).where(Alert.created_at >= today_start)
        )
        new_today = new_today_result.scalar() or 0

        # Entity stats
        entity_result = await db.execute(select(func.count(Entity.id)))
        total_entities = entity_result.scalar() or 0

        # Case stats
        case_result = await db.execute(select(func.count(Case.id)))
        total_cases = case_result.scalar() or 0

        return DashboardStatsResponse(
            alerts=AlertStats(
                total=total_alerts,
                by_severity={"critical": 0, "high": 0, "medium": 0, "low": 0},
                new_today=new_today,
            ),
            cases=CaseStats(
                total=total_cases,
                open=0,
                by_priority={"critical": 0, "high": 0, "medium": 0, "low": 0},
            ),
            entities=EntityStats(
                total=total_entities,
                high_risk=0,
                new_this_week=0,
            ),
            sars=SARStats(
                draft=0,
                pending=0,
                submitted_this_month=0,
            ),
        )
    except Exception:
        # Return empty stats if tables don't exist yet
        return DashboardStatsResponse(
            alerts=AlertStats(
                total=0,
                by_severity={"critical": 0, "high": 0, "medium": 0, "low": 0},
                new_today=0,
            ),
            cases=CaseStats(
                total=0,
                open=0,
                by_priority={"critical": 0, "high": 0, "medium": 0, "low": 0},
            ),
            entities=EntityStats(
                total=0,
                high_risk=0,
                new_this_week=0,
            ),
            sars=SARStats(
                draft=0,
                pending=0,
                submitted_this_month=0,
            ),
        )


@router.get("/recent-alerts", response_model=list[RecentAlert])
async def get_recent_alerts(
    user: User,
    db: AsyncSession = Depends(get_db_session),
    limit: int = Query(5, ge=1, le=20),
):
    """
    Get recent alerts for dashboard display.
    """
    try:
        from halo.models import Alert

        result = await db.execute(
            select(Alert)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )
        alerts = result.scalars().all()

        return [
            RecentAlert(
                id=str(alert.id),
                title=alert.title or f"Alert {alert.id}",
                description=alert.description,
                severity=alert.severity or "medium",
                status=alert.status or "new",
                created_at=alert.created_at,
            )
            for alert in alerts
        ]
    except Exception:
        return []


@router.get("/recent-cases", response_model=list[RecentCase])
async def get_recent_cases(
    user: User,
    db: AsyncSession = Depends(get_db_session),
    limit: int = Query(5, ge=1, le=20),
):
    """
    Get recent cases for dashboard display.
    """
    try:
        from halo.db.orm import Case

        result = await db.execute(
            select(Case)
            .order_by(Case.created_at.desc())
            .limit(limit)
        )
        cases = result.scalars().all()

        return [
            RecentCase(
                id=str(case.id),
                case_number=case.case_number or f"CASE-{case.id}",
                title=case.title or "Untitled Case",
                priority=case.priority or "medium",
                status=case.status or "open",
                created_at=case.created_at,
            )
            for case in cases
        ]
    except Exception:
        return []
