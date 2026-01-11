"""
Pydantic schemas aligned with the Archeron Ontology.

These schemas represent the core data model:
- Entity: Persons, companies, addresses
- EntityIdentifier: Personnummer, orgnummer, etc.
- Fact: Attributes and relationships with temporality
- Mention: Raw observations before resolution
- Provenance: Full data lineage tracking
"""

from halo.schemas.entity import (
    EntityType,
    EntityStatus,
    Entity,
    EntityCreate,
    EntityUpdate,
    EntityIdentifier,
    EntityIdentifierCreate,
    PersonAttributes,
    CompanyAttributes,
    AddressAttributes,
    EventAttributes,
)
from halo.schemas.fact import (
    FactType,
    Predicate,
    Fact,
    FactCreate,
    FactUpdate,
)
from halo.schemas.mention import (
    ResolutionStatus,
    Mention,
    MentionCreate,
    ResolutionDecision,
)
from halo.schemas.provenance import (
    SourceType,
    Provenance,
    ProvenanceCreate,
)

__all__ = [
    # Entity
    "EntityType",
    "EntityStatus",
    "Entity",
    "EntityCreate",
    "EntityUpdate",
    "EntityIdentifier",
    "EntityIdentifierCreate",
    "PersonAttributes",
    "CompanyAttributes",
    "AddressAttributes",
    "EventAttributes",
    # Fact
    "FactType",
    "Predicate",
    "Fact",
    "FactCreate",
    "FactUpdate",
    # Mention
    "ResolutionStatus",
    "Mention",
    "MentionCreate",
    "ResolutionDecision",
    # Provenance
    "SourceType",
    "Provenance",
    "ProvenanceCreate",
]
