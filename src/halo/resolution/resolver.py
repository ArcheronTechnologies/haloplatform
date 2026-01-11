"""
Main entity resolution pipeline.

Orchestrates blocking, comparison, and clustering to resolve
mentions to entities.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from halo.resolution.blocking import BlockingIndex, CandidateEntity, Mention
from halo.resolution.comparison import FeatureComparator, FeatureScores
from halo.resolution.clustering import ClusteringEngine, MentionCluster

logger = logging.getLogger(__name__)


class ResolutionDecision(str, Enum):
    """Decision types for resolution."""

    AUTO_MATCH = "auto_match"  # High confidence automatic match
    AUTO_REJECT = "auto_reject"  # Low confidence automatic rejection
    HUMAN_MATCH = "human_match"  # Human confirmed match
    HUMAN_REJECT = "human_reject"  # Human rejected match
    PENDING_REVIEW = "pending_review"  # Needs human review
    NEW_ENTITY = "new_entity"  # No candidates, create new entity


@dataclass
class ResolutionThreshold:
    """Thresholds for resolution decisions."""

    auto_match: float = 0.95  # Auto-match if score >= this
    human_review_min: float = 0.60  # Queue for review if score >= this
    auto_reject: float = 0.60  # Auto-reject if score < this


@dataclass
class ResolutionConfig:
    """Configuration for entity resolution."""

    person_thresholds: ResolutionThreshold = field(
        default_factory=lambda: ResolutionThreshold(
            auto_match=0.95,
            human_review_min=0.60,
            auto_reject=0.60,
        )
    )
    company_thresholds: ResolutionThreshold = field(
        default_factory=lambda: ResolutionThreshold(
            auto_match=0.95,
            human_review_min=0.60,
            auto_reject=0.60,
        )
    )
    address_thresholds: ResolutionThreshold = field(
        default_factory=lambda: ResolutionThreshold(
            auto_match=0.90,
            human_review_min=0.50,
            auto_reject=0.50,
        )
    )

    def get_threshold(self, entity_type: str) -> ResolutionThreshold:
        """Get thresholds for entity type."""
        if entity_type == "PERSON":
            return self.person_thresholds
        elif entity_type == "COMPANY":
            return self.company_thresholds
        else:
            return self.address_thresholds


@dataclass
class CandidateScore:
    """A candidate entity with its score."""

    entity: CandidateEntity
    score: float
    features: FeatureScores


@dataclass
class ResolutionResult:
    """Result of resolving a single mention."""

    mention_id: UUID
    decision: ResolutionDecision
    entity_id: Optional[UUID] = None
    score: float = 0.0
    features: Optional[FeatureScores] = None
    all_candidates: list[CandidateScore] = field(default_factory=list)
    resolved_at: datetime = field(default_factory=datetime.utcnow)
    resolved_by: str = "system"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mention_id": str(self.mention_id),
            "decision": self.decision.value,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "score": self.score,
            "features": self.features.to_dict() if self.features else None,
            "resolved_at": self.resolved_at.isoformat(),
            "resolved_by": self.resolved_by,
            "reason": self.reason,
        }


@dataclass
class BatchResolutionResult:
    """Result of batch resolution."""

    results: list[ResolutionResult]
    clusters: list[MentionCluster]
    stats: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0


class EntityResolver:
    """
    Main resolution pipeline.

    Flow:
    1. Blocking: Group mentions by blocking keys
    2. Comparison: Score candidate pairs
    3. Decision: Auto-match, auto-reject, or queue for review
    4. Clustering: Group matched mentions
    """

    def __init__(
        self,
        config: Optional[ResolutionConfig] = None,
        blocking_index: Optional[BlockingIndex] = None,
        comparator: Optional[FeatureComparator] = None,
    ):
        self.config = config or ResolutionConfig()
        self.blocker = blocking_index or BlockingIndex()
        self.comparator = comparator or FeatureComparator()

    def resolve_mention(
        self,
        mention: Mention,
    ) -> ResolutionResult:
        """
        Resolve a single mention to an entity.

        Returns the resolution result with decision and matched entity.
        """
        # 1. Get candidates via blocking
        candidates = self.blocker.get_candidates(mention)

        if not candidates:
            # No candidates - create new entity
            logger.debug(f"No candidates for mention {mention.id}, creating new entity")
            return ResolutionResult(
                mention_id=mention.id,
                decision=ResolutionDecision.NEW_ENTITY,
                entity_id=uuid4(),  # New entity ID
                score=1.0,
                reason="No matching candidates found",
            )

        # 2. Score each candidate
        scored_candidates: list[CandidateScore] = []
        for candidate in candidates:
            features = self.comparator.compute_features(mention, candidate)
            score = self.comparator.score_features(features, mention.mention_type)
            scored_candidates.append(
                CandidateScore(entity=candidate, score=score, features=features)
            )

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x.score, reverse=True)

        # 3. Get best match
        best = scored_candidates[0]
        threshold = self.config.get_threshold(mention.mention_type)

        # 4. Make decision
        if best.score >= threshold.auto_match:
            logger.debug(
                f"Auto-match: mention {mention.id} -> entity {best.entity.id} "
                f"(score={best.score:.3f})"
            )
            return ResolutionResult(
                mention_id=mention.id,
                decision=ResolutionDecision.AUTO_MATCH,
                entity_id=best.entity.id,
                score=best.score,
                features=best.features,
                all_candidates=scored_candidates[:5],  # Top 5
                reason=f"Score {best.score:.3f} >= auto_match threshold {threshold.auto_match}",
            )
        elif best.score >= threshold.human_review_min:
            logger.debug(
                f"Pending review: mention {mention.id}, best score={best.score:.3f}"
            )
            return ResolutionResult(
                mention_id=mention.id,
                decision=ResolutionDecision.PENDING_REVIEW,
                entity_id=best.entity.id,
                score=best.score,
                features=best.features,
                all_candidates=scored_candidates[:5],
                reason=f"Score {best.score:.3f} in review range [{threshold.human_review_min}, {threshold.auto_match})",
            )
        else:
            # Score too low - treat as new entity
            logger.debug(
                f"Auto-reject: mention {mention.id}, best score={best.score:.3f} < {threshold.human_review_min}"
            )
            return ResolutionResult(
                mention_id=mention.id,
                decision=ResolutionDecision.NEW_ENTITY,
                entity_id=uuid4(),
                score=best.score,
                features=best.features,
                all_candidates=scored_candidates[:5],
                reason=f"Best score {best.score:.3f} < threshold {threshold.human_review_min}",
            )

    def resolve_batch(
        self,
        mentions: list[Mention],
        cluster: bool = True,
    ) -> BatchResolutionResult:
        """
        Resolve a batch of mentions.

        Args:
            mentions: List of mentions to resolve
            cluster: Whether to cluster results

        Returns:
            Batch resolution result with all decisions and clusters
        """
        import time

        start = time.time()

        results = []
        clustering_engine = ClusteringEngine(min_confidence=0.6)

        for mention in mentions:
            result = self.resolve_mention(mention)
            results.append(result)

            # Add to clustering if matched
            if result.decision in [
                ResolutionDecision.AUTO_MATCH,
                ResolutionDecision.PENDING_REVIEW,
            ]:
                if result.all_candidates:
                    best_candidate = result.all_candidates[0]
                    clustering_engine.add_match(
                        mention,
                        best_candidate.entity,
                        result.score,
                    )

        # Get clusters
        clusters = []
        if cluster:
            cluster_result = clustering_engine.get_clusters()
            clusters = cluster_result.clusters

        duration_ms = int((time.time() - start) * 1000)

        # Compute stats
        stats = {
            "total_mentions": len(mentions),
            "auto_matched": sum(
                1 for r in results if r.decision == ResolutionDecision.AUTO_MATCH
            ),
            "pending_review": sum(
                1 for r in results if r.decision == ResolutionDecision.PENDING_REVIEW
            ),
            "new_entities": sum(
                1 for r in results if r.decision == ResolutionDecision.NEW_ENTITY
            ),
            "clusters": len(clusters),
        }

        return BatchResolutionResult(
            results=results,
            clusters=clusters,
            stats=stats,
            duration_ms=duration_ms,
        )

    def submit_human_decision(
        self,
        mention_id: UUID,
        entity_id: Optional[UUID],
        is_match: bool,
        reviewer_id: str,
    ) -> ResolutionResult:
        """
        Submit a human review decision.

        Args:
            mention_id: The mention being reviewed
            entity_id: The candidate entity (None if new entity)
            is_match: Whether the human confirms the match
            reviewer_id: ID of the reviewer

        Returns:
            Updated resolution result
        """
        decision = (
            ResolutionDecision.HUMAN_MATCH
            if is_match
            else ResolutionDecision.HUMAN_REJECT
        )

        final_entity_id = entity_id if is_match else uuid4()

        return ResolutionResult(
            mention_id=mention_id,
            decision=decision,
            entity_id=final_entity_id,
            score=1.0 if is_match else 0.0,
            resolved_at=datetime.utcnow(),
            resolved_by=reviewer_id,
            reason=f"Human {'match' if is_match else 'reject'} by {reviewer_id}",
        )

    def add_entity_to_index(self, entity: CandidateEntity) -> None:
        """Add an entity to the blocking index."""
        self.blocker.add_entity(entity)

    def get_index_stats(self) -> dict[str, int]:
        """Get blocking index statistics."""
        return self.blocker.stats()
