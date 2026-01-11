"""
Pydantic models for entity representation.

These models are used for API requests/responses and internal processing,
separate from the SQLAlchemy database models.
"""

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PersonAttributes(BaseModel):
    """Attributes specific to person entities."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "SE"
    is_coordination_number: bool = False


class CompanyAttributes(BaseModel):
    """Attributes specific to company entities."""

    legal_name: str
    trade_name: Optional[str] = None
    legal_form: Optional[str] = None  # AB, HB, KB, etc.
    status: Optional[str] = None  # Aktivt, Avregistrerat, etc.
    registration_date: Optional[date] = None
    deregistration_date: Optional[date] = None
    share_capital: Optional[float] = None
    currency: str = "SEK"
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    municipality: Optional[str] = None
    sni_codes: list[str] = Field(default_factory=list)
    employee_count: Optional[int] = None


class PropertyAttributes(BaseModel):
    """Attributes specific to property entities."""

    designation: str  # Fastighetsbeteckning
    municipality: Optional[str] = None
    property_type: Optional[str] = None  # Småhus, Flerbostadshus, etc.
    area_sqm: Optional[float] = None
    assessed_value: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class VehicleAttributes(BaseModel):
    """Attributes specific to vehicle entities."""

    registration_number: str
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    vehicle_type: Optional[str] = None
    status: Optional[str] = None  # I trafik, Avställd


class EntityBase(BaseModel):
    """Base model for all entity types."""

    entity_type: str
    display_name: Optional[str] = None
    name: Optional[str] = None  # Alias for display_name for backward compatibility
    personnummer: Optional[str] = None
    organisationsnummer: Optional[str] = None
    identifier: Optional[str] = None  # Generic identifier (personnummer or organisationsnummer)
    status: Optional[str] = None  # Entity status (active, inactive, etc.)
    risk_score: Optional[float] = None  # Risk score 0-1
    risk_level: Optional[str] = None  # Risk level (low, medium, high, critical)
    attributes: dict[str, Any] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)

    @property
    def effective_name(self) -> str:
        """Get the display name, falling back to name if display_name not set."""
        return self.display_name or self.name or ""


class EntityCreate(EntityBase):
    """Model for creating a new entity."""

    pass


class EntityUpdate(BaseModel):
    """Model for updating an entity."""

    display_name: Optional[str] = None
    attributes: Optional[dict[str, Any]] = None
    sources: Optional[list[str]] = None


class Entity(EntityBase):
    """Full entity model with ID and timestamps."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RelationshipBase(BaseModel):
    """Base model for entity relationships."""

    from_entity_id: UUID
    to_entity_id: UUID
    relationship_type: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    source: str


class RelationshipCreate(RelationshipBase):
    """Model for creating a new relationship."""

    pass


class Relationship(RelationshipBase):
    """Full relationship model with ID."""

    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class EntityWithRelationships(Entity):
    """Entity with its relationships."""

    relationships_from: list[Relationship] = Field(default_factory=list)
    relationships_to: list[Relationship] = Field(default_factory=list)


class EntitySearchResult(BaseModel):
    """Search result for entity queries."""

    entity: Entity
    score: float = 1.0
    highlights: dict[str, list[str]] = Field(default_factory=dict)


class EntityResolutionMatch(BaseModel):
    """Result of entity resolution matching."""

    entity_id: UUID
    match_score: float
    match_type: str  # 'exact', 'fuzzy', 'partial'
    matched_fields: list[str]


class EntityResolutionResult(BaseModel):
    """Full entity resolution result."""

    input_record: dict[str, Any]
    matches: list[EntityResolutionMatch]
    is_new: bool
    resolved_entity_id: Optional[UUID] = None
    confidence: float
