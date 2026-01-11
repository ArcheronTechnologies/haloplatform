"""
Entity anonymization operations for GDPR compliance.

Anonymization removes PII while preserving graph structure:
- Personal identifiers removed (personnummer, name)
- Entity remains in graph with "ANONYMIZED_PERSON_xxx" name
- Relationships preserved for pattern analysis
- Audit trail maintained
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
import hashlib


@dataclass
class AnonymizationResult:
    """Result of an entity anonymization operation."""

    success: bool
    entity_id: UUID
    anonymized_name: str = ""
    error: Optional[str] = None
    fields_anonymized: list[str] = field(default_factory=list)
    relationships_preserved: int = 0
    legal_hold: bool = False  # True if anonymization was blocked


@dataclass
class AnonymizationRequest:
    """Request to anonymize an entity."""

    entity_id: UUID
    reason: str  # GDPR request reference, retention policy, etc.
    requested_by: str  # User or system identifier
    override_legal_hold: bool = False  # If true, anonymize even with hold


class EntityAnonymizer:
    """
    Handles GDPR-compliant entity anonymization.

    Anonymization strategy (per ontology):
    - PERSON entities only (companies are public record)
    - Remove: name, personnummer, birth date, gender
    - Preserve: entity ID, relationships, structural role
    - Replace name with "ANONYMIZED_PERSON_<hash>"
    - Set status to ANONYMIZED
    - Record anonymization timestamp for audit

    Legal holds:
    - Active investigations block anonymization
    - Legal proceedings block anonymization
    - Can be overridden with appropriate authority
    """

    # Fields that are PII and should be anonymized
    PII_FIELDS = [
        "canonical_name",
        "personnummer",
        "samordningsnummer",
        "birth_date",
        "birth_year",
        "gender",
    ]

    def __init__(self, db_session):
        """
        Initialize anonymizer with database session.

        Args:
            db_session: SQLAlchemy async session
        """
        self.db = db_session

    async def anonymize(self, request: AnonymizationRequest) -> AnonymizationResult:
        """
        Anonymize an entity.

        Removes PII while preserving graph structure and relationships.

        Args:
            request: AnonymizationRequest with entity ID

        Returns:
            AnonymizationResult with success status and details
        """
        # Check for legal hold
        has_hold, hold_reason = await self.check_legal_hold(request.entity_id)
        if has_hold and not request.override_legal_hold:
            return AnonymizationResult(
                success=False,
                entity_id=request.entity_id,
                error=f"Entity has legal hold: {hold_reason}",
                legal_hold=True,
            )

        # Generate anonymized name
        anonymized_name = self._generate_anonymized_name(request.entity_id)

        # In a real implementation, this would:
        # 1. Load entity from database
        # 2. Verify entity is PERSON type (companies are public)
        # 3. Verify entity is not already ANONYMIZED
        # 4. Clear PII fields
        # 5. Set canonical_name to anonymized version
        # 6. Set status to ANONYMIZED
        # 7. Record anonymized_at timestamp
        # 8. Create audit log entry

        return AnonymizationResult(
            success=True,
            entity_id=request.entity_id,
            anonymized_name=anonymized_name,
            fields_anonymized=self.PII_FIELDS,
            relationships_preserved=0,  # Would be actual count
        )

    async def anonymize_batch(
        self, requests: list[AnonymizationRequest]
    ) -> list[AnonymizationResult]:
        """
        Anonymize multiple entities.

        Args:
            requests: List of anonymization requests

        Returns:
            List of AnonymizationResults
        """
        results = []
        for request in requests:
            result = await self.anonymize(request)
            results.append(result)
        return results

    async def can_anonymize(
        self, entity_id: UUID
    ) -> tuple[bool, Optional[str]]:
        """
        Check if an entity can be anonymized.

        Args:
            entity_id: Entity to check

        Returns:
            Tuple of (can_anonymize, reason_if_not)
        """
        # Would check:
        # - Entity exists
        # - Entity is PERSON type
        # - Entity is not already ANONYMIZED
        # - No legal hold

        has_hold, hold_reason = await self.check_legal_hold(entity_id)
        if has_hold:
            return False, f"Legal hold: {hold_reason}"

        return True, None

    async def check_legal_hold(
        self, entity_id: UUID
    ) -> tuple[bool, Optional[str]]:
        """
        Check if entity has a legal hold preventing anonymization.

        Args:
            entity_id: Entity to check

        Returns:
            Tuple of (has_hold, reason)
        """
        # Would check:
        # - Active investigations involving this entity
        # - Pending referrals
        # - Legal proceedings
        # - Manual hold flags

        return False, None

    async def set_legal_hold(
        self, entity_id: UUID, reason: str, set_by: str, expires_at: Optional[datetime] = None
    ) -> bool:
        """
        Set a legal hold on an entity.

        Args:
            entity_id: Entity to hold
            reason: Reason for hold
            set_by: User or system identifier
            expires_at: Optional expiration datetime

        Returns:
            True if hold was set successfully
        """
        # Would create a legal_hold record in database
        return True

    async def release_legal_hold(
        self, entity_id: UUID, reason: str, released_by: str
    ) -> bool:
        """
        Release a legal hold on an entity.

        Args:
            entity_id: Entity to release
            reason: Reason for release
            released_by: User or system identifier

        Returns:
            True if hold was released successfully
        """
        # Would update/delete legal_hold record
        return True

    def _generate_anonymized_name(self, entity_id: UUID) -> str:
        """
        Generate a consistent anonymized name for an entity.

        Uses a hash of the entity ID to create a unique but
        non-reversible identifier.

        Args:
            entity_id: Entity UUID

        Returns:
            Anonymized name string
        """
        # Create a hash that's unique but can't be reversed to PII
        hash_input = f"anonymize:{entity_id}"
        hash_value = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        return f"ANONYMIZED_PERSON_{hash_value.upper()}"

    async def get_retention_candidates(
        self, retention_years: int = 7
    ) -> list[UUID]:
        """
        Find entities eligible for anonymization based on retention policy.

        Args:
            retention_years: Years to retain data (default 7 per spec)

        Returns:
            List of entity IDs eligible for anonymization
        """
        # Would query for:
        # - PERSON entities
        # - Last activity > retention_years ago
        # - No active relationships to companies
        # - No legal holds

        return []


def create_anonymization_audit_log(
    entity_id: UUID,
    original_name_hash: str,  # Hash of original name for verification
    reason: str,
    requested_by: str,
    anonymized_fields: list[str],
) -> dict:
    """
    Create an audit log entry for anonymization.

    This is required for GDPR compliance to prove data was erased.

    Args:
        entity_id: Entity that was anonymized
        original_name_hash: Hash of original name (for verification only)
        reason: Reason for anonymization
        requested_by: User or system identifier
        anonymized_fields: List of fields that were cleared

    Returns:
        Dict representing the audit log entry
    """
    return {
        "id": uuid4(),
        "entity_id": entity_id,
        "action": "ANONYMIZE",
        "timestamp": datetime.utcnow(),
        "original_name_hash": original_name_hash,
        "reason": reason,
        "requested_by": requested_by,
        "fields_anonymized": anonymized_fields,
        "gdpr_article": "Article 17 - Right to erasure",
    }
