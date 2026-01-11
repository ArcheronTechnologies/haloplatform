"""
Graph API routes.

Provides endpoints for the intelligence graph operations:
- Entity retrieval with graph context
- Neighbor/network exploration
- Network metrics and centrality
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from halo.api.deps import AuditRepo, User
from halo.graph.client import GraphClient

router = APIRouter()


# Singleton graph client (in production, use proper dependency injection)
_graph_client: Optional[GraphClient] = None


async def get_graph_client() -> GraphClient:
    """Get or create graph client."""
    global _graph_client
    if _graph_client is None:
        _graph_client = GraphClient()
    return _graph_client


GraphClientDep = Annotated[GraphClient, Depends(get_graph_client)]


# Response models
class GraphEntityResponse(BaseModel):
    """Response for graph entity."""
    id: str
    type: str
    properties: dict
    network_metrics: Optional[dict] = None


class NeighborResponse(BaseModel):
    """Response for neighbor entity."""
    entity: dict
    edge: dict
    direction: str  # "incoming" or "outgoing"


class NetworkResponse(BaseModel):
    """Response for network exploration."""
    seed_entity_id: str
    entities: list[dict]
    edges: list[dict]
    total_nodes: int
    total_edges: int


class CentralityResponse(BaseModel):
    """Response for centrality metrics."""
    degree: dict[str, float]
    betweenness: dict[str, float]
    pagerank: dict[str, float]
    clustering: dict[str, float]


class ComponentsResponse(BaseModel):
    """Response for connected components."""
    components: list[list[str]]
    total_components: int
    largest_component_size: int


class FullGraphResponse(BaseModel):
    """Response for full graph visualization."""
    nodes: list[dict]
    edges: list[dict]
    clusters: list[dict]
    stats: dict


@router.get("/entities/{entity_id}", response_model=GraphEntityResponse)
async def get_graph_entity(
    entity_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
    include_metrics: bool = Query(False, description="Include network metrics"),
):
    """
    Get entity from the intelligence graph.

    Returns entity properties and optionally network metrics.
    """
    async with graph:
        if include_metrics:
            entity_data = await graph.get_entity_with_context(entity_id)
        else:
            entity_data = await graph.get_entity(entity_id)

        if not entity_data:
            raise HTTPException(status_code=404, detail="Entity not found in graph")

        # Log access
        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="view",
            resource_type="graph_entity",
            resource_id=entity_id,
        )

        return GraphEntityResponse(
            id=entity_id,
            type=entity_data.get("_type", "Unknown"),
            properties=entity_data,
            network_metrics=entity_data.get("network_metrics") if include_metrics else None,
        )


@router.get("/entities/{entity_id}/neighbors", response_model=list[NeighborResponse])
async def get_entity_neighbors(
    entity_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
    hops: int = Query(1, ge=1, le=3, description="Number of hops to traverse"),
    edge_types: Optional[str] = Query(None, description="Comma-separated edge types to follow"),
):
    """
    Get neighbors of an entity in the graph.

    Returns connected entities up to N hops away.
    """
    async with graph:
        # Parse edge types if provided
        types_list = edge_types.split(",") if edge_types else None

        neighbors = await graph.get_neighbors(entity_id, hops=hops, edge_types=types_list)

        # Log access
        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="view",
            resource_type="graph_neighbors",
            resource_id=entity_id,
            details={"hops": hops, "count": len(neighbors)},
        )

        result = []
        for neighbor in neighbors:
            edge = neighbor.get("edge", {})
            direction = "incoming" if edge.get("to_id") == entity_id else "outgoing"
            result.append(NeighborResponse(
                entity=neighbor.get("m", {}),
                edge=edge,
                direction=direction,
            ))

        return result


@router.get("/entities/{entity_id}/network", response_model=NetworkResponse)
async def get_entity_network(
    entity_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
    hops: int = Query(2, ge=1, le=4, description="Network depth"),
    max_nodes: int = Query(100, ge=1, le=500, description="Maximum nodes to return"),
):
    """
    Get the network around an entity.

    Returns all entities and edges within N hops, suitable for visualization.
    """
    async with graph:
        neighbors = await graph.get_neighbors(entity_id, hops=hops)

        # Build network structure
        entities = {}
        edges = []

        # Add seed entity
        seed = await graph.get_entity(entity_id)
        if seed:
            entities[entity_id] = seed

        # Add neighbors and edges
        for neighbor in neighbors[:max_nodes]:
            entity = neighbor.get("m", {})
            edge = neighbor.get("edge", {})

            if entity.get("id"):
                entities[entity["id"]] = entity

            if edge:
                edges.append(edge)

        # Log access
        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="view",
            resource_type="graph_network",
            resource_id=entity_id,
            details={"hops": hops, "nodes": len(entities), "edges": len(edges)},
        )

        return NetworkResponse(
            seed_entity_id=entity_id,
            entities=list(entities.values()),
            edges=edges,
            total_nodes=len(entities),
            total_edges=len(edges),
        )


@router.get("/metrics/centrality", response_model=CentralityResponse)
async def get_centrality_metrics(
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Get centrality metrics for all entities in the graph.

    Returns degree, betweenness, PageRank, and clustering coefficients.
    """
    async with graph:
        metrics = graph.compute_centrality()

        # Log access
        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="compute",
            resource_type="graph_centrality",
            resource_id="global",
        )

        return CentralityResponse(
            degree=metrics.get("degree", {}),
            betweenness=metrics.get("betweenness", {}),
            pagerank=metrics.get("pagerank", {}),
            clustering=metrics.get("clustering", {}),
        )


@router.get("/metrics/components", response_model=ComponentsResponse)
async def get_connected_components(
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Get connected components in the graph.

    Returns groups of entities that are connected to each other.
    """
    async with graph:
        components = graph.find_connected_components()

        # Sort by size descending
        sorted_components = sorted(components, key=len, reverse=True)

        # Log access
        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="compute",
            resource_type="graph_components",
            resource_id="global",
            details={"total_components": len(components)},
        )

        return ComponentsResponse(
            components=[list(c) for c in sorted_components],
            total_components=len(components),
            largest_component_size=len(sorted_components[0]) if sorted_components else 0,
        )


@router.get("/full", response_model=FullGraphResponse)
async def get_full_graph(
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
    max_nodes: int = Query(200, ge=1, le=1000, description="Maximum nodes to return"),
    min_shell_score: float = Query(0, ge=0, le=1, description="Minimum shell score filter"),
    mode: str = Query("connected", description="Mode: connected, all, or high_risk"),
):
    """
    Get full graph visualization data.

    Returns nodes, edges, clusters, and statistics for network visualization.
    """
    async with graph:
        # Get all entities from the graph
        all_entities = await graph.get_all_entities(limit=max_nodes * 2)

        # Filter by mode
        if mode == "connected":
            # Prioritize entities with more connections
            entities = sorted(all_entities, key=lambda e: e.get("degree", 0), reverse=True)[:max_nodes]
        elif mode == "high_risk":
            # Prioritize high shell scores
            entities = [e for e in all_entities if e.get("shell_score", 0) >= min_shell_score]
            entities = sorted(entities, key=lambda e: e.get("shell_score", 0), reverse=True)[:max_nodes]
        else:  # all
            entities = all_entities[:max_nodes]

        entity_ids = {e["id"] for e in entities}

        # Get all edges between these entities
        all_edges = []
        for entity in entities:
            entity_edges = await graph.get_entity_edges(entity["id"])
            # Only include edges where both nodes are in our entity set
            all_edges.extend([e for e in entity_edges if e["source"] in entity_ids and e["target"] in entity_ids])

        # Remove duplicate edges
        unique_edges = []
        seen_edges = set()
        for edge in all_edges:
            edge_key = tuple(sorted([edge["source"], edge["target"]]))
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                unique_edges.append(edge)

        # Find clusters (connected components)
        components = graph.find_connected_components()

        # Convert to cluster format
        clusters = []
        for i, component in enumerate(sorted(components, key=len, reverse=True)[:20]):
            # Only include clusters that have entities in our filtered set
            cluster_entities = [eid for eid in component if eid in entity_ids]
            if not cluster_entities:
                continue

            cluster_companies = sum(1 for eid in cluster_entities if entities[entity_ids.index(eid)].get("type") == "Company")
            cluster_persons = sum(1 for eid in cluster_entities if entities[entity_ids.index(eid)].get("type") == "Person")
            shell_scores = [entities[entity_ids.index(eid)].get("shell_score", 0) for eid in cluster_entities]

            clusters.append({
                "id": f"cluster_{i}",
                "nodes": cluster_entities,
                "size": len(cluster_entities),
                "avgShellScore": sum(shell_scores) / len(shell_scores) if shell_scores else 0,
                "maxShellScore": max(shell_scores) if shell_scores else 0,
                "companyCount": cluster_companies,
                "personCount": cluster_persons,
            })

        # Convert entities to node format
        nodes = []
        for entity in entities:
            nodes.append({
                "id": entity["id"],
                "type": entity.get("type", "Unknown"),
                "label": entity.get("name", entity["id"]),
                "riskScore": entity.get("risk_score", 0),
                "shellScore": entity.get("shell_score", 0),
                "degree": entity.get("degree", 0),
                "clusterId": next((c["id"] for c in clusters if entity["id"] in c["nodes"]), None),
            })

        # Calculate stats
        company_count = sum(1 for n in nodes if n["type"] == "Company")
        person_count = sum(1 for n in nodes if n["type"] == "Person")
        connected_count = sum(1 for n in nodes if n["degree"] > 0)

        stats = {
            "total_nodes": len(all_entities),
            "total_edges": len(all_edges),
            "displayed_nodes": len(nodes),
            "displayed_edges": len(unique_edges),
            "connected_nodes": connected_count,
            "cluster_count": len(clusters),
            "total_companies": company_count,
            "total_persons": person_count,
        }

        # Log access
        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="view",
            resource_type="graph_full",
            resource_id="global",
            details={"mode": mode, "max_nodes": max_nodes, "displayed_nodes": len(nodes)},
        )

        return FullGraphResponse(
            nodes=nodes,
            edges=unique_edges,
            clusters=clusters,
            stats=stats,
        )
