"""
Clustering for grouping resolved mentions.

Groups mentions that have been matched to the same entity
or should be merged into a new entity.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID, uuid4

from halo.resolution.blocking import CandidateEntity, Mention

logger = logging.getLogger(__name__)


@dataclass
class MentionCluster:
    """A cluster of mentions resolved to the same entity."""

    id: UUID
    entity_id: Optional[UUID]  # None if new entity should be created
    mentions: list[Mention] = field(default_factory=list)
    canonical_name: str = ""
    entity_type: str = ""
    confidence: float = 0.0
    identifiers: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, any] = field(default_factory=dict)

    def add_mention(self, mention: Mention, confidence: float) -> None:
        """Add a mention to this cluster."""
        self.mentions.append(mention)
        # Update cluster confidence (average)
        total_conf = self.confidence * (len(self.mentions) - 1) + confidence
        self.confidence = total_conf / len(self.mentions)

        # Update identifiers from mention
        if mention.extracted_personnummer:
            self.identifiers["PERSONNUMMER"] = mention.extracted_personnummer
        if mention.extracted_orgnummer:
            self.identifiers["ORGANISATIONSNUMMER"] = mention.extracted_orgnummer

    def merge_attributes(self) -> dict[str, any]:
        """Merge attributes from all mentions."""
        merged = {}
        for mention in self.mentions:
            for key, value in mention.extracted_attributes.items():
                if key not in merged:
                    merged[key] = value
                elif isinstance(value, list):
                    existing = merged[key] if isinstance(merged[key], list) else [merged[key]]
                    merged[key] = list(set(existing + value))
        return merged

    def get_canonical_name(self) -> str:
        """Determine canonical name from mentions."""
        if self.canonical_name:
            return self.canonical_name

        # Use the longest normalized form as canonical
        if self.mentions:
            return max(
                (m.normalized_form for m in self.mentions),
                key=len,
                default="",
            )
        return ""


@dataclass
class ClusteringResult:
    """Result of clustering operation."""

    clusters: list[MentionCluster]
    orphan_mentions: list[Mention]  # Mentions that couldn't be clustered
    stats: dict[str, int] = field(default_factory=dict)


class ClusteringEngine:
    """
    Engine for clustering mentions into entity groups.

    Uses union-find algorithm for transitive closure.
    """

    def __init__(self, min_confidence: float = 0.6):
        self.min_confidence = min_confidence
        self._parent: dict[UUID, UUID] = {}
        self._rank: dict[UUID, int] = {}
        self._mention_map: dict[UUID, Mention] = {}
        self._entity_map: dict[UUID, CandidateEntity] = {}
        self._scores: dict[tuple[UUID, UUID], float] = {}

    def add_match(
        self,
        mention: Mention,
        entity: CandidateEntity,
        score: float,
    ) -> None:
        """Add a match between mention and entity."""
        if score < self.min_confidence:
            return

        self._mention_map[mention.id] = mention
        self._entity_map[entity.id] = entity
        self._scores[(mention.id, entity.id)] = score

        # Initialize union-find for both
        if mention.id not in self._parent:
            self._parent[mention.id] = mention.id
            self._rank[mention.id] = 0

        if entity.id not in self._parent:
            self._parent[entity.id] = entity.id
            self._rank[entity.id] = 1  # Entities have higher rank

        # Union them
        self._union(mention.id, entity.id)

    def add_mention_match(
        self,
        mention1: Mention,
        mention2: Mention,
        score: float,
    ) -> None:
        """Add a match between two mentions."""
        if score < self.min_confidence:
            return

        self._mention_map[mention1.id] = mention1
        self._mention_map[mention2.id] = mention2
        self._scores[(mention1.id, mention2.id)] = score

        # Initialize union-find
        for m in [mention1, mention2]:
            if m.id not in self._parent:
                self._parent[m.id] = m.id
                self._rank[m.id] = 0

        self._union(mention1.id, mention2.id)

    def get_clusters(self) -> ClusteringResult:
        """Get all clusters after matches have been added."""
        # Group by root
        root_groups: dict[UUID, list[UUID]] = {}
        for node_id in self._parent:
            root = self._find(node_id)
            if root not in root_groups:
                root_groups[root] = []
            root_groups[root].append(node_id)

        clusters = []
        orphans = []

        for root, members in root_groups.items():
            mentions = [
                self._mention_map[m]
                for m in members
                if m in self._mention_map
            ]
            entities = [
                self._entity_map[m]
                for m in members
                if m in self._entity_map
            ]

            if not mentions:
                continue

            # Determine entity_id (use existing entity if present)
            entity_id = entities[0].id if entities else None
            entity_type = mentions[0].mention_type

            # Get canonical name from entity or compute from mentions
            if entities:
                canonical_name = entities[0].canonical_name
            else:
                canonical_name = max(
                    (m.normalized_form for m in mentions),
                    key=len,
                    default="",
                )

            # Compute average confidence
            relevant_scores = [
                s for (m1, m2), s in self._scores.items()
                if m1 in members or m2 in members
            ]
            avg_confidence = (
                sum(relevant_scores) / len(relevant_scores)
                if relevant_scores else 0.0
            )

            cluster = MentionCluster(
                id=uuid4(),
                entity_id=entity_id,
                mentions=mentions,
                canonical_name=canonical_name,
                entity_type=entity_type,
                confidence=avg_confidence,
            )

            # Merge identifiers
            for mention in mentions:
                if mention.extracted_personnummer:
                    cluster.identifiers["PERSONNUMMER"] = mention.extracted_personnummer
                if mention.extracted_orgnummer:
                    cluster.identifiers["ORGANISATIONSNUMMER"] = mention.extracted_orgnummer

            for entity in entities:
                cluster.identifiers.update(entity.identifiers)

            if len(mentions) == 1 and not entities:
                # Single mention with no entity match
                orphans.append(mentions[0])
            else:
                clusters.append(cluster)

        return ClusteringResult(
            clusters=clusters,
            orphan_mentions=orphans,
            stats={
                "total_clusters": len(clusters),
                "total_orphans": len(orphans),
                "total_mentions": len(self._mention_map),
                "total_entities": len(self._entity_map),
            },
        )

    def _find(self, x: UUID) -> UUID:
        """Find root with path compression."""
        if self._parent[x] != x:
            self._parent[x] = self._find(self._parent[x])
        return self._parent[x]

    def _union(self, x: UUID, y: UUID) -> None:
        """Union by rank."""
        root_x = self._find(x)
        root_y = self._find(y)

        if root_x == root_y:
            return

        # Union by rank
        if self._rank[root_x] < self._rank[root_y]:
            self._parent[root_x] = root_y
        elif self._rank[root_x] > self._rank[root_y]:
            self._parent[root_y] = root_x
        else:
            self._parent[root_y] = root_x
            self._rank[root_x] += 1

    def clear(self) -> None:
        """Clear all state."""
        self._parent.clear()
        self._rank.clear()
        self._mention_map.clear()
        self._entity_map.clear()
        self._scores.clear()
