"""
SQLAlchemy ORM models aligned with Archeron Ontology.

These models map directly to the PostgreSQL schema defined in the ontology.
"""

from halo.models.base import OntologyBase

from halo.models.entity import (
    Entity,
    EntityIdentifier,
    PersonAttributes,
    CompanyAttributes,
    AddressAttributes,
    EventAttributes,
    EntityType,
    EntityStatus,
    IdentifierType,
)
from halo.models.fact import (
    Fact,
    FactType,
    Predicate,
)
from halo.models.mention import (
    Mention,
    ResolutionDecision,
    ResolutionStatus,
)
from halo.models.provenance import (
    Provenance,
    SourceAuthority,
    SourceType,
)
from halo.models.audit import (
    AuditLog,
    ActorType,
)
from halo.models.derivation import (
    DerivationRule,
    DerivationRun,
    DerivationRuleType,
    DerivationRunStatus,
)
from halo.models.validation import (
    ResolutionConfig,
    ValidationGroundTruth,
    GroundTruthType,
)
from halo.models.alert import (
    Alert,
    AlertStatus,
    ALERT_TYPES,
)

__all__ = [
    # Base
    "OntologyBase",
    # Entity
    "Entity",
    "EntityIdentifier",
    "PersonAttributes",
    "CompanyAttributes",
    "AddressAttributes",
    "EventAttributes",
    "EntityType",
    "EntityStatus",
    "IdentifierType",
    # Fact
    "Fact",
    "FactType",
    "Predicate",
    # Mention
    "Mention",
    "ResolutionDecision",
    "ResolutionStatus",
    # Provenance
    "Provenance",
    "SourceAuthority",
    "SourceType",
    # Audit
    "AuditLog",
    "ActorType",
    # Derivation
    "DerivationRule",
    "DerivationRun",
    "DerivationRuleType",
    "DerivationRunStatus",
    # Validation
    "ResolutionConfig",
    "ValidationGroundTruth",
    "GroundTruthType",
    # Alerts
    "Alert",
    "AlertStatus",
    "ALERT_TYPES",
]
