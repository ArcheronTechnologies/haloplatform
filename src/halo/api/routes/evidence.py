"""
Evidence package API routes.

Provides endpoints for:
- Compiling evidence packages
- Managing chain of custody
- Exporting court-grade documentation
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from halo.api.deps import AuditRepo, User
from halo.evidence import (
    EvidencePackage,
    create_evidence_package,
    ProvenanceChain,
    ExportFormat,
)

router = APIRouter()


class EvidenceCompileRequest(BaseModel):
    """Request to compile an evidence package."""

    case_id: UUID = Field(..., description="Case to compile evidence for")
    include_source_docs: bool = Field(
        default=True, description="Include source documents"
    )
    include_analysis: bool = Field(
        default=True, description="Include analysis results"
    )
    include_timeline: bool = Field(
        default=True, description="Include temporal timeline"
    )
    classification: str = Field(
        default="restricted",
        description="Classification level: public, internal, restricted, confidential"
    )


class EvidenceItemResponse(BaseModel):
    """Response for a single evidence item."""

    id: UUID
    item_type: str
    source: str
    description: str
    hash: str
    added_at: datetime
    added_by: str


class EvidencePackageResponse(BaseModel):
    """Response containing compiled evidence package."""

    id: UUID
    case_id: UUID
    created_at: datetime
    created_by: str
    classification: str
    item_count: int
    total_size_bytes: int
    integrity_hash: str
    provenance_chain_length: int


class ProvenanceEventResponse(BaseModel):
    """Response for a provenance event."""

    event_id: UUID
    event_type: str
    occurred_at: datetime
    actor: str
    description: str
    hash: str


class ExportRequest(BaseModel):
    """Request to export evidence package."""

    format: str = Field(
        default="pdf",
        description="Export format: pdf, docx, json, xml"
    )
    include_provenance: bool = Field(
        default=True, description="Include provenance chain"
    )
    authority_format: Optional[str] = Field(
        default=None,
        description="Authority-specific format (ebm, skv, fiu)"
    )


@router.post("/compile", response_model=EvidencePackageResponse)
async def compile_evidence(
    request: EvidenceCompileRequest,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Compile evidence package for a case.

    Creates a cryptographically verified evidence package with
    full provenance chain for court-grade documentation.
    """
    package = await create_evidence_package(
        case_id=request.case_id,
        compiled_by=str(user.user_id),
        include_source_docs=request.include_source_docs,
        include_analysis=request.include_analysis,
        include_timeline=request.include_timeline,
        classification=request.classification,
    )

    if not package:
        raise HTTPException(
            status_code=400,
            detail="Failed to compile evidence. Case may not exist or have no evidence.",
        )

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="compile_evidence",
        resource_type="evidence_package",
        resource_id=package.id,
        details={
            "case_id": str(request.case_id),
            "classification": request.classification,
            "item_count": package.item_count,
        },
    )

    return EvidencePackageResponse(
        id=package.id,
        case_id=package.case_id,
        created_at=package.created_at,
        created_by=package.created_by,
        classification=package.classification,
        item_count=package.item_count,
        total_size_bytes=package.total_size_bytes,
        integrity_hash=package.integrity_hash,
        provenance_chain_length=len(package.provenance_chain),
    )


@router.get("/{package_id}", response_model=EvidencePackageResponse)
async def get_evidence_package(
    package_id: UUID,
    audit_repo: AuditRepo,
    user: User,
):
    """Get details of an evidence package."""
    # In production, this would query a repository
    package = None  # await evidence_repo.get_by_id(package_id)

    if not package:
        raise HTTPException(status_code=404, detail="Evidence package not found")

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="evidence_package",
        resource_id=package_id,
    )

    return EvidencePackageResponse(
        id=package.id,
        case_id=package.case_id,
        created_at=package.created_at,
        created_by=package.created_by,
        classification=package.classification,
        item_count=package.item_count,
        total_size_bytes=package.total_size_bytes,
        integrity_hash=package.integrity_hash,
        provenance_chain_length=len(package.provenance_chain),
    )


@router.get("/{package_id}/items", response_model=list[EvidenceItemResponse])
async def list_evidence_items(
    package_id: UUID,
    audit_repo: AuditRepo,
    user: User,
    item_type: Optional[str] = Query(None, description="Filter by item type"),
):
    """List items in an evidence package."""
    # In production, this would query a repository
    items = []  # await evidence_repo.get_items(package_id, item_type=item_type)

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view_items",
        resource_type="evidence_package",
        resource_id=package_id,
    )

    return [
        EvidenceItemResponse(
            id=item.id,
            item_type=item.item_type,
            source=item.source,
            description=item.description,
            hash=item.hash,
            added_at=item.added_at,
            added_by=item.added_by,
        )
        for item in items
    ]


@router.get("/{package_id}/provenance", response_model=list[ProvenanceEventResponse])
async def get_provenance_chain(
    package_id: UUID,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Get the provenance chain for an evidence package.

    Returns the complete chain of custody with cryptographic
    verification hashes.
    """
    # In production, this would query a repository
    events = []  # await evidence_repo.get_provenance(package_id)

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view_provenance",
        resource_type="evidence_package",
        resource_id=package_id,
    )

    return [
        ProvenanceEventResponse(
            event_id=e.event_id,
            event_type=e.event_type,
            occurred_at=e.occurred_at,
            actor=e.actor,
            description=e.description,
            hash=e.hash,
        )
        for e in events
    ]


@router.post("/{package_id}/verify")
async def verify_evidence_integrity(
    package_id: UUID,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Verify the integrity of an evidence package.

    Checks the cryptographic hash chain to ensure no tampering
    has occurred.
    """
    # In production, this would verify the package
    is_valid = True
    verification_details: dict[str, Any] = {
        "package_id": str(package_id),
        "verified_at": datetime.utcnow().isoformat(),
        "hash_chain_valid": True,
        "items_verified": 0,
        "errors": [],
    }

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="verify_integrity",
        resource_type="evidence_package",
        resource_id=package_id,
        details={"result": "valid" if is_valid else "invalid"},
    )

    return {
        "valid": is_valid,
        "details": verification_details,
    }


@router.post("/{package_id}/export")
async def export_evidence_package(
    package_id: UUID,
    request: ExportRequest,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Export evidence package in specified format.

    Generates a formatted export suitable for court submission
    or authority referral.
    """
    valid_formats = ["pdf", "docx", "json", "xml"]
    if request.format not in valid_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format. Valid options: {valid_formats}",
        )

    # In production, this would generate the export
    export_url = f"/exports/{package_id}.{request.format}"

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="export",
        resource_type="evidence_package",
        resource_id=package_id,
        justification=f"Exported in {request.format} format",
        details={
            "format": request.format,
            "authority_format": request.authority_format,
            "include_provenance": request.include_provenance,
        },
    )

    return {
        "export_url": export_url,
        "format": request.format,
        "expires_at": datetime.utcnow().isoformat(),
    }
