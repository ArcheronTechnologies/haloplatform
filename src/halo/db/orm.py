"""
SQLAlchemy database models for Halo platform.

Implements the entity graph model with support for:
- User authentication and session management
- People, companies, properties, and vehicles
- Relationships between entities
- Documents with NLP analysis results
- Financial transactions for AML
- Alerts with tiered human-in-loop review
- Immutable audit logging with hash chain integrity
- Investigation cases with need-to-know access control

Security:
- PII fields encrypted at rest using AES-256-GCM
- Blind indexing uses HMAC (not plain SHA-256)
- Audit logs use hash chain for tamper detection
- Case-level access control (not just role-based)
"""

import enum
import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from halo.db.types import EncryptedPersonnummer, EncryptedOrganisationsnummer, EncryptedAccountNumber


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class UserRole(enum.Enum):
    """User roles for RBAC."""
    VIEWER = "viewer"
    ANALYST = "analyst"
    SENIOR_ANALYST = "senior_analyst"
    ADMIN = "admin"
    SYSTEM = "system"


class User(Base):
    """
    User authentication and profile.

    Security features:
    - Argon2id password hashing
    - Account lockout after failed attempts
    - Session management
    - MFA ready (totp_secret field)
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Credentials
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Profile
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.VIEWER)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Security - Lockout
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_failed_login: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Security - MFA (optional TOTP)
    totp_secret: Mapped[Optional[str]] = mapped_column(String(32))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Security - Password policy
    password_changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)

    # Sessions
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    sessions: Mapped[list["UserSession"]] = relationship("UserSession", back_populates="user")
    case_assignments: Mapped[list["CaseAssignment"]] = relationship("CaseAssignment", back_populates="user")

    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
    )

    @property
    def is_locked(self) -> bool:
        """Check if account is currently locked."""
        if self.locked_until is None:
            return False
        return datetime.utcnow() < self.locked_until

    def record_failed_login(self) -> None:
        """Record a failed login attempt and potentially lock account."""
        self.failed_login_attempts += 1
        self.last_failed_login = datetime.utcnow()

        # Lock after 5 failed attempts for 30 minutes
        if self.failed_login_attempts >= 5:
            from datetime import timedelta
            self.locked_until = datetime.utcnow() + timedelta(minutes=30)

    def record_successful_login(self, ip_address: str) -> None:
        """Record a successful login and reset lockout."""
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login = datetime.utcnow()
        self.last_login_ip = ip_address


class UserSession(Base):
    """
    User session tracking for concurrent session control.

    Security features:
    - Single active session per user (configurable)
    - Session invalidation on password change
    - Device fingerprinting
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Session token (hashed)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # Device info
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))

    # Validity
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")

    __table_args__ = (
        Index("idx_sessions_user", "user_id"),
        Index("idx_sessions_token", "token_hash"),
        Index("idx_sessions_expires", "expires_at"),
    )

    @property
    def is_valid(self) -> bool:
        """Check if session is still valid."""
        if self.revoked_at is not None:
            return False
        return datetime.utcnow() < self.expires_at


class EntityType(enum.Enum):
    """Types of entities tracked in the system."""

    PERSON = "person"
    COMPANY = "company"
    PROPERTY = "property"
    VEHICLE = "vehicle"
    EVENT = "event"


class Entity(Base):
    """
    Core entity table - people, companies, properties, vehicles.

    Uses PostgreSQL JSONB for flexible attributes while maintaining
    typed columns for searchable/indexable fields.

    Security: personnummer and organisationsnummer are encrypted at rest.
    A hash of the identifier is stored separately for indexed lookups.
    """

    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[EntityType] = mapped_column(SQLEnum(EntityType), nullable=False)

    # Common identifiers - ENCRYPTED at rest
    # Note: Encrypted values are stored, but a hash is used for lookups
    personnummer: Mapped[Optional[str]] = mapped_column(EncryptedPersonnummer(), unique=False)
    organisationsnummer: Mapped[Optional[str]] = mapped_column(EncryptedOrganisationsnummer(), unique=False)

    # Hash of identifiers for indexed lookups (SHA-256, truncated)
    # This allows searching without decrypting all records
    personnummer_hash: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)
    organisationsnummer_hash: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)

    # Display name (computed/cached)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Flexible attributes as JSONB
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Source tracking
    sources: Mapped[list] = mapped_column(ARRAY(String), default=list)

    # Risk level for quick filtering
    risk_level: Mapped[Optional[str]] = mapped_column(String(20))  # 'low', 'medium', 'high', 'very_high'
    status: Mapped[str] = mapped_column(String(20), default="active")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    relationships_from: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.from_entity_id",
        back_populates="from_entity",
    )
    relationships_to: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.to_entity_id",
        back_populates="to_entity",
    )

    @property
    def identifier(self) -> Optional[str]:
        """Get the primary identifier for this entity."""
        if self.entity_type == EntityType.PERSON:
            return self.personnummer
        elif self.entity_type == EntityType.COMPANY:
            return self.organisationsnummer
        return self.display_name


class RelationshipType(enum.Enum):
    """Types of relationships between entities."""

    # Person-Company
    OWNER = "owner"
    OWNS = "owns"  # Generic ownership
    BOARD_MEMBER = "board_member"
    BOARD_CHAIR = "board_chair"
    BOARD_DEPUTY = "board_deputy"
    CEO = "ceo"
    EMPLOYEE = "employee"
    EMPLOYED_BY = "employed_by"
    BENEFICIAL_OWNER = "beneficial_owner"
    SIGNATORY = "signatory"
    AUDITOR = "auditor"

    # Person-Person
    FAMILY = "family"
    SPOUSE = "spouse"
    BUSINESS_PARTNER = "business_partner"
    ASSOCIATED = "associated"  # General association

    # Company-Company
    SUBSIDIARY = "subsidiary"
    PARENT = "parent"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"

    # Person/Company-Property
    OWNS_PROPERTY = "owns_property"
    REGISTERED_AT = "registered_at"
    COLOCATED = "colocated"  # Same address

    # Person-Vehicle
    OWNS_VEHICLE = "owns_vehicle"

    # Financial
    TRANSACTED_WITH = "transacted_with"


class EntityRelationship(Base):
    """Relationships between entities."""

    __tablename__ = "entity_relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    from_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(
        SQLEnum(RelationshipType), nullable=False
    )

    # Relationship metadata
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    # Validity period
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Source
    source: Mapped[str] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    from_entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[from_entity_id])
    to_entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[to_entity_id])

    __table_args__ = (
        Index("idx_relationships_from", "from_entity_id"),
        Index("idx_relationships_to", "to_entity_id"),
        Index("idx_relationships_type", "relationship_type"),
    )


class Document(Base):
    """Ingested documents for NLP analysis."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Document metadata
    title: Mapped[Optional[str]] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # 'upload', 'scrape', 'api'
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(
        String(50)
    )  # 'forum_post', 'news', 'report', etc.

    # Content
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="sv")

    # NLP results (populated after analysis)
    entities_extracted: Mapped[dict] = mapped_column(JSONB, default=dict)
    sentiment_scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    threat_indicators: Mapped[list] = mapped_column(ARRAY(String), default=list)
    summary: Mapped[Optional[str]] = mapped_column(Text)

    # Processing status
    processed: Mapped[bool] = mapped_column(default=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Link to entities mentioned
    mentioned_entities: Mapped[list["DocumentEntityMention"]] = relationship(
        "DocumentEntityMention", back_populates="document"
    )


class DocumentEntityMention(Base):
    """Links documents to entities mentioned in them."""

    __tablename__ = "document_entity_mentions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )

    # Where in document
    start_char: Mapped[int] = mapped_column()
    end_char: Mapped[int] = mapped_column()
    mention_text: Mapped[str] = mapped_column(String(500))

    # Confidence
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    document: Mapped["Document"] = relationship("Document", back_populates="mentioned_entities")


class Transaction(Base):
    """
    Financial transactions for AML analysis.

    Security: Account numbers are encrypted at rest.
    """

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Transaction details
    transaction_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # Parties
    from_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id")
    )
    to_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id")
    )
    # Account numbers - ENCRYPTED at rest
    from_account: Mapped[str] = mapped_column(EncryptedAccountNumber())
    to_account: Mapped[str] = mapped_column(EncryptedAccountNumber())

    # Amount
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="SEK")

    # Metadata
    transaction_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Risk scoring (populated by anomaly detection)
    risk_score: Mapped[Optional[float]] = mapped_column(Float)
    risk_factors: Mapped[list] = mapped_column(ARRAY(String), default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_transactions_timestamp", "timestamp"),
        Index("idx_transactions_from", "from_entity_id"),
        Index("idx_transactions_to", "to_entity_id"),
    )


class Alert(Base):
    """
    Alerts generated by anomaly detection.

    CRITICAL: Implements tiered human-in-loop review system required by
    Brottsdatalagen 2 kap. 19 §. See "Human-in-Loop Compliance Framework"
    section for full details.

    Tiers:
    - Tier 1: Informational only, no review needed
    - Tier 2: Requires acknowledgment before export
    - Tier 3: Requires explicit approval with justification
    """

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Alert details
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'critical', 'high', 'medium', 'low'
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Related entities
    entity_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    transaction_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)

    # Scoring
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # === HUMAN-IN-LOOP COMPLIANCE ===

    # Tier determines review requirements (1, 2, or 3)
    tier: Mapped[int] = mapped_column(default=2)

    # Does this alert affect an identifiable person?
    affects_person: Mapped[bool] = mapped_column(default=True)

    # Tier 2: Acknowledgment (human saw it)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(100))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Tier 3: Approval (human approved action)
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    approval_decision: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # 'approved', 'rejected', 'escalated'
    approval_justification: Mapped[Optional[str]] = mapped_column(Text)

    # Review quality metrics (for rubber-stamp detection)
    review_displayed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    review_duration_seconds: Mapped[Optional[float]] = mapped_column(Float)

    # Legacy status field (kept for compatibility)
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_alerts_status", "status"),
        Index("idx_alerts_severity", "severity"),
        Index("idx_alerts_tier", "tier"),
        Index("idx_alerts_pending_review", "tier", "acknowledged_at", "approved_at"),
    )

    @property
    def can_export(self) -> bool:
        """Check if alert can be exported/actioned based on review status."""
        if self.tier <= 1:
            return True
        if self.tier == 2:
            return self.acknowledged_by is not None
        if self.tier == 3:
            return self.approval_decision == "approved"
        return False

    @property
    def review_status(self) -> str:
        """Human-readable review status."""
        if self.tier <= 1:
            return "no_review_needed"
        if self.tier == 2:
            if self.acknowledged_by:
                return "acknowledged"
            return "pending_acknowledgment"
        if self.tier == 3:
            if self.approval_decision:
                return f"decision_{self.approval_decision}"
            return "pending_approval"
        return "unknown"

    @property
    def is_rubber_stamp(self) -> bool:
        """Flag if review was suspiciously fast (<2 seconds)."""
        if self.review_duration_seconds is None:
            return False
        return self.review_duration_seconds < 2.0


class AuditLog(Base):
    """
    Immutable audit log - CRITICAL for Säkerhetsskyddslagen compliance.

    Every access to entity data must be logged with:
    - WHO accessed
    - WHAT was accessed
    - WHEN it was accessed
    - WHY (justification)

    Security: Uses hash chain for tamper detection.
    Each entry includes HMAC of previous entry, creating an append-only chain.
    If any entry is modified or deleted, the chain verification will fail.

    Retention: 25 years for classified data.
    """

    __tablename__ = "audit_log"

    # Sequential ID for ordering (in addition to UUID)
    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, default=uuid.uuid4)

    # Hash chain integrity
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="GENESIS")
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Who
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    user_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # What
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'view', 'search', 'export', 'update'
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'entity', 'document', 'transaction'
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))

    # Details
    details: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Why (justification)
    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id")
    )
    justification: Mapped[Optional[str]] = mapped_column(Text)

    # When
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Request metadata
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))

    __table_args__ = (
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
        Index("idx_audit_sequence", "sequence_id"),
    )

    @staticmethod
    def compute_entry_hash(
        previous_hash: str,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: Optional[uuid.UUID],
        timestamp: datetime,
        audit_key: bytes,
    ) -> str:
        """
        Compute HMAC hash for this audit entry.

        The hash includes:
        - Previous entry's hash (chain link)
        - All entry fields
        - HMAC key (prevents forgery)

        Args:
            previous_hash: Hash of the previous entry (or "GENESIS")
            user_id: User who performed the action
            action: The action performed
            resource_type: Type of resource accessed
            resource_id: ID of resource accessed
            timestamp: When the action occurred
            audit_key: Secret key for HMAC

        Returns:
            Hex-encoded HMAC-SHA256
        """
        data = json.dumps({
            "previous_hash": previous_hash,
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "timestamp": timestamp.isoformat(),
        }, sort_keys=True)

        return hmac.new(audit_key, data.encode("utf-8"), "sha256").hexdigest()

    @classmethod
    def verify_chain(cls, entries: list["AuditLog"], audit_key: bytes) -> tuple[bool, Optional[int]]:
        """
        Verify the integrity of a chain of audit entries.

        Args:
            entries: List of AuditLog entries in sequence order
            audit_key: Secret key for HMAC verification

        Returns:
            Tuple of (is_valid, first_invalid_sequence_id)
            If valid, returns (True, None)
            If invalid, returns (False, sequence_id_of_first_invalid_entry)
        """
        if not entries:
            return True, None

        # First entry must link to GENESIS
        if entries[0].previous_hash != "GENESIS":
            return False, entries[0].sequence_id

        for i, entry in enumerate(entries):
            # Compute expected hash
            expected_hash = cls.compute_entry_hash(
                previous_hash=entry.previous_hash,
                user_id=entry.user_id,
                action=entry.action,
                resource_type=entry.resource_type,
                resource_id=entry.resource_id,
                timestamp=entry.timestamp,
                audit_key=audit_key,
            )

            # Verify this entry's hash
            if not hmac.compare_digest(expected_hash, entry.entry_hash):
                return False, entry.sequence_id

            # Verify chain link (except for first entry)
            if i > 0:
                if entry.previous_hash != entries[i - 1].entry_hash:
                    return False, entry.sequence_id

        return True, None


class CaseAccessLevel(enum.Enum):
    """Access levels for case assignments."""
    READ = "read"
    WRITE = "write"
    OWNER = "owner"


class CaseAssignment(Base):
    """
    Case-level access control (need-to-know enforcement).

    Not everyone with ANALYST role can access every case.
    Users must be explicitly assigned to cases they need to work on.

    Security: Implements need-to-know principle required by Säkerhetsskyddslagen.
    """

    __tablename__ = "case_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Assignment
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Access level
    access_level: Mapped[CaseAccessLevel] = mapped_column(
        SQLEnum(CaseAccessLevel), default=CaseAccessLevel.READ
    )

    # Audit trail
    granted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)

    # Validity
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revoked_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))

    # Relationships
    case: Mapped["Case"] = relationship("Case", back_populates="assignments")
    user: Mapped["User"] = relationship("User", back_populates="case_assignments")

    __table_args__ = (
        Index("idx_case_assignments_case", "case_id"),
        Index("idx_case_assignments_user", "user_id"),
        Index("idx_case_assignments_active", "case_id", "user_id", "revoked_at"),
    )

    @property
    def is_active(self) -> bool:
        """Check if assignment is currently active."""
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and datetime.utcnow() > self.expires_at:
            return False
        return True

    def can_read(self) -> bool:
        """Check if assignment grants read access."""
        return self.is_active and self.access_level in [
            CaseAccessLevel.READ,
            CaseAccessLevel.WRITE,
            CaseAccessLevel.OWNER,
        ]

    def can_write(self) -> bool:
        """Check if assignment grants write access."""
        return self.is_active and self.access_level in [
            CaseAccessLevel.WRITE,
            CaseAccessLevel.OWNER,
        ]

    def is_owner(self) -> bool:
        """Check if assignment grants owner access."""
        return self.is_active and self.access_level == CaseAccessLevel.OWNER


class Case(Base):
    """
    Investigation case management.

    Security: Access is controlled via CaseAssignment, not just roles.
    Users must be explicitly assigned to access a case.
    """

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Case details
    case_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    case_type: Mapped[str] = mapped_column(String(50), default="other")

    # Legacy assignment (deprecated - use CaseAssignment)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(100))

    # Related entities
    entity_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    alert_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)

    # Notes and findings
    notes: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    assignments: Mapped[list["CaseAssignment"]] = relationship(
        "CaseAssignment", back_populates="case"
    )
