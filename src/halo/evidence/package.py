"""
Evidence package compilation for court-grade evidence.

Creates structured evidence packages that can be used in legal proceedings.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class PackageStatus(str, Enum):
    """Status of an evidence package."""

    DRAFT = "draft"
    COMPILING = "compiling"
    REVIEW = "review"
    SEALED = "sealed"
    EXPORTED = "exported"


@dataclass
class EvidenceItem:
    """Single piece of evidence in a package."""

    id: UUID
    item_type: str  # document, transaction, entity, detection, etc.
    title: str
    description: str
    source: str
    source_timestamp: datetime
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance_id: Optional[UUID] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "item_type": self.item_type,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "source_timestamp": self.source_timestamp.isoformat(),
            "content_hash": self.content_hash,
            "metadata": self.metadata,
            "provenance_id": str(self.provenance_id) if self.provenance_id else None,
        }


@dataclass
class EvidencePackage:
    """
    A complete evidence package for legal proceedings.

    Contains all evidence, provenance chain, and metadata needed
    for court-grade evidence submission.
    """

    id: UUID
    case_id: UUID
    title: str
    status: PackageStatus
    created_at: datetime
    created_by: str
    items: list[EvidenceItem] = field(default_factory=list)
    summary: str = ""
    package_hash: Optional[str] = None
    sealed_at: Optional[datetime] = None
    sealed_by: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_item(self, item: EvidenceItem) -> None:
        """Add an evidence item to the package."""
        if self.status == PackageStatus.SEALED:
            raise ValueError("Cannot add items to a sealed package")
        self.items.append(item)
        logger.info(f"Added evidence item {item.id} to package {self.id}")

    def calculate_hash(self) -> str:
        """Calculate the integrity hash of the entire package."""
        hasher = hashlib.sha256()

        # Include all item hashes in order
        for item in sorted(self.items, key=lambda x: str(x.id)):
            hasher.update(item.content_hash.encode())

        # Include package metadata
        hasher.update(str(self.id).encode())
        hasher.update(str(self.case_id).encode())
        hasher.update(self.title.encode())

        return hasher.hexdigest()

    def seal(self, sealed_by: str) -> None:
        """
        Seal the package, preventing further modifications.

        Once sealed, the package hash is calculated and stored.
        """
        if self.status == PackageStatus.SEALED:
            raise ValueError("Package is already sealed")

        self.package_hash = self.calculate_hash()
        self.sealed_at = datetime.utcnow()
        self.sealed_by = sealed_by
        self.status = PackageStatus.SEALED

        logger.info(f"Sealed evidence package {self.id} with hash {self.package_hash}")

    def verify_integrity(self) -> bool:
        """Verify the package hasn't been tampered with."""
        if not self.package_hash:
            return False
        return self.calculate_hash() == self.package_hash

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "case_id": str(self.case_id),
            "title": self.title,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "items": [item.to_dict() for item in self.items],
            "summary": self.summary,
            "package_hash": self.package_hash,
            "sealed_at": self.sealed_at.isoformat() if self.sealed_at else None,
            "sealed_by": self.sealed_by,
            "metadata": self.metadata,
        }


def create_evidence_package(
    case_id: UUID,
    title: str,
    created_by: str,
    summary: str = "",
    metadata: Optional[dict] = None,
) -> EvidencePackage:
    """
    Create a new evidence package.

    Args:
        case_id: ID of the associated case
        title: Package title
        created_by: User who created the package
        summary: Brief summary of the evidence
        metadata: Additional metadata

    Returns:
        New EvidencePackage instance
    """
    return EvidencePackage(
        id=uuid4(),
        case_id=case_id,
        title=title,
        status=PackageStatus.DRAFT,
        created_at=datetime.utcnow(),
        created_by=created_by,
        summary=summary,
        metadata=metadata or {},
    )


def create_evidence_item(
    item_type: str,
    title: str,
    description: str,
    source: str,
    content: bytes,
    metadata: Optional[dict] = None,
) -> EvidenceItem:
    """
    Create a new evidence item with automatic hash calculation.

    Args:
        item_type: Type of evidence (document, transaction, etc.)
        title: Item title
        description: Detailed description
        source: Source of the evidence
        content: Raw content bytes for hashing
        metadata: Additional metadata

    Returns:
        New EvidenceItem instance
    """
    content_hash = hashlib.sha256(content).hexdigest()

    return EvidenceItem(
        id=uuid4(),
        item_type=item_type,
        title=title,
        description=description,
        source=source,
        source_timestamp=datetime.utcnow(),
        content_hash=content_hash,
        metadata=metadata or {},
    )
