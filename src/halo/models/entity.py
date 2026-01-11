"""
Entity ORM models aligned with Archeron Ontology.

Entities are resolved real-world objects: persons, companies, addresses.
"""

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from halo.models.base import OntologyBase as Base

if TYPE_CHECKING:
    from halo.models.fact import Fact
    from halo.models.mention import Mention
    from halo.models.provenance import Provenance


class EntityType(str, enum.Enum):
    """Types of entities in the system."""

    PERSON = "PERSON"
    COMPANY = "COMPANY"
    ADDRESS = "ADDRESS"
    EVENT = "EVENT"  # Investigation events, transactions, etc.


class EntityStatus(str, enum.Enum):
    """Status of an entity."""

    ACTIVE = "ACTIVE"
    MERGED = "MERGED"
    SPLIT = "SPLIT"
    ANONYMIZED = "ANONYMIZED"


class IdentifierType(str, enum.Enum):
    """Types of entity identifiers."""

    PERSONNUMMER = "PERSONNUMMER"
    SAMORDNINGSNUMMER = "SAMORDNINGSNUMMER"
    ORGANISATIONSNUMMER = "ORGANISATIONSNUMMER"
    POSTAL_CODE = "POSTAL_CODE"
    PROPERTY_ID = "PROPERTY_ID"


class Entity(Base):
    """
    Core entity table.

    Represents a resolved real-world object (person, company, or address).
    """

    __tablename__ = "onto_entities"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, name="entity_type_enum"), nullable=False
    )
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )

    # Status
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, name="entity_status_enum"),
        nullable=False,
        default=EntityStatus.ACTIVE,
    )
    merged_into: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), nullable=True
    )
    split_from: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    anonymized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    identifiers: Mapped[List["EntityIdentifier"]] = relationship(
        "EntityIdentifier", back_populates="entity", cascade="all, delete-orphan"
    )
    person_attributes: Mapped[Optional["PersonAttributes"]] = relationship(
        "PersonAttributes", back_populates="entity", uselist=False
    )
    company_attributes: Mapped[Optional["CompanyAttributes"]] = relationship(
        "CompanyAttributes", back_populates="entity", uselist=False
    )
    address_attributes: Mapped[Optional["AddressAttributes"]] = relationship(
        "AddressAttributes", back_populates="entity", uselist=False
    )
    event_attributes: Mapped[Optional["EventAttributes"]] = relationship(
        "EventAttributes", back_populates="entity", uselist=False
    )

    # Facts where this entity is subject
    subject_facts: Mapped[List["Fact"]] = relationship(
        "Fact",
        foreign_keys="Fact.subject_id",
        back_populates="subject",
    )
    # Facts where this entity is object (for relationships)
    object_facts: Mapped[List["Fact"]] = relationship(
        "Fact",
        foreign_keys="Fact.object_id",
        back_populates="object",
    )

    __table_args__ = (
        CheckConstraint(
            "resolution_confidence >= 0 AND resolution_confidence <= 1",
            name="check_resolution_confidence",
        ),
        Index("idx_entities_type", "entity_type", postgresql_where=status == "ACTIVE"),
        Index("idx_entities_merged", "merged_into", postgresql_where=merged_into.isnot(None)),
    )


class EntityIdentifier(Base):
    """
    Entity identifiers table.

    Stores personnummer, orgnummer, and other identifiers for entities.
    Multiple identifiers can be associated with a single entity.
    """

    __tablename__ = "onto_entity_identifiers"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    entity_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), nullable=False
    )
    identifier_type: Mapped[IdentifierType] = mapped_column(
        Enum(IdentifierType, name="identifier_type_enum"), nullable=False
    )
    identifier_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    provenance_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_provenances.id"), nullable=False
    )
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    entity: Mapped["Entity"] = relationship("Entity", back_populates="identifiers")
    provenance: Mapped["Provenance"] = relationship("Provenance")

    __table_args__ = (
        UniqueConstraint(
            "entity_id", "identifier_type", "identifier_value",
            name="uq_entity_identifier"
        ),
        Index("idx_identifiers_lookup", "identifier_type", "identifier_value"),
        Index("idx_identifiers_entity", "entity_id"),
    )


class PersonAttributes(Base):
    """
    Person-specific attributes.

    Stores attributes specific to PERSON entities.
    """

    __tablename__ = "onto_person_attributes"

    entity_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), primary_key=True
    )

    # Extracted/derived attributes
    birth_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Cached computations (updated nightly)
    company_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_directorship_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    network_cluster_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_factors: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True, default=list
    )

    # Activity tracking
    first_seen: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_activity: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    entity: Mapped["Entity"] = relationship(
        "Entity", back_populates="person_attributes"
    )

    __table_args__ = (
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 1", name="check_person_risk_score"
        ),
    )


class CompanyAttributes(Base):
    """
    Company-specific attributes.

    Stores attributes specific to COMPANY entities.
    """

    __tablename__ = "onto_company_attributes"

    entity_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), primary_key=True
    )

    # Core info
    legal_form: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN")
    registration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    dissolution_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Industry
    sni_codes: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True, default=list
    )
    sni_primary: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Financials (from annual reports)
    latest_revenue: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latest_employees: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latest_assets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    financial_year_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Cached computations (updated nightly)
    director_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    director_change_velocity: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    network_cluster_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_factors: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True, default=list
    )
    shell_indicators: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True, default=list
    )
    ownership_opacity_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )

    # Activity tracking
    last_filing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    entity: Mapped["Entity"] = relationship(
        "Entity", back_populates="company_attributes"
    )

    __table_args__ = (
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 1", name="check_company_risk_score"
        ),
        Index("idx_company_status", "status"),
        Index("idx_company_sni", "sni_primary"),
        Index("idx_company_risk", "risk_score", postgresql_where="risk_score > 0.5"),
    )


class AddressAttributes(Base):
    """
    Address-specific attributes.

    Stores attributes specific to ADDRESS entities.
    """

    __tablename__ = "onto_address_attributes"

    entity_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), primary_key=True
    )

    # Normalized components
    street: Mapped[str] = mapped_column(Text, nullable=False)
    street_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    city: Mapped[str] = mapped_column(Text, nullable=False)
    municipality: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Geocoded location (stored as lat/lon)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geocode_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Zone classification
    vulnerable_area: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vulnerability_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Cached computations (updated nightly)
    company_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    person_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_registration_hub: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    entity: Mapped["Entity"] = relationship(
        "Entity", back_populates="address_attributes"
    )

    __table_args__ = (
        Index("idx_address_postal", "postal_code"),
        Index(
            "idx_address_vulnerable",
            "vulnerable_area",
            postgresql_where="vulnerable_area = TRUE",
        ),
    )


class EventAttributes(Base):
    """
    Event-specific attributes.

    Stores attributes specific to EVENT entities.
    Events represent temporal occurrences like company registrations,
    director changes, or transactions.
    """

    __tablename__ = "onto_event_attributes"

    entity_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onto_entities.id"), primary_key=True
    )

    # Event classification
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_subtype: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Temporal
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Source document
    source_document_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    source_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Related entities
    involved_entity_ids: Mapped[Optional[list]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )

    # Event-specific data (flexible)
    event_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)

    # Risk indicators
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_indicators: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True, default=list
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    entity: Mapped["Entity"] = relationship(
        "Entity", back_populates="event_attributes"
    )

    __table_args__ = (
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 1", name="check_event_risk_score"
        ),
        Index("idx_event_type", "event_type"),
        Index("idx_event_date", "event_date"),
        Index("idx_event_risk", "risk_score", postgresql_where="risk_score > 0.5"),
    )
