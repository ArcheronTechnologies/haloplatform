"""
Risk scoring for transaction anomaly detection.

Combines multiple pattern signals into a unified risk score
with explanations for human review.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from halo.anomaly.transaction_patterns import PatternMatch, PatternType
from halo.config import settings


@dataclass
class RiskScore:
    """Risk score result for an entity or transaction."""

    score: float  # 0.0 to 1.0
    tier: int  # 1, 2, or 3 (for human-in-loop)
    factors: list[str]  # Explanation of contributing factors
    pattern_matches: list[PatternMatch] = field(default_factory=list)
    entity_id: Optional[UUID] = None
    calculated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def severity(self) -> str:
        """Get severity level based on score."""
        if self.score >= 0.85:
            return "critical"
        elif self.score >= 0.70:
            return "high"
        elif self.score >= 0.50:
            return "medium"
        else:
            return "low"

    @property
    def requires_review(self) -> bool:
        """Check if this score requires human review."""
        return self.tier >= 2


class RiskScorer:
    """
    Calculates risk scores from detected patterns.

    Uses weighted combination of pattern confidences
    with adjustments for pattern severity and recency.
    """

    # Weights for different pattern types
    PATTERN_WEIGHTS = {
        PatternType.STRUCTURING: 1.0,  # Most serious
        PatternType.RAPID_IN_OUT: 0.8,
        PatternType.VELOCITY_SPIKE: 0.7,
        PatternType.NEW_COUNTERPARTY: 0.5,
        PatternType.ROUND_AMOUNTS: 0.4,
        PatternType.UNUSUAL_TIME: 0.3,
        PatternType.DORMANT_REACTIVATION: 0.6,
    }

    def __init__(
        self,
        tier_3_threshold: float = None,
        tier_2_threshold: float = None,
    ):
        """
        Initialize the risk scorer.

        Args:
            tier_3_threshold: Score threshold for Tier 3 (approval required)
            tier_2_threshold: Score threshold for Tier 2 (acknowledgment required)
        """
        self.tier_3_threshold = tier_3_threshold or settings.tier_3_threshold
        self.tier_2_threshold = tier_2_threshold or settings.tier_2_threshold

    def calculate_score(
        self,
        patterns: list[PatternMatch],
        entity_id: Optional[UUID] = None,
        affects_person: bool = True,
    ) -> RiskScore:
        """
        Calculate risk score from detected patterns.

        Args:
            patterns: List of detected patterns
            entity_id: Entity being scored
            affects_person: Whether this affects an identifiable person

        Returns:
            RiskScore with score, tier, and explanation
        """
        if not patterns:
            return RiskScore(
                score=0.0,
                tier=1,
                factors=["No suspicious patterns detected"],
                entity_id=entity_id,
            )

        # Calculate weighted score
        weighted_sum = 0.0
        weight_total = 0.0
        factors = []

        for pattern in patterns:
            weight = self.PATTERN_WEIGHTS.get(pattern.pattern_type, 0.5)
            contribution = pattern.confidence * weight

            weighted_sum += contribution
            weight_total += weight

            factors.append(
                f"{pattern.pattern_type.value}: {pattern.description} "
                f"(confidence: {pattern.confidence:.0%})"
            )

        # Normalize score
        if weight_total > 0:
            base_score = weighted_sum / weight_total
        else:
            base_score = 0.0

        # Boost for multiple patterns (compound risk)
        pattern_count_bonus = min(0.2, len(patterns) * 0.05)
        final_score = min(1.0, base_score + pattern_count_bonus)

        # Determine tier based on score and whether it affects a person
        tier = self._determine_tier(final_score, affects_person)

        return RiskScore(
            score=final_score,
            tier=tier,
            factors=factors,
            pattern_matches=patterns,
            entity_id=entity_id,
        )

    def _determine_tier(self, score: float, affects_person: bool) -> int:
        """
        Determine review tier based on score.

        Implements Brottsdatalagen compliance requirements.
        """
        if not affects_person:
            return 1  # Entity-only, no review needed

        if score >= self.tier_3_threshold:
            return 3  # Requires approval with justification

        if score >= self.tier_2_threshold:
            return 2  # Requires acknowledgment

        return 1  # Informational only

    def score_entity(
        self,
        entity_id: UUID,
        patterns: list[PatternMatch],
        historical_scores: Optional[list[RiskScore]] = None,
    ) -> RiskScore:
        """
        Calculate risk score for a specific entity.

        Takes into account historical risk scores for trend analysis.

        Args:
            entity_id: Entity to score
            patterns: Current patterns involving the entity
            historical_scores: Previous risk scores

        Returns:
            Updated risk score
        """
        # Filter patterns to this entity
        entity_patterns = [
            p for p in patterns if entity_id in p.entity_ids
        ]

        # Calculate base score
        score = self.calculate_score(entity_patterns, entity_id)

        # Adjust for historical trends
        if historical_scores:
            # If entity has been flagged before, increase score
            prev_high_scores = [
                s.score for s in historical_scores if s.score >= 0.5
            ]
            if len(prev_high_scores) >= 2:
                trend_bonus = min(0.15, len(prev_high_scores) * 0.05)
                score.score = min(1.0, score.score + trend_bonus)
                score.factors.append(
                    f"Historical risk: {len(prev_high_scores)} previous high-risk scores"
                )

                # Recalculate tier
                score.tier = self._determine_tier(score.score, True)

        return score

    def aggregate_scores(
        self,
        scores: list[RiskScore],
    ) -> RiskScore:
        """
        Aggregate multiple risk scores into one.

        Used for combining entity and transaction scores.

        Args:
            scores: List of risk scores to aggregate

        Returns:
            Aggregated score
        """
        if not scores:
            return RiskScore(score=0.0, tier=1, factors=["No data"])

        # Take maximum score
        max_score = max(scores, key=lambda s: s.score)

        # Combine factors
        all_factors = []
        all_patterns = []
        for score in scores:
            all_factors.extend(score.factors)
            all_patterns.extend(score.pattern_matches)

        # Deduplicate
        seen_factors = set()
        unique_factors = []
        for f in all_factors:
            if f not in seen_factors:
                seen_factors.add(f)
                unique_factors.append(f)

        return RiskScore(
            score=max_score.score,
            tier=max_score.tier,
            factors=unique_factors,
            pattern_matches=all_patterns,
        )
