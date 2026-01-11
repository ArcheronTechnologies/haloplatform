"""
Entity split operations.

Splitting separates incorrectly merged entities by:
1. Creating a new entity from selected facts
2. Moving specified facts to the new entity
3. Preserving audit trail with SPLIT status
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4


@dataclass
class SplitResult:
    """Result of an entity split operation."""

    success: bool
    original_entity_id: UUID
    new_entity_id: Optional[UUID] = None
    error: Optional[str] = None
    facts_moved: int = 0
    facts_retained: int = 0
    identifiers_moved: int = 0


@dataclass
class SplitRequest:
    """Request to split an entity."""

    source_entity_id: UUID  # Entity to split
    fact_ids_to_move: list[UUID]  # Facts that go to new entity
    identifier_ids_to_move: list[UUID]  # Identifiers that go to new entity
    new_entity_name: str  # Name for the new entity
    split_reason: str
    provenance_id: UUID
    split_by: str  # 'system' or user ID


class EntitySplitter:
    """
    Handles entity split operations.

    Split strategy (per ontology):
    - Original entity remains (potentially modified)
    - New entity created with SPLIT status
    - New entity's split_from points to original
    - Selected facts moved to new entity
    - Selected identifiers moved to new entity
    - Audit trail preserved
    """

    def __init__(self, db_session):
        """
        Initialize splitter with database session.

        Args:
            db_session: SQLAlchemy async session
        """
        self.db = db_session

    async def split(self, request: SplitRequest) -> SplitResult:
        """
        Split an entity into two.

        Creates a new entity and moves specified facts/identifiers to it.

        Args:
            request: SplitRequest with entity ID and facts to move

        Returns:
            SplitResult with success status and new entity ID
        """
        # Validation
        if not request.fact_ids_to_move and not request.identifier_ids_to_move:
            return SplitResult(
                success=False,
                original_entity_id=request.source_entity_id,
                error="Must specify at least one fact or identifier to move",
            )

        if not request.new_entity_name.strip():
            return SplitResult(
                success=False,
                original_entity_id=request.source_entity_id,
                error="New entity name cannot be empty",
            )

        # In a real implementation, this would:
        # 1. Load source entity
        # 2. Verify entity is ACTIVE
        # 3. Verify all fact/identifier IDs belong to source entity
        # 4. Create new entity with same type
        # 5. Move facts (update subject_id)
        # 6. Move identifiers (update entity_id)
        # 7. Create provenance for the split operation

        new_entity_id = uuid4()

        return SplitResult(
            success=True,
            original_entity_id=request.source_entity_id,
            new_entity_id=new_entity_id,
            facts_moved=len(request.fact_ids_to_move),
            facts_retained=0,  # Would be calculated
            identifiers_moved=len(request.identifier_ids_to_move),
        )

    async def can_split(
        self, entity_id: UUID, fact_ids: list[UUID]
    ) -> tuple[bool, Optional[str]]:
        """
        Check if an entity can be split with the given facts.

        Args:
            entity_id: Entity to split
            fact_ids: Facts to move to new entity

        Returns:
            Tuple of (can_split, reason_if_not)
        """
        if not fact_ids:
            return False, "No facts specified to move"

        # Would check:
        # - Entity exists and is ACTIVE
        # - All fact_ids belong to entity
        # - Split would leave original entity with at least one fact
        # - No derived facts depend on moved facts

        return True, None

    async def preview_split(
        self, entity_id: UUID, fact_ids: list[UUID]
    ) -> dict:
        """
        Preview what a split would look like.

        Args:
            entity_id: Entity to split
            fact_ids: Facts that would be moved

        Returns:
            Dict with preview of both resulting entities
        """
        # Would return:
        # - Original entity after split (remaining facts)
        # - New entity (moved facts)
        # - Any warnings (e.g., breaking relationships)
        return {
            "original_entity": {
                "id": entity_id,
                "facts_after_split": [],
                "identifiers_after_split": [],
            },
            "new_entity": {
                "facts": [],
                "identifiers": [],
            },
            "warnings": [],
        }

    async def get_split_suggestions(
        self, entity_id: UUID
    ) -> list[dict]:
        """
        Get suggestions for how to split an entity.

        Analyzes facts to find natural split points (e.g., facts
        from different sources, different time periods, etc.).

        Args:
            entity_id: Entity to analyze

        Returns:
            List of suggested splits with rationale
        """
        # Would analyze:
        # - Facts by provenance (different sources might be different people)
        # - Facts by time period
        # - Contradictory facts (e.g., two different birth dates)

        return []


def create_split_provenance(
    source_entity_id: UUID,
    new_entity_id: UUID,
    split_reason: str,
    split_by: str,
    fact_ids_moved: list[UUID],
) -> dict:
    """
    Create provenance record for a split operation.

    Args:
        source_entity_id: Original entity ID
        new_entity_id: New entity ID
        split_reason: Human-readable reason
        split_by: User or system identifier
        fact_ids_moved: Facts that were moved

    Returns:
        Dict representing the provenance record
    """
    return {
        "id": uuid4(),
        "source_type": "DERIVED_COMPUTATION",
        "source_id": f"split:{source_entity_id}:{new_entity_id}",
        "extraction_method": "entity_split",
        "extraction_timestamp": datetime.utcnow(),
        "extraction_system_version": "halo-1.0",
        "derived_from": fact_ids_moved,
        "derivation_rule": f"Split by {split_by}: {split_reason}",
    }
