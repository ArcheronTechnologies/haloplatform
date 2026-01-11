"""
Pattern detection API routes.

Provides endpoints for:
- Shell company network detection
- Registration mill detection
- Risk pattern alerts

Per API Contract (ontology.md):
- POST /api/v1/patterns/shell-network - Response time: <10s
"""

import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from halo.api.deps import get_db_session
from halo.patterns import (
    ShellNetworkParams,
    ShellNetworkQueryService,
    detect_shell_networks_db,
    detect_registration_mills_db,
)

router = APIRouter(prefix="/patterns", tags=["patterns"])


# ========== Request/Response Models ==========


class ShellNetworkRequest(BaseModel):
    """Request for shell network detection (per ontology spec)."""

    min_companies: int = Field(default=3, ge=2, description="Minimum companies to qualify as network")
    max_employees: int = Field(default=2, ge=0, description="Maximum employees for shell-like company")
    max_revenue: int = Field(default=500000, ge=0, description="Maximum revenue for shell-like company")


class ShellNetworkMatchResponse(BaseModel):
    """A single shell network match (per ontology spec)."""

    person_id: UUID
    person_name: Optional[str] = None
    companies: list[UUID]
    risk_score: float = Field(ge=0.0, le=1.0)
    indicators: list[str]


class ShellNetworkResponse(BaseModel):
    """Response from shell network detection (per ontology spec)."""

    matches: list[ShellNetworkMatchResponse]
    execution_time_ms: int


class ShellIndicator(BaseModel):
    """A shell company indicator."""

    indicator: str
    score: float = Field(ge=0.0, le=1.0)
    details: Optional[str] = None


class ShellCompanyResult(BaseModel):
    """Result of shell company analysis."""

    company_id: UUID
    org_nr: str
    name: str
    is_shell: bool
    shell_score: float = Field(ge=0.0, le=1.0)
    indicators: list[ShellIndicator]


class NetworkNode(BaseModel):
    """A node in a pattern network."""

    id: UUID
    entity_type: str
    name: str
    risk_score: float = Field(ge=0.0, le=1.0)


class NetworkEdge(BaseModel):
    """An edge in a pattern network."""

    source: UUID
    target: UUID
    relationship: str
    weight: float


class ShellNetworkResult(BaseModel):
    """Result of shell network detection."""

    network_id: str
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]
    total_shell_score: float = Field(ge=0.0, le=1.0)
    hub_persons: list[UUID]
    shell_companies: list[UUID]


class RegistrationMillResult(BaseModel):
    """Result of registration mill detection."""

    address_id: UUID
    address: str
    company_count: int
    unique_person_count: int
    person_per_company_ratio: float
    is_mill: bool
    confidence: float = Field(ge=0.0, le=1.0)


class PatternAlert(BaseModel):
    """An alert from pattern detection."""

    alert_id: UUID
    alert_type: str
    severity: str
    entity_ids: list[UUID]
    description: str
    created_at: str


# ========== Endpoints ==========


@router.post("/shell-network", response_model=ShellNetworkResponse)
async def detect_shell_network_post(
    request: ShellNetworkRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Detect shell company networks (per ontology API contract).

    Response time target: <10s

    Finds persons directing multiple low-activity companies.
    """
    start_time = time.time()

    params = ShellNetworkParams(
        min_companies=request.min_companies,
        max_employees=request.max_employees,
        max_revenue=request.max_revenue,
    )

    try:
        matches = await detect_shell_networks_db(db, params, limit=100)

        results = [
            ShellNetworkMatchResponse(
                person_id=m.person_id,
                person_name=m.person_name,
                companies=m.company_ids,
                risk_score=m.risk_score,
                indicators=m.indicators,
            )
            for m in matches
        ]
    except Exception:
        # If DB not available, return empty result
        results = []

    execution_time_ms = int((time.time() - start_time) * 1000)

    return ShellNetworkResponse(
        matches=results,
        execution_time_ms=execution_time_ms,
    )


@router.get("/shell-networks", response_model=list[ShellNetworkResult])
async def detect_shell_networks(
    min_companies: int = Query(3, ge=2, description="Minimum companies in network"),
    min_score: float = Query(0.7, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Detect shell company networks.

    Finds clusters of companies with shared directors and
    shell company characteristics.
    """
    params = ShellNetworkParams(min_companies=min_companies)

    try:
        matches = await detect_shell_networks_db(db, params, limit=limit)

        # Convert to legacy response format
        return [
            ShellNetworkResult(
                network_id=f"network_{m.person_id}",
                nodes=[
                    NetworkNode(
                        id=m.person_id,
                        entity_type="PERSON",
                        name=m.person_name,
                        risk_score=m.risk_score,
                    )
                ],
                edges=[],
                total_shell_score=m.risk_score,
                hub_persons=[m.person_id],
                shell_companies=m.company_ids,
            )
            for m in matches
            if m.risk_score >= min_score
        ]
    except Exception:
        return []


@router.get("/shell-networks/{entity_id}", response_model=ShellNetworkResult)
async def get_shell_network_for_entity(
    entity_id: UUID,
    depth: int = Query(2, ge=1, le=4),
):
    """
    Get shell network containing a specific entity.

    Expands from the entity to find connected shell companies.
    """
    # Placeholder
    return ShellNetworkResult(
        network_id="",
        nodes=[],
        edges=[],
        total_shell_score=0.0,
        hub_persons=[],
        shell_companies=[],
    )


@router.get("/shell-company/{company_id}", response_model=ShellCompanyResult)
async def analyze_shell_company(company_id: UUID):
    """
    Analyze a single company for shell indicators.

    Returns detailed breakdown of shell company signals.
    """
    # Placeholder - would call derivation.shell_indicators
    return ShellCompanyResult(
        company_id=company_id,
        org_nr="",
        name="",
        is_shell=False,
        shell_score=0.0,
        indicators=[],
    )


@router.get("/registration-mills", response_model=list[RegistrationMillResult])
async def detect_registration_mills(
    min_companies: int = Query(10, ge=5),
    max_person_ratio: float = Query(0.2, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Detect registration mill addresses.

    Finds addresses with many companies but few actual persons.
    """
    params = ShellNetworkParams(min_address_density=min_companies)

    try:
        mills = await detect_registration_mills_db(db, params, limit=limit)

        return [
            RegistrationMillResult(
                address_id=m.address_id,
                address=f"{m.address}, {m.postal_code} {m.city}",
                company_count=m.company_count,
                unique_person_count=len(m.shared_directors) if m.shared_directors else 0,
                person_per_company_ratio=(
                    len(m.shared_directors) / m.company_count if m.company_count > 0 else 0
                ),
                is_mill=m.company_count >= min_companies,
                confidence=m.risk_score,
            )
            for m in mills
        ]
    except Exception:
        return []


@router.get("/alerts", response_model=list[PatternAlert])
async def get_pattern_alerts(
    alert_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get pattern-based alerts.

    Returns alerts generated by pattern detection systems.
    """
    # Placeholder - would call patterns.alerting
    return []


@router.post("/scan")
async def trigger_pattern_scan(
    entity_ids: Optional[list[UUID]] = None,
    full_scan: bool = False,
):
    """
    Trigger pattern detection scan.

    Either scans specific entities or runs a full scan.
    """
    # Placeholder - would trigger async pattern detection job
    return {
        "status": "scheduled",
        "entity_count": len(entity_ids) if entity_ids else "full",
        "job_id": "placeholder",
    }


@router.get("/director-velocity/{company_id}")
async def get_director_velocity(company_id: UUID):
    """
    Get director change velocity for a company.

    High velocity (>2/year) is a risk indicator.
    """
    # Placeholder - would call derivation.velocity
    return {
        "company_id": str(company_id),
        "velocity": 0.0,
        "changes_last_year": 0,
        "changes_last_3_years": 0,
        "is_high_velocity": False,
    }
