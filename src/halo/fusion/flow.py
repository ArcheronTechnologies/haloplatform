"""
Flow analysis for tracking movement patterns.

Analyzes flows across the network:
- Financial flows (money movement)
- Physical flows (location patterns)
- Organizational flows (control and ownership)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class FlowType(str, Enum):
    """Types of flows to analyze."""

    FINANCIAL = "financial"  # Money movement
    PHYSICAL = "physical"  # Location/address changes
    OWNERSHIP = "ownership"  # Ownership transfers
    CONTROL = "control"  # Control/director changes
    GOODS = "goods"  # Physical goods movement


@dataclass
class FlowNode:
    """A node in a flow network."""

    id: UUID
    entity_id: UUID
    entity_type: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)

    # Flow statistics
    inflow_count: int = 0
    outflow_count: int = 0
    inflow_value: float = 0.0
    outflow_value: float = 0.0

    def net_flow(self) -> float:
        """Calculate net flow (inflow - outflow)."""
        return self.inflow_value - self.outflow_value

    def is_sink(self) -> bool:
        """Check if node is primarily a sink (more inflow)."""
        return self.inflow_value > self.outflow_value * 1.5

    def is_source(self) -> bool:
        """Check if node is primarily a source (more outflow)."""
        return self.outflow_value > self.inflow_value * 1.5

    def is_pass_through(self) -> bool:
        """Check if node is a pass-through (similar in/out)."""
        if self.inflow_value == 0 or self.outflow_value == 0:
            return False
        ratio = self.inflow_value / self.outflow_value
        return 0.8 <= ratio <= 1.2

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id),
            "entity_type": self.entity_type,
            "label": self.label,
            "properties": self.properties,
            "inflow_count": self.inflow_count,
            "outflow_count": self.outflow_count,
            "inflow_value": self.inflow_value,
            "outflow_value": self.outflow_value,
            "net_flow": self.net_flow(),
            "is_sink": self.is_sink(),
            "is_source": self.is_source(),
            "is_pass_through": self.is_pass_through(),
        }


@dataclass
class FlowEdge:
    """An edge representing flow between nodes."""

    source_id: UUID
    target_id: UUID
    flow_type: FlowType
    value: float
    occurred_at: datetime
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_id": str(self.source_id),
            "target_id": str(self.target_id),
            "flow_type": self.flow_type.value,
            "value": self.value,
            "occurred_at": self.occurred_at.isoformat(),
            "description": self.description,
            "metadata": self.metadata,
        }


@dataclass
class FlowPath:
    """A path through the flow network."""

    nodes: list[FlowNode]
    edges: list[FlowEdge]
    flow_type: FlowType
    total_value: float
    path_length: int
    start_time: datetime
    end_time: datetime
    risk_indicators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "flow_type": self.flow_type.value,
            "total_value": self.total_value,
            "path_length": self.path_length,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "risk_indicators": self.risk_indicators,
        }


class FlowAnalyzer:
    """
    Analyzes flow patterns in entity networks.

    Identifies suspicious patterns like:
    - Layering (many pass-through entities)
    - Concentration (money flowing to few sinks)
    - Circular flows (money returning to source)
    """

    def __init__(self):
        self._nodes: dict[UUID, FlowNode] = {}
        self._edges: list[FlowEdge] = []
        self._adjacency: dict[UUID, list[FlowEdge]] = {}

    def add_node(self, node: FlowNode) -> None:
        """Add a node to the flow network."""
        self._nodes[node.id] = node
        if node.id not in self._adjacency:
            self._adjacency[node.id] = []

    def add_edge(self, edge: FlowEdge) -> None:
        """Add a flow edge to the network."""
        self._edges.append(edge)

        # Update adjacency list
        if edge.source_id not in self._adjacency:
            self._adjacency[edge.source_id] = []
        self._adjacency[edge.source_id].append(edge)

        # Update node statistics
        if edge.source_id in self._nodes:
            self._nodes[edge.source_id].outflow_count += 1
            self._nodes[edge.source_id].outflow_value += edge.value
        if edge.target_id in self._nodes:
            self._nodes[edge.target_id].inflow_count += 1
            self._nodes[edge.target_id].inflow_value += edge.value

    def find_paths(
        self,
        source_id: UUID,
        target_id: Optional[UUID] = None,
        flow_type: Optional[FlowType] = None,
        max_depth: int = 5,
    ) -> list[FlowPath]:
        """
        Find flow paths from source to target.

        Args:
            source_id: Starting node
            target_id: Ending node (optional, finds all paths if None)
            flow_type: Filter by flow type
            max_depth: Maximum path length

        Returns:
            List of flow paths
        """
        paths = []

        def dfs(
            current: UUID,
            path_nodes: list[FlowNode],
            path_edges: list[FlowEdge],
            visited: set[UUID],
        ):
            if len(path_nodes) > max_depth:
                return

            # Check if we've reached target
            if target_id and current == target_id and path_edges:
                paths.append(self._create_path(path_nodes, path_edges, flow_type))
                return

            # If no target, create path at each node
            if not target_id and path_edges:
                paths.append(self._create_path(path_nodes, path_edges, flow_type))

            # Continue DFS
            for edge in self._adjacency.get(current, []):
                if flow_type and edge.flow_type != flow_type:
                    continue
                if edge.target_id in visited:
                    continue

                target_node = self._nodes.get(edge.target_id)
                if not target_node:
                    continue

                visited.add(edge.target_id)
                dfs(
                    edge.target_id,
                    path_nodes + [target_node],
                    path_edges + [edge],
                    visited,
                )
                visited.remove(edge.target_id)

        start_node = self._nodes.get(source_id)
        if start_node:
            dfs(source_id, [start_node], [], {source_id})

        return paths

    def find_circular_flows(
        self,
        flow_type: Optional[FlowType] = None,
        min_value: float = 0.0,
    ) -> list[FlowPath]:
        """
        Find circular flow patterns (money laundering indicator).

        Args:
            flow_type: Filter by flow type
            min_value: Minimum flow value

        Returns:
            List of circular flow paths
        """
        circular_paths = []

        for node_id in self._nodes:
            # Find paths that return to source
            paths = self.find_paths(
                source_id=node_id,
                target_id=node_id,
                flow_type=flow_type,
                max_depth=6,
            )

            for path in paths:
                if path.total_value >= min_value:
                    path.risk_indicators.append("Circular flow detected")
                    circular_paths.append(path)

        return circular_paths

    def find_layering_patterns(
        self,
        min_layers: int = 3,
    ) -> list[FlowPath]:
        """
        Find layering patterns (many pass-through entities).

        Args:
            min_layers: Minimum number of pass-through entities

        Returns:
            List of paths with layering
        """
        layering_paths = []

        for path in self._get_all_paths():
            # Count pass-through nodes (excluding source and sink)
            middle_nodes = path.nodes[1:-1] if len(path.nodes) > 2 else []
            pass_through_count = sum(
                1 for n in middle_nodes if n.is_pass_through()
            )

            if pass_through_count >= min_layers:
                path.risk_indicators.append(
                    f"Layering: {pass_through_count} pass-through entities"
                )
                layering_paths.append(path)

        return layering_paths

    def find_sinks(
        self,
        min_inflow: float = 0.0,
    ) -> list[FlowNode]:
        """
        Find sink nodes (entities receiving more than they send).

        Args:
            min_inflow: Minimum total inflow

        Returns:
            List of sink nodes
        """
        sinks = []
        for node in self._nodes.values():
            if node.is_sink() and node.inflow_value >= min_inflow:
                sinks.append(node)

        return sorted(sinks, key=lambda n: n.inflow_value, reverse=True)

    def find_sources(
        self,
        min_outflow: float = 0.0,
    ) -> list[FlowNode]:
        """
        Find source nodes (entities sending more than they receive).

        Args:
            min_outflow: Minimum total outflow

        Returns:
            List of source nodes
        """
        sources = []
        for node in self._nodes.values():
            if node.is_source() and node.outflow_value >= min_outflow:
                sources.append(node)

        return sorted(sources, key=lambda n: n.outflow_value, reverse=True)

    def get_flow_summary(self) -> dict[str, Any]:
        """Get summary statistics for the flow network."""
        total_flow = sum(e.value for e in self._edges)
        node_count = len(self._nodes)
        edge_count = len(self._edges)

        sinks = self.find_sinks()
        sources = self.find_sources()
        pass_throughs = [n for n in self._nodes.values() if n.is_pass_through()]

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "total_flow_value": total_flow,
            "sink_count": len(sinks),
            "source_count": len(sources),
            "pass_through_count": len(pass_throughs),
            "average_path_length": self._average_path_length(),
        }

    def _create_path(
        self,
        nodes: list[FlowNode],
        edges: list[FlowEdge],
        flow_type: Optional[FlowType],
    ) -> FlowPath:
        """Create a FlowPath from nodes and edges."""
        total_value = sum(e.value for e in edges)
        return FlowPath(
            nodes=nodes,
            edges=edges,
            flow_type=flow_type or FlowType.FINANCIAL,
            total_value=total_value,
            path_length=len(edges),
            start_time=edges[0].occurred_at if edges else datetime.utcnow(),
            end_time=edges[-1].occurred_at if edges else datetime.utcnow(),
            risk_indicators=[],
        )

    def _get_all_paths(self, max_depth: int = 5) -> list[FlowPath]:
        """Get all paths in the network."""
        all_paths = []
        for node_id in self._nodes:
            paths = self.find_paths(source_id=node_id, max_depth=max_depth)
            all_paths.extend(paths)
        return all_paths

    def _average_path_length(self) -> float:
        """Calculate average path length in the network."""
        paths = self._get_all_paths(max_depth=3)  # Limit for performance
        if not paths:
            return 0.0
        return sum(p.path_length for p in paths) / len(paths)
