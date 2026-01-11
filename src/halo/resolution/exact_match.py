"""
Exact-match entity resolution for Swedish identifiers.

Handles "gold standard" exact matches on:
- Personnummer (Swedish personal ID)
- Samordningsnummer (coordination numbers)
- Organisationsnummer (company registration numbers)

Per the Archeron Ontology spec, exact identifier matches have 1.0 confidence
and are used as ground truth for accuracy measurement.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from halo.swedish.personnummer import validate_personnummer
from halo.swedish.organisationsnummer import validate_organisationsnummer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class ExactMatchResult:
    """Result of exact-match resolution."""

    mention_id: UUID
    matched: bool
    entity_id: Optional[UUID] = None
    identifier_type: Optional[str] = None
    identifier_value: Optional[str] = None
    is_new_entity: bool = False
    confidence: float = 1.0
    resolved_at: datetime = field(default_factory=datetime.utcnow)
    reason: str = ""


# SQL query to find entity by identifier
FIND_ENTITY_BY_IDENTIFIER_QUERY = """
SELECT
    ei.entity_id,
    ei.identifier_type,
    ei.identifier_value,
    e.canonical_name,
    e.entity_type,
    e.status
FROM onto_entity_identifiers ei
JOIN onto_entities e ON e.id = ei.entity_id
WHERE ei.identifier_type = :identifier_type
AND ei.identifier_value = :identifier_value
AND e.status = 'ACTIVE'
LIMIT 1;
"""

# SQL query to create entity from mention
CREATE_ENTITY_QUERY = """
INSERT INTO onto_entities (id, entity_type, canonical_name, resolution_confidence, status, created_at, updated_at)
VALUES (:id, :entity_type, :canonical_name, :confidence, 'ACTIVE', NOW(), NOW())
RETURNING id;
"""

# SQL query to create entity identifier
CREATE_IDENTIFIER_QUERY = """
INSERT INTO onto_entity_identifiers (id, entity_id, identifier_type, identifier_value, confidence, provenance_id, created_at)
VALUES (:id, :entity_id, :identifier_type, :identifier_value, :confidence, :provenance_id, NOW())
ON CONFLICT (entity_id, identifier_type, identifier_value) DO NOTHING;
"""

# SQL query to update mention resolution status
UPDATE_MENTION_QUERY = """
UPDATE onto_mentions
SET resolution_status = :status,
    resolved_to = :entity_id,
    resolution_confidence = :confidence,
    resolution_method = :method,
    resolved_at = NOW(),
    resolved_by = 'system'
WHERE id = :mention_id;
"""


class ExactMatchResolver:
    """
    Resolver for exact identifier matches.

    Handles personnummer, samordningsnummer, and organisationsnummer
    with 1.0 confidence matches (gold standard per ontology spec).
    """

    def __init__(self, session: Optional["AsyncSession"] = None):
        """
        Initialize the exact match resolver.

        Args:
            session: Optional SQLAlchemy async session for database operations.
                     If None, operates in validation-only mode.
        """
        self.session = session

    async def resolve_personnummer(
        self,
        mention_id: UUID,
        personnummer: str,
        name: Optional[str] = None,
        provenance_id: Optional[UUID] = None,
        create_if_not_found: bool = True,
    ) -> ExactMatchResult:
        """
        Resolve a mention by exact personnummer match.

        Args:
            mention_id: The mention being resolved
            personnummer: The personnummer to match
            name: Optional name for new entity creation
            provenance_id: Optional provenance for new identifier
            create_if_not_found: Whether to create new entity if not found

        Returns:
            ExactMatchResult with match details
        """
        # Validate personnummer format
        validation = validate_personnummer(personnummer)
        if not validation.valid:
            return ExactMatchResult(
                mention_id=mention_id,
                matched=False,
                reason=f"Invalid personnummer format: {personnummer}",
            )

        # Normalize to 12-digit format
        normalized = validation.normalized_12

        # Determine identifier type
        identifier_type = (
            "SAMORDNINGSNUMMER" if validation.is_samordningsnummer else "PERSONNUMMER"
        )

        return await self._resolve_by_identifier(
            mention_id=mention_id,
            identifier_type=identifier_type,
            identifier_value=normalized,
            entity_type="PERSON",
            canonical_name=name or f"Person ({normalized[:8]}...)",
            provenance_id=provenance_id,
            create_if_not_found=create_if_not_found,
        )

    async def resolve_organisationsnummer(
        self,
        mention_id: UUID,
        orgnummer: str,
        name: Optional[str] = None,
        provenance_id: Optional[UUID] = None,
        create_if_not_found: bool = True,
    ) -> ExactMatchResult:
        """
        Resolve a mention by exact organisationsnummer match.

        Args:
            mention_id: The mention being resolved
            orgnummer: The organisationsnummer to match
            name: Optional name for new entity creation
            provenance_id: Optional provenance for new identifier
            create_if_not_found: Whether to create new entity if not found

        Returns:
            ExactMatchResult with match details
        """
        # Validate organisationsnummer format
        validation = validate_organisationsnummer(orgnummer)
        if not validation.valid:
            return ExactMatchResult(
                mention_id=mention_id,
                matched=False,
                reason=f"Invalid organisationsnummer format: {orgnummer}",
            )

        # Normalize to 10-digit format
        normalized = validation.normalized

        return await self._resolve_by_identifier(
            mention_id=mention_id,
            identifier_type="ORGANISATIONSNUMMER",
            identifier_value=normalized,
            entity_type="COMPANY",
            canonical_name=name or f"Company ({normalized})",
            provenance_id=provenance_id,
            create_if_not_found=create_if_not_found,
        )

    async def _resolve_by_identifier(
        self,
        mention_id: UUID,
        identifier_type: str,
        identifier_value: str,
        entity_type: str,
        canonical_name: str,
        provenance_id: Optional[UUID],
        create_if_not_found: bool,
    ) -> ExactMatchResult:
        """
        Internal method to resolve by any identifier type.
        """
        if not self.session:
            # Validation-only mode
            return ExactMatchResult(
                mention_id=mention_id,
                matched=False,
                identifier_type=identifier_type,
                identifier_value=identifier_value,
                reason="No database session - validation only",
            )

        from sqlalchemy import text

        # Look up existing entity
        result = await self.session.execute(
            text(FIND_ENTITY_BY_IDENTIFIER_QUERY),
            {
                "identifier_type": identifier_type,
                "identifier_value": identifier_value,
            },
        )
        row = result.fetchone()

        if row:
            # Found existing entity - exact match!
            entity_id = row.entity_id
            logger.info(
                f"Exact {identifier_type} match: mention {mention_id} -> entity {entity_id}"
            )

            # Update mention resolution status
            await self.session.execute(
                text(UPDATE_MENTION_QUERY),
                {
                    "mention_id": mention_id,
                    "status": "AUTO_MATCHED",
                    "entity_id": entity_id,
                    "confidence": 1.0,
                    "method": f"exact_{identifier_type.lower()}_match",
                },
            )
            await self.session.commit()

            return ExactMatchResult(
                mention_id=mention_id,
                matched=True,
                entity_id=entity_id,
                identifier_type=identifier_type,
                identifier_value=identifier_value,
                is_new_entity=False,
                confidence=1.0,
                reason=f"Exact {identifier_type} match to existing entity",
            )

        elif create_if_not_found:
            # Create new entity
            new_entity_id = uuid4()
            new_identifier_id = uuid4()

            # Create entity
            await self.session.execute(
                text(CREATE_ENTITY_QUERY),
                {
                    "id": new_entity_id,
                    "entity_type": entity_type,
                    "canonical_name": canonical_name,
                    "confidence": 1.0,
                },
            )

            # Create identifier
            await self.session.execute(
                text(CREATE_IDENTIFIER_QUERY),
                {
                    "id": new_identifier_id,
                    "entity_id": new_entity_id,
                    "identifier_type": identifier_type,
                    "identifier_value": identifier_value,
                    "confidence": 1.0,
                    "provenance_id": provenance_id or uuid4(),
                },
            )

            # Update mention
            await self.session.execute(
                text(UPDATE_MENTION_QUERY),
                {
                    "mention_id": mention_id,
                    "status": "AUTO_MATCHED",
                    "entity_id": new_entity_id,
                    "confidence": 1.0,
                    "method": f"new_entity_from_{identifier_type.lower()}",
                },
            )

            await self.session.commit()

            logger.info(
                f"Created new entity {new_entity_id} for {identifier_type}={identifier_value}"
            )

            return ExactMatchResult(
                mention_id=mention_id,
                matched=True,
                entity_id=new_entity_id,
                identifier_type=identifier_type,
                identifier_value=identifier_value,
                is_new_entity=True,
                confidence=1.0,
                reason=f"Created new entity from {identifier_type}",
            )

        else:
            # No match found and not creating new
            return ExactMatchResult(
                mention_id=mention_id,
                matched=False,
                identifier_type=identifier_type,
                identifier_value=identifier_value,
                reason=f"No existing entity with {identifier_type}={identifier_value}",
            )


async def resolve_mention_exact(
    session: "AsyncSession",
    mention_id: UUID,
    personnummer: Optional[str] = None,
    orgnummer: Optional[str] = None,
    name: Optional[str] = None,
    provenance_id: Optional[UUID] = None,
) -> Optional[ExactMatchResult]:
    """
    Convenience function for exact-match resolution.

    Tries personnummer first, then organisationsnummer.
    Returns None if neither identifier is provided.

    Args:
        session: SQLAlchemy async session
        mention_id: The mention being resolved
        personnummer: Optional personnummer to match
        orgnummer: Optional organisationsnummer to match
        name: Optional name for new entity
        provenance_id: Optional provenance ID

    Returns:
        ExactMatchResult or None if no identifier provided
    """
    resolver = ExactMatchResolver(session)

    if personnummer:
        return await resolver.resolve_personnummer(
            mention_id=mention_id,
            personnummer=personnummer,
            name=name,
            provenance_id=provenance_id,
        )

    if orgnummer:
        return await resolver.resolve_organisationsnummer(
            mention_id=mention_id,
            orgnummer=orgnummer,
            name=name,
            provenance_id=provenance_id,
        )

    return None


def validate_identifier(identifier: str) -> tuple[bool, str, str]:
    """
    Validate and identify a Swedish identifier.

    Returns:
        Tuple of (is_valid, identifier_type, normalized_value)
    """
    # Try personnummer first
    pnr_result = validate_personnummer(identifier)
    if pnr_result.valid:
        id_type = "SAMORDNINGSNUMMER" if pnr_result.is_samordningsnummer else "PERSONNUMMER"
        return (True, id_type, pnr_result.normalized_12)

    # Try organisationsnummer
    org_result = validate_organisationsnummer(identifier)
    if org_result.valid:
        return (True, "ORGANISATIONSNUMMER", org_result.normalized)

    return (False, "", identifier)
