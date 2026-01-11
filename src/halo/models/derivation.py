"""
Derivation ORM models for nightly computation jobs.

Tracks derivation rules, job runs, and derived fact configuration.
"""

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from halo.models.base import OntologyBase as Base


class DerivationRuleType(str, enum.Enum):
    """Types of derivation rules."""

    RISK_SCORE = "RISK_SCORE"
    NETWORK_CLUSTER = "NETWORK_CLUSTER"
    SHELL_INDICATOR = "SHELL_INDICATOR"
    VELOCITY = "VELOCITY"
    ADDRESS_STATS = "ADDRESS_STATS"


class DerivationRunStatus(str, enum.Enum):
    """Status of derivation job runs."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DerivationRule(Base):
    """
    Derivation rule configuration.

    Defines how derived facts are computed in nightly batch jobs.
    """

    __tablename__ = "onto_derivation_rules"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    rule_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    rule_type: Mapped[DerivationRuleType] = mapped_column(
        Enum(DerivationRuleType, name="derivation_rule_type"), nullable=False
    )
    rule_definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index(
            "idx_derivation_rules_active",
            "rule_type",
            postgresql_where="active = TRUE",
        ),
    )


class DerivationRun(Base):
    """
    Derivation job run tracking.

    Logs each nightly computation job for monitoring and debugging.
    """

    __tablename__ = "onto_derivation_runs"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="RUNNING"
    )
    entities_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    facts_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="check_run_status",
        ),
        Index("idx_derivation_runs_status", "status", "started_at"),
    )

    def complete(self, entities_processed: int, facts_created: int) -> None:
        """Mark run as complete."""
        self.completed_at = datetime.utcnow()
        self.status = "COMPLETED"
        self.entities_processed = entities_processed
        self.facts_created = facts_created

    def fail(self, error: str) -> None:
        """Mark run as failed."""
        self.completed_at = datetime.utcnow()
        self.status = "FAILED"
        self.errors.append({"timestamp": datetime.utcnow().isoformat(), "error": error})
