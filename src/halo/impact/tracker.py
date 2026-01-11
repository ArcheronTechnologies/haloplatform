"""
Impact tracking for referral and case outcomes.

Tracks the real-world outcomes of intelligence and referrals
to measure system effectiveness.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class ImpactType(str, Enum):
    """Types of impact events."""

    # Investigation lifecycle
    INVESTIGATION_OPENED = "investigation_opened"
    INVESTIGATION_CLOSED = "investigation_closed"

    # Legal actions
    CHARGES_FILED = "charges_filed"
    CONVICTION = "conviction"
    ACQUITTAL = "acquittal"
    SETTLEMENT = "settlement"

    # Financial impact
    ASSETS_SEIZED = "assets_seized"
    TAX_RECOVERED = "tax_recovered"
    FINES_IMPOSED = "fines_imposed"

    # Prevention
    FRAUD_PREVENTED = "fraud_prevented"
    ACTIVITY_DISRUPTED = "activity_disrupted"

    # Administrative
    LICENSE_REVOKED = "license_revoked"
    SANCTIONS_APPLIED = "sanctions_applied"


@dataclass
class ImpactRecord:
    """Record of a single impact event."""

    id: UUID
    referral_id: Optional[UUID]
    case_id: Optional[UUID]
    impact_type: ImpactType
    occurred_at: datetime
    recorded_at: datetime
    recorded_by: str
    authority: str
    description: str
    value_sek: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "referral_id": str(self.referral_id) if self.referral_id else None,
            "case_id": str(self.case_id) if self.case_id else None,
            "impact_type": self.impact_type.value,
            "occurred_at": self.occurred_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
            "recorded_by": self.recorded_by,
            "authority": self.authority,
            "description": self.description,
            "value_sek": self.value_sek,
            "metadata": self.metadata,
        }


class ImpactTracker:
    """
    Tracks and manages impact records.

    Maintains a record of all outcomes from referrals and investigations
    to enable effectiveness measurement and reporting.
    """

    def __init__(self):
        self.records: dict[UUID, ImpactRecord] = {}
        self._by_referral: dict[UUID, list[UUID]] = {}
        self._by_case: dict[UUID, list[UUID]] = {}

    def record(
        self,
        impact_type: ImpactType,
        authority: str,
        description: str,
        recorded_by: str,
        referral_id: Optional[UUID] = None,
        case_id: Optional[UUID] = None,
        occurred_at: Optional[datetime] = None,
        value_sek: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> ImpactRecord:
        """
        Record a new impact event.

        Args:
            impact_type: Type of impact
            authority: Authority that reported the outcome
            description: Human-readable description
            recorded_by: User recording the impact
            referral_id: Associated referral ID
            case_id: Associated case ID
            occurred_at: When the impact occurred (defaults to now)
            value_sek: Financial value in SEK
            metadata: Additional metadata

        Returns:
            The created ImpactRecord
        """
        record_id = uuid4()
        now = datetime.utcnow()

        record = ImpactRecord(
            id=record_id,
            referral_id=referral_id,
            case_id=case_id,
            impact_type=impact_type,
            occurred_at=occurred_at or now,
            recorded_at=now,
            recorded_by=recorded_by,
            authority=authority,
            description=description,
            value_sek=value_sek,
            metadata=metadata or {},
        )

        # Store record
        self.records[record_id] = record

        # Index by referral
        if referral_id:
            if referral_id not in self._by_referral:
                self._by_referral[referral_id] = []
            self._by_referral[referral_id].append(record_id)

        # Index by case
        if case_id:
            if case_id not in self._by_case:
                self._by_case[case_id] = []
            self._by_case[case_id].append(record_id)

        logger.info(
            f"Recorded impact {record_id}: {impact_type.value} "
            f"from {authority} - {description[:50]}..."
        )

        return record

    def get_by_referral(self, referral_id: UUID) -> list[ImpactRecord]:
        """Get all impact records for a referral."""
        record_ids = self._by_referral.get(referral_id, [])
        return [self.records[rid] for rid in record_ids]

    def get_by_case(self, case_id: UUID) -> list[ImpactRecord]:
        """Get all impact records for a case."""
        record_ids = self._by_case.get(case_id, [])
        return [self.records[rid] for rid in record_ids]

    def get_by_type(self, impact_type: ImpactType) -> list[ImpactRecord]:
        """Get all records of a specific impact type."""
        return [r for r in self.records.values() if r.impact_type == impact_type]

    def get_by_authority(self, authority: str) -> list[ImpactRecord]:
        """Get all records from a specific authority."""
        return [r for r in self.records.values() if r.authority == authority]

    def total_value(
        self,
        impact_type: Optional[ImpactType] = None,
        authority: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> float:
        """
        Calculate total financial value of impacts.

        Args:
            impact_type: Filter by impact type
            authority: Filter by authority
            since: Only include records after this date

        Returns:
            Total value in SEK
        """
        total = 0.0
        for record in self.records.values():
            if impact_type and record.impact_type != impact_type:
                continue
            if authority and record.authority != authority:
                continue
            if since and record.occurred_at < since:
                continue
            total += record.value_sek
        return total


def record_impact(
    tracker: ImpactTracker,
    impact_type: ImpactType,
    authority: str,
    description: str,
    recorded_by: str,
    **kwargs,
) -> ImpactRecord:
    """
    Convenience function to record an impact event.

    Args:
        tracker: The ImpactTracker instance
        impact_type: Type of impact
        authority: Authority that reported the outcome
        description: Human-readable description
        recorded_by: User recording the impact
        **kwargs: Additional arguments passed to tracker.record()

    Returns:
        The created ImpactRecord
    """
    return tracker.record(
        impact_type=impact_type,
        authority=authority,
        description=description,
        recorded_by=recorded_by,
        **kwargs,
    )
