"""
Alert ORM model for real-time pattern detection.

Alerts are generated when high-risk patterns are detected,
such as new company registrations with suspicious characteristics.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from halo.models.base import OntologyBase as Base

if TYPE_CHECKING:
    from halo.models.entity import Entity


class AlertStatus(str, enum.Enum):
    """Status of an alert."""

    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATED = "INVESTIGATED"
    DISMISSED = "DISMISSED"


class Alert(Base):
    """
    Alert for detected patterns requiring attention.

    Generated in real-time when:
    - High-risk company registrations occur
    - Shell network patterns are detected
    - Unusual director changes happen
    """

    __tablename__ = "onto_alerts"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), nullable=False
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    alert_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NEW")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    entity: Mapped["Entity"] = relationship("Entity")

    __table_args__ = (
        CheckConstraint(
            "status IN ('NEW', 'ACKNOWLEDGED', 'INVESTIGATED', 'DISMISSED')",
            name="check_alert_status",
        ),
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 1",
            name="check_alert_risk_score",
        ),
        Index(
            "idx_alerts_new",
            "alert_type",
            "created_at",
            postgresql_where="status = 'NEW'",
        ),
        Index("idx_alerts_entity", "entity_id"),
    )

    def acknowledge(self, user_id: str) -> None:
        """Mark alert as acknowledged."""
        self.status = AlertStatus.ACKNOWLEDGED.value
        self.acknowledged_at = datetime.utcnow()
        self.acknowledged_by = user_id

    def investigate(self) -> None:
        """Mark alert as under investigation."""
        self.status = AlertStatus.INVESTIGATED.value

    def dismiss(self, reason: str) -> None:
        """Dismiss alert with reason."""
        self.status = AlertStatus.DISMISSED.value
        if "dismissal_reason" not in self.alert_data:
            self.alert_data["dismissal_reason"] = reason


# Common alert types
ALERT_TYPES = {
    "HIGH_RISK_REGISTRATION": "New company registration with high risk indicators",
    "SHELL_NETWORK_DETECTED": "Multiple shell companies linked to same person",
    "DIRECTOR_VELOCITY_SPIKE": "Unusual director turnover rate",
    "ADDRESS_HUB_GROWTH": "Address registration hub expansion",
    "CIRCULAR_OWNERSHIP": "Circular ownership structure detected",
}
