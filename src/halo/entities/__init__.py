"""
Entity resolution module for Halo platform.

Provides:
- Swedish personnummer validation
- Swedish organisationsnummer validation
- Entity matching and resolution
- Relationship graph operations
- Relationship extraction from structured data and text
"""

from halo.swedish.organisationsnummer import (
    OrganisationsnummerInfo,
    format_organisationsnummer,
    validate_organisationsnummer,
)
from halo.swedish.personnummer import (
    PersonnummerInfo,
    format_personnummer,
    validate_personnummer,
)
from halo.entities.graph import (
    EntityGraph,
    GraphNode,
    GraphEdge,
    GraphPath,
    Subgraph,
)
from halo.entities.relationships import (
    RelationshipExtractor,
    ExtractedRelationship,
    StructuredRelationshipExtractor,
    NLPRelationshipExtractor,
    TransactionRelationshipExtractor,
    RelationshipSource,
)

__all__ = [
    # Personnummer
    "PersonnummerInfo",
    "validate_personnummer",
    "format_personnummer",
    # Organisationsnummer
    "OrganisationsnummerInfo",
    "validate_organisationsnummer",
    "format_organisationsnummer",
    # Graph
    "EntityGraph",
    "GraphNode",
    "GraphEdge",
    "GraphPath",
    "Subgraph",
    # Relationships
    "RelationshipExtractor",
    "ExtractedRelationship",
    "StructuredRelationshipExtractor",
    "NLPRelationshipExtractor",
    "TransactionRelationshipExtractor",
    "RelationshipSource",
]
