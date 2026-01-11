"""
Entity schemas aligned with Archeron Ontology.

Entities are resolved real-world objects: persons, companies, addresses.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class EntityType(str, Enum):
    """Types of entities in the system."""

    PERSON = "PERSON"
    COMPANY = "COMPANY"
    ADDRESS = "ADDRESS"
    EVENT = "EVENT"  # Investigation events, transactions, etc.


class EntityStatus(str, Enum):
    """Status of an entity."""

    ACTIVE = "ACTIVE"
    MERGED = "MERGED"  # Merged into another entity
    SPLIT = "SPLIT"  # Split from another entity
    ANONYMIZED = "ANONYMIZED"  # GDPR erasure applied


class IdentifierType(str, Enum):
    """Types of entity identifiers."""

    PERSONNUMMER = "PERSONNUMMER"
    SAMORDNINGSNUMMER = "SAMORDNINGSNUMMER"
    ORGANISATIONSNUMMER = "ORGANISATIONSNUMMER"
    POSTAL_CODE = "POSTAL_CODE"
    PROPERTY_ID = "PROPERTY_ID"


class EntityIdentifierCreate(BaseModel):
    """Schema for creating an entity identifier."""

    identifier_type: IdentifierType
    identifier_value: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_id: UUID
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class EntityIdentifier(EntityIdentifierCreate):
    """Full entity identifier with ID and timestamps."""

    id: UUID
    entity_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class PersonAttributes(BaseModel):
    """Attributes specific to person entities."""

    birth_year: Optional[int] = None
    birth_date: Optional[date] = None
    gender: Optional[str] = Field(None, pattern="^(M|F)$")

    # Cached computations (updated nightly)
    company_count: int = 0
    active_directorship_count: int = 0
    network_cluster_id: Optional[UUID] = None
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_factors: list[str] = Field(default_factory=list)

    # Activity tracking
    first_seen: Optional[date] = None
    last_activity: Optional[date] = None

    class Config:
        from_attributes = True


class CompanyAttributes(BaseModel):
    """Attributes specific to company entities."""

    # Core info
    legal_form: Optional[str] = None  # AB, HB, KB, EF, etc.
    status: str = "UNKNOWN"  # ACTIVE, LIQUIDATION, DISSOLVED, BANKRUPTCY
    registration_date: Optional[date] = None
    dissolution_date: Optional[date] = None

    # Industry
    sni_codes: list[str] = Field(default_factory=list)
    sni_primary: Optional[str] = None

    # Financials (from annual reports)
    latest_revenue: Optional[int] = None
    latest_employees: Optional[int] = None
    latest_assets: Optional[int] = None
    financial_year_end: Optional[date] = None

    # Cached computations (updated nightly)
    director_count: int = 0
    director_change_velocity: float = 0.0  # Changes per year
    network_cluster_id: Optional[UUID] = None
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_factors: list[str] = Field(default_factory=list)
    shell_indicators: list[str] = Field(default_factory=list)
    ownership_opacity_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Activity tracking
    last_filing_date: Optional[date] = None

    class Config:
        from_attributes = True


class AddressAttributes(BaseModel):
    """Attributes specific to address entities."""

    # Normalized components
    street: str
    street_number: Optional[str] = None
    postal_code: str
    city: str
    municipality: Optional[str] = None

    # Geocoded location (stored as lat/lon for simplicity)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geocode_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    # Zone classification
    vulnerable_area: bool = False
    vulnerability_level: Optional[str] = None  # PARTICULARLY, RISK, CONCERN

    # Cached computations (updated nightly)
    company_count: int = 0
    person_count: int = 0
    is_registration_hub: bool = False  # Many companies, few people

    class Config:
        from_attributes = True


class EventAttributes(BaseModel):
    """Attributes specific to event entities."""

    # Event classification
    event_type: str  # REGISTRATION, DIRECTOR_CHANGE, TRANSACTION, etc.
    event_subtype: Optional[str] = None

    # Temporal
    event_date: date
    event_timestamp: Optional[datetime] = None

    # Source document
    source_document_id: Optional[UUID] = None
    source_reference: Optional[str] = None

    # Related entities (by ID)
    involved_entity_ids: list[UUID] = Field(default_factory=list)

    # Event-specific data
    event_data: dict[str, Any] = Field(default_factory=dict)

    # Risk indicators
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_indicators: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class EntityCreate(BaseModel):
    """Schema for creating a new entity."""

    entity_type: EntityType
    canonical_name: str
    resolution_confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    # Identifiers to create with the entity
    identifiers: list[EntityIdentifierCreate] = Field(default_factory=list)

    # Type-specific attributes
    person_attributes: Optional[PersonAttributes] = None
    company_attributes: Optional[CompanyAttributes] = None
    address_attributes: Optional[AddressAttributes] = None
    event_attributes: Optional[EventAttributes] = None

    @field_validator("person_attributes", "company_attributes", "address_attributes", "event_attributes")
    @classmethod
    def validate_attributes_match_type(cls, v, info):
        """Validate that attributes match entity type."""
        # This validation happens at the application level
        return v


class EntityUpdate(BaseModel):
    """Schema for updating an entity."""

    canonical_name: Optional[str] = None
    resolution_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: Optional[EntityStatus] = None
    merged_into: Optional[UUID] = None
    split_from: Optional[UUID] = None

    # Type-specific attributes
    person_attributes: Optional[PersonAttributes] = None
    company_attributes: Optional[CompanyAttributes] = None
    address_attributes: Optional[AddressAttributes] = None
    event_attributes: Optional[EventAttributes] = None


class Entity(BaseModel):
    """Full entity model with ID and timestamps."""

    id: UUID
    entity_type: EntityType
    canonical_name: str
    resolution_confidence: float = Field(ge=0.0, le=1.0)

    # Status
    status: EntityStatus = EntityStatus.ACTIVE
    merged_into: Optional[UUID] = None  # For MERGED status
    split_from: Optional[UUID] = None  # For SPLIT status

    # Timestamps
    created_at: datetime
    updated_at: datetime
    anonymized_at: Optional[datetime] = None  # For GDPR erasure

    # Related data (optional, for API responses)
    identifiers: list[EntityIdentifier] = Field(default_factory=list)
    same_as: list[UUID] = Field(default_factory=list)  # Merged entities

    # Type-specific attributes
    person_attributes: Optional[PersonAttributes] = None
    company_attributes: Optional[CompanyAttributes] = None
    address_attributes: Optional[AddressAttributes] = None
    event_attributes: Optional[EventAttributes] = None

    class Config:
        from_attributes = True

    @property
    def primary_identifier(self) -> Optional[str]:
        """Get the primary identifier (personnummer or orgnummer)."""
        for ident in self.identifiers:
            if ident.identifier_type in [
                IdentifierType.PERSONNUMMER,
                IdentifierType.ORGANISATIONSNUMMER,
            ]:
                return ident.identifier_value
        return None

    @property
    def risk_score(self) -> float:
        """Get risk score from attributes."""
        if self.person_attributes:
            return self.person_attributes.risk_score
        if self.company_attributes:
            return self.company_attributes.risk_score
        if self.event_attributes:
            return self.event_attributes.risk_score
        return 0.0


class EntityResponse(BaseModel):
    """API response for entity lookup."""

    id: UUID
    entity_type: str
    canonical_name: str
    status: str
    resolution_confidence: float
    identifiers: list[EntityIdentifier]
    attributes: dict[str, Any]
    same_as: list[UUID]
    created_at: datetime
    updated_at: datetime


class GraphNode(BaseModel):
    """A node in a graph response."""

    id: UUID
    entity_type: str
    canonical_name: str
    risk_score: Optional[float] = None


class GraphEdge(BaseModel):
    """An edge in a graph response."""

    source: UUID
    target: UUID
    predicate: str
    valid_from: date
    valid_to: Optional[date] = None


class GraphResponse(BaseModel):
    """API response for graph traversal."""

    root: UUID
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool
    total_nodes: int
