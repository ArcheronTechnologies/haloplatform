"""
Entity graph operations for relationship traversal and analysis.

Provides:
- Graph traversal (BFS/DFS)
- Path finding between entities
- Network analysis (centrality, clustering)
- Subgraph extraction for investigations
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from halo.db.orm import Entity, EntityRelationship, RelationshipType

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node in the entity graph."""

    entity_id: UUID
    entity_type: str
    display_name: str
    attributes: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """An edge (relationship) in the entity graph."""

    relationship_id: UUID
    from_entity_id: UUID
    to_entity_id: UUID
    relationship_type: str
    confidence: float
    attributes: dict = field(default_factory=dict)


@dataclass
class GraphPath:
    """A path between two entities."""

    nodes: list[UUID]
    edges: list[UUID]
    total_confidence: float

    @property
    def length(self) -> int:
        """Number of hops in the path."""
        return len(self.edges)


@dataclass
class Subgraph:
    """A subgraph extracted from the main entity graph."""

    nodes: dict[UUID, GraphNode]
    edges: list[GraphEdge]
    center_entity_id: Optional[UUID] = None

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)


class EntityGraph:
    """
    Graph operations on the entity database.

    Supports:
    - Finding paths between entities
    - Extracting subgraphs around an entity
    - Computing network metrics
    - Detecting communities/clusters
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize the entity graph.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def get_neighbors(
        self,
        entity_id: UUID,
        relationship_types: Optional[list[RelationshipType]] = None,
        direction: str = "both",  # 'outgoing', 'incoming', 'both'
    ) -> list[tuple[Entity, EntityRelationship]]:
        """
        Get neighboring entities connected to the given entity.

        Args:
            entity_id: Center entity ID
            relationship_types: Filter by relationship types (None = all)
            direction: Which direction of relationships to include

        Returns:
            List of (entity, relationship) tuples
        """
        neighbors = []

        # Build query based on direction
        if direction in ("outgoing", "both"):
            stmt = select(Entity, EntityRelationship).join(
                EntityRelationship,
                EntityRelationship.to_entity_id == Entity.id,
            ).where(EntityRelationship.from_entity_id == entity_id)

            if relationship_types:
                stmt = stmt.where(EntityRelationship.relationship_type.in_(relationship_types))

            result = await self.session.execute(stmt)
            neighbors.extend(result.all())

        if direction in ("incoming", "both"):
            stmt = select(Entity, EntityRelationship).join(
                EntityRelationship,
                EntityRelationship.from_entity_id == Entity.id,
            ).where(EntityRelationship.to_entity_id == entity_id)

            if relationship_types:
                stmt = stmt.where(EntityRelationship.relationship_type.in_(relationship_types))

            result = await self.session.execute(stmt)
            neighbors.extend(result.all())

        return neighbors

    async def find_path(
        self,
        from_entity_id: UUID,
        to_entity_id: UUID,
        max_depth: int = 4,
        relationship_types: Optional[list[RelationshipType]] = None,
    ) -> Optional[GraphPath]:
        """
        Find the shortest path between two entities using BFS.

        Args:
            from_entity_id: Starting entity
            to_entity_id: Target entity
            max_depth: Maximum path length to search
            relationship_types: Filter by relationship types

        Returns:
            GraphPath if found, None otherwise
        """
        if from_entity_id == to_entity_id:
            return GraphPath(nodes=[from_entity_id], edges=[], total_confidence=1.0)

        # BFS
        visited = {from_entity_id}
        queue = deque([(from_entity_id, [], [], 1.0)])  # (node, path_nodes, path_edges, confidence)

        while queue:
            current, path_nodes, path_edges, confidence = queue.popleft()

            if len(path_edges) >= max_depth:
                continue

            neighbors = await self.get_neighbors(
                current,
                relationship_types=relationship_types,
            )

            for entity, rel in neighbors:
                if entity.id in visited:
                    continue

                new_path_nodes = path_nodes + [current]
                new_path_edges = path_edges + [rel.id]
                new_confidence = confidence * rel.confidence

                if entity.id == to_entity_id:
                    return GraphPath(
                        nodes=new_path_nodes + [entity.id],
                        edges=new_path_edges,
                        total_confidence=new_confidence,
                    )

                visited.add(entity.id)
                queue.append((entity.id, new_path_nodes, new_path_edges, new_confidence))

        return None

    async def find_all_paths(
        self,
        from_entity_id: UUID,
        to_entity_id: UUID,
        max_depth: int = 4,
        max_paths: int = 10,
    ) -> list[GraphPath]:
        """
        Find all paths between two entities up to max_depth.

        Args:
            from_entity_id: Starting entity
            to_entity_id: Target entity
            max_depth: Maximum path length
            max_paths: Maximum number of paths to return

        Returns:
            List of GraphPath objects, sorted by confidence
        """
        paths = []

        async def dfs(
            current: UUID,
            path_nodes: list[UUID],
            path_edges: list[UUID],
            confidence: float,
            visited: set[UUID],
        ):
            if len(paths) >= max_paths:
                return

            if current == to_entity_id:
                paths.append(GraphPath(
                    nodes=path_nodes + [current],
                    edges=path_edges,
                    total_confidence=confidence,
                ))
                return

            if len(path_edges) >= max_depth:
                return

            neighbors = await self.get_neighbors(current)

            for entity, rel in neighbors:
                if entity.id not in visited:
                    await dfs(
                        entity.id,
                        path_nodes + [current],
                        path_edges + [rel.id],
                        confidence * rel.confidence,
                        visited | {entity.id},
                    )

        await dfs(from_entity_id, [], [], 1.0, {from_entity_id})

        # Sort by confidence descending
        paths.sort(key=lambda p: p.total_confidence, reverse=True)
        return paths[:max_paths]

    async def extract_subgraph(
        self,
        center_entity_id: UUID,
        depth: int = 2,
        max_nodes: int = 100,
        relationship_types: Optional[list[RelationshipType]] = None,
    ) -> Subgraph:
        """
        Extract a subgraph centered on an entity.

        Args:
            center_entity_id: Center entity ID
            depth: How many hops to include
            max_nodes: Maximum nodes in subgraph
            relationship_types: Filter by relationship types

        Returns:
            Subgraph with nodes and edges
        """
        nodes: dict[UUID, GraphNode] = {}
        edges: list[GraphEdge] = []
        visited: set[UUID] = set()
        queue = deque([(center_entity_id, 0)])

        # Get center entity
        result = await self.session.execute(
            select(Entity).where(Entity.id == center_entity_id)
        )
        center_entity = result.scalar_one_or_none()

        if not center_entity:
            return Subgraph(nodes={}, edges=[], center_entity_id=center_entity_id)

        nodes[center_entity_id] = GraphNode(
            entity_id=center_entity.id,
            entity_type=center_entity.entity_type.value,
            display_name=center_entity.display_name,
            attributes=center_entity.attributes,
        )
        visited.add(center_entity_id)

        while queue and len(nodes) < max_nodes:
            current_id, current_depth = queue.popleft()

            if current_depth >= depth:
                continue

            neighbors = await self.get_neighbors(
                current_id,
                relationship_types=relationship_types,
            )

            for entity, rel in neighbors:
                # Add edge
                edges.append(GraphEdge(
                    relationship_id=rel.id,
                    from_entity_id=rel.from_entity_id,
                    to_entity_id=rel.to_entity_id,
                    relationship_type=rel.relationship_type.value,
                    confidence=rel.confidence,
                    attributes=rel.attributes,
                ))

                # Add node if not visited
                if entity.id not in visited and len(nodes) < max_nodes:
                    nodes[entity.id] = GraphNode(
                        entity_id=entity.id,
                        entity_type=entity.entity_type.value,
                        display_name=entity.display_name,
                        attributes=entity.attributes,
                    )
                    visited.add(entity.id)
                    queue.append((entity.id, current_depth + 1))

        return Subgraph(
            nodes=nodes,
            edges=edges,
            center_entity_id=center_entity_id,
        )

    async def compute_degree_centrality(
        self,
        entity_ids: Optional[list[UUID]] = None,
    ) -> dict[UUID, float]:
        """
        Compute degree centrality for entities.

        Degree centrality = number of connections / (n - 1)

        Args:
            entity_ids: Specific entities to analyze (None = all)

        Returns:
            Dict mapping entity ID to centrality score
        """
        # Count relationships per entity
        degree_counts: dict[UUID, int] = defaultdict(int)

        stmt = select(EntityRelationship)
        if entity_ids:
            stmt = stmt.where(
                or_(
                    EntityRelationship.from_entity_id.in_(entity_ids),
                    EntityRelationship.to_entity_id.in_(entity_ids),
                )
            )

        result = await self.session.execute(stmt)
        relationships = result.scalars().all()

        for rel in relationships:
            degree_counts[rel.from_entity_id] += 1
            degree_counts[rel.to_entity_id] += 1

        # Normalize
        if not degree_counts:
            return {}

        n = len(degree_counts)
        if n <= 1:
            return {k: 0.0 for k in degree_counts}

        max_possible = n - 1
        return {
            entity_id: count / max_possible
            for entity_id, count in degree_counts.items()
        }

    async def find_common_connections(
        self,
        entity_id_1: UUID,
        entity_id_2: UUID,
    ) -> list[Entity]:
        """
        Find entities connected to both given entities.

        Useful for finding shared business partners, board members, etc.

        Args:
            entity_id_1: First entity
            entity_id_2: Second entity

        Returns:
            List of commonly connected entities
        """
        # Get neighbors of entity 1
        neighbors_1 = await self.get_neighbors(entity_id_1)
        neighbor_ids_1 = {e.id for e, _ in neighbors_1}

        # Get neighbors of entity 2
        neighbors_2 = await self.get_neighbors(entity_id_2)
        neighbor_ids_2 = {e.id for e, _ in neighbors_2}

        # Find intersection
        common_ids = neighbor_ids_1 & neighbor_ids_2

        if not common_ids:
            return []

        # Fetch common entities
        result = await self.session.execute(
            select(Entity).where(Entity.id.in_(list(common_ids)))
        )
        return list(result.scalars().all())

    async def detect_clusters(
        self,
        min_cluster_size: int = 3,
        relationship_types: Optional[list[RelationshipType]] = None,
    ) -> list[set[UUID]]:
        """
        Detect clusters of densely connected entities.

        Uses connected components algorithm.

        Args:
            min_cluster_size: Minimum entities in a cluster
            relationship_types: Filter by relationship types

        Returns:
            List of entity ID sets (one per cluster)
        """
        # Build adjacency list
        adjacency: dict[UUID, set[UUID]] = defaultdict(set)

        stmt = select(EntityRelationship)
        if relationship_types:
            stmt = stmt.where(EntityRelationship.relationship_type.in_(relationship_types))

        result = await self.session.execute(stmt)
        relationships = result.scalars().all()

        for rel in relationships:
            adjacency[rel.from_entity_id].add(rel.to_entity_id)
            adjacency[rel.to_entity_id].add(rel.from_entity_id)

        # Find connected components using BFS
        visited: set[UUID] = set()
        clusters: list[set[UUID]] = []

        for start_node in adjacency.keys():
            if start_node in visited:
                continue

            # BFS to find component
            cluster: set[UUID] = set()
            queue = deque([start_node])

            while queue:
                node = queue.popleft()
                if node in visited:
                    continue

                visited.add(node)
                cluster.add(node)

                for neighbor in adjacency[node]:
                    if neighbor not in visited:
                        queue.append(neighbor)

            if len(cluster) >= min_cluster_size:
                clusters.append(cluster)

        # Sort by size descending
        clusters.sort(key=len, reverse=True)
        return clusters

    def to_networkx(self, subgraph: Subgraph) -> Any:
        """
        Convert subgraph to NetworkX graph for advanced analysis.

        Requires networkx to be installed.

        Args:
            subgraph: Subgraph to convert

        Returns:
            NetworkX DiGraph
        """
        try:
            import networkx as nx
        except ImportError:
            raise ImportError("networkx is required for this function")

        G = nx.DiGraph()

        # Add nodes
        for node_id, node in subgraph.nodes.items():
            G.add_node(
                str(node_id),
                entity_type=node.entity_type,
                display_name=node.display_name,
                **node.attributes,
            )

        # Add edges
        for edge in subgraph.edges:
            G.add_edge(
                str(edge.from_entity_id),
                str(edge.to_entity_id),
                relationship_type=edge.relationship_type,
                confidence=edge.confidence,
                **edge.attributes,
            )

        return G
