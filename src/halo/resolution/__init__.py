"""
Entity resolution system for matching mentions to entities.

This module implements rule-based entity resolution:
- Blocking: Efficient candidate generation
- Comparison: Feature-based similarity scoring
- Clustering: Grouping matched mentions
- Resolver: Main resolution pipeline
- Exact Match: Gold-standard identifier matching for Swedish IDs
"""

from halo.resolution.blocking import BlockingIndex, BlockingStrategy, Mention, CandidateEntity
from halo.resolution.comparison import FeatureComparator, FeatureScores
from halo.resolution.clustering import MentionCluster, ClusteringEngine
from halo.resolution.resolver import (
    EntityResolver,
    ResolutionResult,
    ResolutionDecision,
    ResolutionConfig,
)
from halo.resolution.exact_match import (
    ExactMatchResolver,
    ExactMatchResult,
    resolve_mention_exact,
    validate_identifier,
)

__all__ = [
    # Blocking
    "BlockingIndex",
    "BlockingStrategy",
    "Mention",
    "CandidateEntity",
    # Comparison
    "FeatureComparator",
    "FeatureScores",
    # Clustering
    "MentionCluster",
    "ClusteringEngine",
    # Main resolver
    "EntityResolver",
    "ResolutionResult",
    "ResolutionDecision",
    "ResolutionConfig",
    # Exact match (Swedish identifiers)
    "ExactMatchResolver",
    "ExactMatchResult",
    "resolve_mention_exact",
    "validate_identifier",
]
