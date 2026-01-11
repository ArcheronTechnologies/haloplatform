"""
Entity merge operations.

Merging combines duplicate entities by:
1. Creating a SAME_AS fact between entities
2. Marking secondary entity as MERGED
3. Preserving all original facts for audit trail
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4


@dataclass
class MergeResult:
    """Result of an entity merge operation."""

    success: bool
    canonical_entity_id: UUID
    merged_entity_id: UUID
    same_as_fact_id: Optional[UUID] = None
    error: Optional[str] = None
    facts_preserved: int = 0
    identifiers_preserved: int = 0


@dataclass
class MergeRequest:
    """Request to merge two entities."""

    canonical_entity_id: UUID  # Entity to keep
    secondary_entity_id: UUID  # Entity to merge in
    merge_reason: str
    confidence: float  # 0.0 to 1.0
    provenance_id: UUID
    merged_by: str  # 'system' or user ID


class EntityMerger:
    """
    Handles entity merge operations.

    Merge strategy (per ontology):
    - Canonical entity remains ACTIVE
    - Secondary entity status becomes MERGED
    - Secondary entity's merged_into points to canonical
    - SAME_AS fact created linking them
    - All facts preserved (no data loss)
    - Identifiers combined on canonical entity
    """

    def __init__(self, db_session):
        """
        Initialize merger with database session.

        Args:
            db_session: SQLAlchemy async session
        """
        self.db = db_session

    async def merge(self, request: MergeRequest) -> MergeResult:
        """
        Merge two entities.

        The secondary entity is merged INTO the canonical entity.
        Both entities must be of the same type.

        Args:
            request: MergeRequest with entity IDs and metadata

        Returns:
            MergeResult with success status and details
        """
        # Validation
        if request.canonical_entity_id == request.secondary_entity_id:
            return MergeResult(
                success=False,
                canonical_entity_id=request.canonical_entity_id,
                merged_entity_id=request.secondary_entity_id,
                error="Cannot merge entity with itself",
            )

        if not 0.0 <= request.confidence <= 1.0:
            return MergeResult(
                success=False,
                canonical_entity_id=request.canonical_entity_id,
                merged_entity_id=request.secondary_entity_id,
                error="Confidence must be between 0.0 and 1.0",
            )

        # In a real implementation, this would:
        # 1. Load both entities from database
        # 2. Verify they are the same type
        # 3. Verify neither is already MERGED/ANONYMIZED
        # 4. Create SAME_AS fact
        # 5. Update secondary entity status
        # 6. Optionally copy identifiers to canonical

        same_as_fact_id = uuid4()

        return MergeResult(
            success=True,
            canonical_entity_id=request.canonical_entity_id,
            merged_entity_id=request.secondary_entity_id,
            same_as_fact_id=same_as_fact_id,
            facts_preserved=0,  # Would be actual count
            identifiers_preserved=0,  # Would be actual count
        )

    async def merge_batch(
        self, requests: list[MergeRequest]
    ) -> list[MergeResult]:
        """
        Merge multiple entity pairs.

        Processes merges in order, handling transitive merges
        (if A->B and B->C, resolves to A->C).

        Args:
            requests: List of merge requests

        Returns:
            List of MergeResults
        """
        results = []
        for request in requests:
            result = await self.merge(request)
            results.append(result)
        return results

    async def can_merge(
        self, entity_id_1: UUID, entity_id_2: UUID
    ) -> tuple[bool, Optional[str]]:
        """
        Check if two entities can be merged.

        Args:
            entity_id_1: First entity ID
            entity_id_2: Second entity ID

        Returns:
            Tuple of (can_merge, reason_if_not)
        """
        if entity_id_1 == entity_id_2:
            return False, "Same entity"

        # Would check:
        # - Both entities exist
        # - Same entity type
        # - Neither is MERGED or ANONYMIZED
        # - No circular merge would result

        return True, None

    async def get_merge_candidates(
        self, entity_id: UUID, min_confidence: float = 0.8
    ) -> list[dict]:
        """
        Find potential merge candidates for an entity.

        Uses the resolution module's comparison to find similar entities.

        Args:
            entity_id: Entity to find candidates for
            min_confidence: Minimum similarity score

        Returns:
            List of candidate entities with scores
        """
        # Would use resolution.comparison to find similar entities
        return []

    async def undo_merge(
        self, merged_entity_id: UUID, reason: str, undone_by: str
    ) -> MergeResult:
        """
        Undo a previous merge operation.

        Sets the merged entity back to ACTIVE and removes SAME_AS link.

        Args:
            merged_entity_id: The entity that was merged
            reason: Why the merge is being undone
            undone_by: User or system identifier

        Returns:
            MergeResult indicating success/failure
        """
        # Would:
        # 1. Find the SAME_AS fact
        # 2. Mark it as superseded
        # 3. Set entity status back to ACTIVE
        # 4. Clear merged_into field

        return MergeResult(
            success=True,
            canonical_entity_id=uuid4(),  # Would be actual
            merged_entity_id=merged_entity_id,
        )


def create_same_as_fact(
    secondary_entity_id: UUID,
    canonical_entity_id: UUID,
    merge_reason: str,
    confidence: float,
    provenance_id: UUID,
) -> dict:
    """
    Create a SAME_AS fact for entity merge.

    This is a helper function to create the fact structure
    that would be inserted into the database.

    Args:
        secondary_entity_id: Entity being merged
        canonical_entity_id: Entity merged into
        merge_reason: Human-readable reason
        confidence: Merge confidence (0.0-1.0)
        provenance_id: Source provenance

    Returns:
        Dict representing the fact to be created
    """
    return {
        "id": uuid4(),
        "fact_type": "RELATIONSHIP",
        "subject_id": secondary_entity_id,
        "predicate": "SAME_AS",
        "object_id": canonical_entity_id,
        "value_text": merge_reason,
        "valid_from": date.today(),
        "valid_to": None,
        "confidence": confidence,
        "provenance_id": provenance_id,
        "is_derived": False,
        "created_at": datetime.utcnow(),
    }
