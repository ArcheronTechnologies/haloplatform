"""
Evidence management for investigations.

Tracks evidence items and maintains chain of custody.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class EvidenceType(str, Enum):
    """Types of evidence."""

    DOCUMENT = "document"
    TRANSACTION = "transaction"
    TRANSACTION_RECORD = "transaction_record"  # Alias for backward compat
    COMMUNICATION = "communication"
    SCREENSHOT = "screenshot"
    DATABASE_RECORD = "database_record"
    API_RESPONSE = "api_response"
    REPORT = "report"
    WITNESS_STATEMENT = "witness_statement"
    ANALYSIS = "analysis"
    LINK = "link"  # External reference
    OTHER = "other"


class EvidenceStatus(str, Enum):
    """Status of evidence in the investigation."""

    COLLECTED = "collected"
    UNDER_REVIEW = "under_review"
    VERIFIED = "verified"
    CHALLENGED = "challenged"  # Authenticity questioned
    EXCLUDED = "excluded"  # Not admissible
    ARCHIVED = "archived"


@dataclass
class ChainOfCustodyEntry:
    """Entry in the chain of custody."""

    id: UUID = field(default_factory=uuid4)
    action: str = ""  # collected, transferred, reviewed, modified, etc.
    actor_id: UUID = None
    actor_name: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""
    location: str = ""  # Where the evidence was at this point

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "action": self.action,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "actor_name": self.actor_name,
            "timestamp": self.timestamp.isoformat(),
            "notes": self.notes,
            "location": self.location,
        }


@dataclass
class Evidence:
    """An evidence item."""

    id: UUID = field(default_factory=uuid4)
    evidence_type: EvidenceType = EvidenceType.OTHER
    status: EvidenceStatus = EvidenceStatus.COLLECTED

    # Description
    title: str = ""
    description: str = ""
    source: str = ""  # Where/how collected

    # Content
    content: Optional[str] = None  # Text content or structured data
    content_bytes: Optional[bytes] = None  # Raw binary content
    file_path: Optional[str] = None  # Path to file if applicable
    file_hash: Optional[str] = None  # SHA-256 hash for integrity
    hash: Optional[str] = None  # SHA-256 hash of content (alias for file_hash)
    file_size: Optional[int] = None
    mime_type: Optional[str] = None

    # External reference
    external_url: Optional[str] = None
    external_id: Optional[str] = None

    # Linked entities
    entity_ids: list[UUID] = field(default_factory=list)
    transaction_ids: list[UUID] = field(default_factory=list)
    case_ids: list[UUID] = field(default_factory=list)

    # Chain of custody
    chain_of_custody: list[ChainOfCustodyEntry] = field(default_factory=list)

    # Metadata
    collected_at: datetime = field(default_factory=datetime.utcnow)
    collected_by: Optional[UUID] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Tags for categorization
    tags: list[str] = field(default_factory=list)

    # Relevance to investigation
    relevance_score: float = 0.0  # 0-1, how relevant to the case
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "evidence_type": self.evidence_type.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "has_content": self.content is not None,
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "external_url": self.external_url,
            "external_id": self.external_id,
            "entity_ids": [str(e) for e in self.entity_ids],
            "transaction_ids": [str(t) for t in self.transaction_ids],
            "case_ids": [str(c) for c in self.case_ids],
            "chain_of_custody": [c.to_dict() for c in self.chain_of_custody],
            "collected_at": self.collected_at.isoformat(),
            "collected_by": str(self.collected_by) if self.collected_by else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
            "relevance_score": self.relevance_score,
            "notes": self.notes,
        }

    def add_custody_entry(
        self,
        action: str,
        actor_id: Optional[UUID] = None,
        actor_name: str = "",
        notes: str = "",
        location: str = "",
    ) -> ChainOfCustodyEntry:
        """Add an entry to the chain of custody."""
        entry = ChainOfCustodyEntry(
            action=action,
            actor_id=actor_id,
            actor_name=actor_name,
            notes=notes,
            location=location,
        )
        self.chain_of_custody.append(entry)
        self.updated_at = datetime.utcnow()
        return entry

    def verify_integrity(self) -> bool:
        """Verify file integrity using stored hash."""
        if not self.file_path or not self.file_hash:
            return True  # No file to verify

        try:
            current_hash = self._calculate_file_hash(self.file_path)
            return current_hash == self.file_hash
        except Exception as e:
            logger.error(f"Error verifying evidence {self.id}: {e}")
            return False

    @staticmethod
    def _calculate_file_hash(file_path: str) -> str:
        """Calculate SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


@dataclass
class EvidenceChain:
    """
    A collection of related evidence items.

    Used to group evidence that supports a particular finding.
    """

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""
    case_id: Optional[UUID] = None

    # Evidence items in this chain
    evidence_ids: list[UUID] = field(default_factory=list)

    # What this evidence chain proves/supports
    conclusion: str = ""
    confidence: float = 0.0  # 0-1

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[UUID] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "case_id": str(self.case_id) if self.case_id else None,
            "evidence_ids": [str(e) for e in self.evidence_ids],
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "created_by": str(self.created_by) if self.created_by else None,
        }


class EvidenceCollector:
    """
    Collects and manages evidence for investigations.

    Handles evidence creation, storage, and chain of custody.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the evidence collector.

        Args:
            storage_path: Path for storing evidence files
        """
        self.storage_path = storage_path or Path("./evidence")

        # In-memory storage for demo
        self._evidence: dict[UUID, Evidence] = {}
        self._chains: dict[UUID, EvidenceChain] = {}

    def add_evidence(
        self,
        case_id: UUID,
        title: str,
        evidence_type: EvidenceType,
        source: str,
        content: bytes,
        collected_by: UUID,
    ) -> Evidence:
        """
        Add evidence to a case.

        Args:
            case_id: Case to add evidence to
            title: Evidence title
            evidence_type: Type of evidence
            source: Source of evidence
            content: Raw content bytes
            collected_by: User collecting the evidence

        Returns:
            Created Evidence object with hash and chain of custody
        """
        # Calculate hash of content
        content_hash = hashlib.sha256(content).hexdigest()

        evidence = Evidence(
            evidence_type=evidence_type,
            title=title,
            source=source,
            content_bytes=content,
            file_hash=content_hash,
            hash=content_hash,
            collected_by=collected_by,
        )

        evidence.case_ids.append(case_id)

        # Initial chain of custody entry
        evidence.add_custody_entry(
            action="collected",
            actor_id=collected_by,
            notes=f"Evidence collected from {source}",
        )

        self._evidence[evidence.id] = evidence

        logger.info(f"Added evidence: {title}")

        return evidence

    def verify_integrity(self, evidence: Evidence, content: bytes) -> bool:
        """
        Verify evidence content matches its hash.

        Args:
            evidence: Evidence object to verify
            content: Content bytes to check against hash

        Returns:
            True if content matches hash, False otherwise
        """
        if not evidence.hash:
            return False

        current_hash = hashlib.sha256(content).hexdigest()
        return current_hash == evidence.hash

    def record_access(
        self,
        evidence_id: UUID,
        user_id: UUID,
        action: str,
    ) -> Evidence:
        """
        Record access to evidence in chain of custody.

        Args:
            evidence_id: Evidence being accessed
            user_id: User accessing the evidence
            action: Type of access (e.g., 'reviewed', 'exported')

        Returns:
            Updated Evidence object
        """
        evidence = self._evidence.get(evidence_id)
        if not evidence:
            raise ValueError(f"Evidence not found: {evidence_id}")

        evidence.add_custody_entry(
            action=action,
            actor_id=user_id,
            notes=f"Evidence accessed: {action}",
        )

        return evidence

    def collect_document(
        self,
        title: str,
        file_path: str,
        source: str,
        collected_by: Optional[UUID] = None,
        description: str = "",
        entity_ids: Optional[list[UUID]] = None,
        case_id: Optional[UUID] = None,
    ) -> Evidence:
        """
        Collect a document as evidence.

        Args:
            title: Evidence title
            file_path: Path to the document
            source: How/where the document was obtained
            collected_by: User who collected it
            description: Description of the document
            entity_ids: Related entity IDs
            case_id: Related case ID

        Returns:
            Created Evidence object
        """
        path = Path(file_path)

        # Calculate hash for integrity
        file_hash = Evidence._calculate_file_hash(file_path)

        evidence = Evidence(
            evidence_type=EvidenceType.DOCUMENT,
            title=title,
            description=description,
            source=source,
            file_path=file_path,
            file_hash=file_hash,
            file_size=path.stat().st_size,
            mime_type=self._guess_mime_type(path),
            entity_ids=entity_ids or [],
            collected_by=collected_by,
        )

        if case_id:
            evidence.case_ids.append(case_id)

        # Initial chain of custody entry
        evidence.add_custody_entry(
            action="collected",
            actor_id=collected_by,
            notes=f"Document collected from {source}",
            location=file_path,
        )

        self._evidence[evidence.id] = evidence

        logger.info(f"Collected document evidence: {title}")

        return evidence

    def collect_transaction(
        self,
        transaction_data: dict,
        source: str,
        collected_by: Optional[UUID] = None,
        entity_ids: Optional[list[UUID]] = None,
        case_id: Optional[UUID] = None,
    ) -> Evidence:
        """
        Collect a transaction as evidence.

        Args:
            transaction_data: Transaction data dict
            source: Source system
            collected_by: User who collected it
            entity_ids: Related entity IDs
            case_id: Related case ID

        Returns:
            Created Evidence object
        """
        import json

        txn_id = transaction_data.get("id", "unknown")
        amount = transaction_data.get("amount", 0)
        currency = transaction_data.get("currency", "SEK")

        evidence = Evidence(
            evidence_type=EvidenceType.TRANSACTION,
            title=f"Transaction {txn_id}: {amount} {currency}",
            description=f"Transaction record from {source}",
            source=source,
            content=json.dumps(transaction_data, default=str),
            entity_ids=entity_ids or [],
            collected_by=collected_by,
        )

        if transaction_data.get("id"):
            evidence.transaction_ids.append(UUID(str(transaction_data["id"])))

        if case_id:
            evidence.case_ids.append(case_id)

        evidence.add_custody_entry(
            action="collected",
            actor_id=collected_by,
            notes=f"Transaction record retrieved from {source}",
        )

        self._evidence[evidence.id] = evidence

        return evidence

    def collect_api_response(
        self,
        title: str,
        response_data: dict,
        api_source: str,
        query_params: Optional[dict] = None,
        collected_by: Optional[UUID] = None,
        entity_ids: Optional[list[UUID]] = None,
        case_id: Optional[UUID] = None,
    ) -> Evidence:
        """
        Collect an API response as evidence.

        Args:
            title: Evidence title
            response_data: API response data
            api_source: API that was queried
            query_params: Parameters used in the query
            collected_by: User who collected it
            entity_ids: Related entity IDs
            case_id: Related case ID

        Returns:
            Created Evidence object
        """
        import json

        content = {
            "api_source": api_source,
            "query_params": query_params,
            "response": response_data,
            "collected_at": datetime.utcnow().isoformat(),
        }

        evidence = Evidence(
            evidence_type=EvidenceType.API_RESPONSE,
            title=title,
            description=f"API response from {api_source}",
            source=api_source,
            content=json.dumps(content, default=str),
            external_id=api_source,
            entity_ids=entity_ids or [],
            collected_by=collected_by,
        )

        if case_id:
            evidence.case_ids.append(case_id)

        evidence.add_custody_entry(
            action="collected",
            actor_id=collected_by,
            notes=f"API response collected from {api_source}",
        )

        self._evidence[evidence.id] = evidence

        return evidence

    def collect_screenshot(
        self,
        title: str,
        file_path: str,
        url: str,
        collected_by: Optional[UUID] = None,
        description: str = "",
        case_id: Optional[UUID] = None,
    ) -> Evidence:
        """
        Collect a screenshot as evidence.

        Args:
            title: Evidence title
            file_path: Path to screenshot file
            url: URL that was screenshotted
            collected_by: User who collected it
            description: Description
            case_id: Related case ID

        Returns:
            Created Evidence object
        """
        path = Path(file_path)
        file_hash = Evidence._calculate_file_hash(file_path)

        evidence = Evidence(
            evidence_type=EvidenceType.SCREENSHOT,
            title=title,
            description=description or f"Screenshot of {url}",
            source=url,
            file_path=file_path,
            file_hash=file_hash,
            file_size=path.stat().st_size,
            mime_type=self._guess_mime_type(path),
            external_url=url,
            collected_by=collected_by,
        )

        if case_id:
            evidence.case_ids.append(case_id)

        evidence.add_custody_entry(
            action="collected",
            actor_id=collected_by,
            notes=f"Screenshot captured from {url}",
            location=file_path,
        )

        self._evidence[evidence.id] = evidence

        return evidence

    def collect_analysis(
        self,
        title: str,
        analysis_content: str,
        source_evidence_ids: list[UUID],
        analyst_id: Optional[UUID] = None,
        case_id: Optional[UUID] = None,
    ) -> Evidence:
        """
        Collect an analysis as evidence.

        Args:
            title: Analysis title
            analysis_content: Analysis text
            source_evidence_ids: Evidence this analysis is based on
            analyst_id: User who performed the analysis
            case_id: Related case ID

        Returns:
            Created Evidence object
        """
        evidence = Evidence(
            evidence_type=EvidenceType.ANALYSIS,
            title=title,
            description="Analysis performed on collected evidence",
            source="internal_analysis",
            content=analysis_content,
            collected_by=analyst_id,
        )

        if case_id:
            evidence.case_ids.append(case_id)

        evidence.add_custody_entry(
            action="created",
            actor_id=analyst_id,
            notes=f"Analysis based on {len(source_evidence_ids)} evidence items",
        )

        # Add tags for source evidence
        evidence.tags.extend([f"source:{e}" for e in source_evidence_ids])

        self._evidence[evidence.id] = evidence

        return evidence

    def get_evidence(self, evidence_id: UUID) -> Optional[Evidence]:
        """Get evidence by ID."""
        return self._evidence.get(evidence_id)

    def get_for_case(self, case_id: UUID) -> list[Evidence]:
        """Get all evidence for a case."""
        return [e for e in self._evidence.values() if case_id in e.case_ids]

    def get_for_entity(self, entity_id: UUID) -> list[Evidence]:
        """Get all evidence related to an entity."""
        return [e for e in self._evidence.values() if entity_id in e.entity_ids]

    def update_status(
        self,
        evidence_id: UUID,
        new_status: EvidenceStatus,
        user_id: Optional[UUID] = None,
        notes: str = "",
    ) -> Evidence:
        """Update evidence status."""
        evidence = self._evidence.get(evidence_id)
        if not evidence:
            raise ValueError(f"Evidence not found: {evidence_id}")

        old_status = evidence.status
        evidence.status = new_status
        evidence.updated_at = datetime.utcnow()

        evidence.add_custody_entry(
            action=f"status_changed_to_{new_status.value}",
            actor_id=user_id,
            notes=notes or f"Status changed from {old_status.value} to {new_status.value}",
        )

        return evidence

    def transfer_custody(
        self,
        evidence_id: UUID,
        from_user_id: UUID,
        to_user_id: UUID,
        notes: str = "",
    ) -> Evidence:
        """Transfer evidence custody to another user."""
        evidence = self._evidence.get(evidence_id)
        if not evidence:
            raise ValueError(f"Evidence not found: {evidence_id}")

        evidence.add_custody_entry(
            action="transferred",
            actor_id=to_user_id,
            notes=notes or f"Custody transferred from {from_user_id}",
        )

        evidence.updated_at = datetime.utcnow()

        return evidence

    def create_chain(
        self,
        name: str,
        evidence_ids: list[UUID],
        case_id: Optional[UUID] = None,
        description: str = "",
        conclusion: str = "",
        created_by: Optional[UUID] = None,
    ) -> EvidenceChain:
        """
        Create an evidence chain linking related evidence.

        Args:
            name: Chain name
            evidence_ids: Evidence items to include
            case_id: Related case
            description: Description of the chain
            conclusion: What this evidence chain proves
            created_by: User creating the chain

        Returns:
            Created EvidenceChain
        """
        chain = EvidenceChain(
            name=name,
            description=description,
            case_id=case_id,
            evidence_ids=evidence_ids,
            conclusion=conclusion,
            created_by=created_by,
        )

        self._chains[chain.id] = chain

        logger.info(f"Created evidence chain: {name} with {len(evidence_ids)} items")

        return chain

    def verify_all_integrity(self) -> dict[UUID, bool]:
        """Verify integrity of all file-based evidence."""
        results = {}
        for evidence_id, evidence in self._evidence.items():
            if evidence.file_path:
                results[evidence_id] = evidence.verify_integrity()
        return results

    def _guess_mime_type(self, path: Path) -> str:
        """Guess MIME type from file extension."""
        mime_types = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".txt": "text/plain",
            ".json": "application/json",
            ".xml": "application/xml",
            ".csv": "text/csv",
        }
        return mime_types.get(path.suffix.lower(), "application/octet-stream")
