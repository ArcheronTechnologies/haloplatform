"""
Audit log ORM model aligned with Archeron Ontology.

Separate storage for tamper resistance and compliance.
"""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from halo.models.base import OntologyBase as Base


class ActorType(str, enum.Enum):
    """Types of actors that can generate audit events."""

    SYSTEM = "SYSTEM"
    USER = "USER"
    API = "API"


class AuditLog(Base):
    """
    Audit log table.

    Stores all audit events for compliance and security.
    Designed for append-only operation and tamper resistance.
    """

    __tablename__ = "onto_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)

    # Actor
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type_enum"), nullable=False
    )
    actor_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Target
    target_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Event details
    event_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Request context
    request_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_audit_timestamp", "event_timestamp"),
        Index("idx_audit_target", "target_type", "target_id"),
        Index("idx_audit_actor", "actor_type", "actor_id"),
        Index("idx_audit_event_type", "event_type"),
    )


# Audit event types as defined in the ontology
AUDIT_EVENT_TYPES = {
    # Entity lifecycle
    "ENTITY_CREATE": {"retention_years": 3},
    "ENTITY_UPDATE": {"retention_years": 3},
    "ENTITY_MERGE": {"retention_years": 3},
    "ENTITY_SPLIT": {"retention_years": 3},
    "ENTITY_ANONYMIZE": {"retention_years": 3},
    # Fact lifecycle
    "FACT_CREATE": {"retention_years": 3},
    "FACT_SUPERSEDE": {"retention_years": 3},
    # Resolution
    "RESOLUTION_DECISION": {"retention_years": 3},
    "HUMAN_REVIEW": {"retention_years": 3},
    # Access
    "PII_QUERY": {"retention_years": 0.5},  # 6 months
    "ENTITY_VIEW": {"retention_years": 1},
    "GRAPH_TRAVERSAL": {"retention_years": 1},
    # Pattern detection
    "PATTERN_MATCH": {"retention_years": 3},
    "ALERT_GENERATED": {"retention_years": 3},
    # Export
    "EXPORT_EVIDENCE": {"retention_years": 3},
    "REFERRAL_GENERATED": {"retention_years": 3},
    # System
    "DERIVATION_JOB": {"retention_years": 1},
    "INGESTION_BATCH": {"retention_years": 1},
}
