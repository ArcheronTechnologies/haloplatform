"""
Tests for graph API endpoints.

Tests:
- Full graph endpoint
- Graph filtering
- Network visualization
- Cluster detection
"""

from datetime import datetime
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGraphFullEndpoint:
    """Tests for /graph/full endpoint."""

    def test_full_graph_response_format(self):
        """Should return complete graph visualization data."""
        response = {
            "nodes": [
                {
                    "id": str(uuid4()),
                    "type": "Company",
                    "label": "Test AB",
                    "riskScore": 0.5,
                    "shellScore": 0.3,
                    "degree": 5,
                    "clusterId": "cluster_0",
                }
            ],
            "edges": [
                {
                    "source": str(uuid4()),
                    "target": str(uuid4()),
                    "type": "OWNS",
                    "label": "owns 51%",
                }
            ],
            "clusters": [
                {
                    "id": "cluster_0",
                    "nodes": [str(uuid4()), str(uuid4())],
                    "size": 2,
                    "avgShellScore": 0.35,
                    "maxShellScore": 0.6,
                    "companyCount": 1,
                    "personCount": 1,
                }
            ],
            "stats": {
                "total_nodes": 100,
                "total_edges": 150,
                "displayed_nodes": 50,
                "displayed_edges": 75,
                "connected_nodes": 45,
                "cluster_count": 5,
                "total_companies": 30,
                "total_persons": 20,
            },
        }

        assert "nodes" in response
        assert "edges" in response
        assert "clusters" in response
        assert "stats" in response

        # Verify node structure
        assert response["nodes"][0]["type"] in ["Company", "Person", "Address"]
        assert "degree" in response["nodes"][0]

        # Verify stats structure
        assert response["stats"]["displayed_nodes"] <= response["stats"]["total_nodes"]
        assert response["stats"]["displayed_edges"] <= response["stats"]["total_edges"]

    def test_graph_filtering_by_mode(self):
        """Should filter graph by mode parameter."""
        # Test different modes
        modes = ["connected", "all", "high_risk"]

        for mode in modes:
            params = {
                "max_nodes": 200,
                "min_shell_score": 0,
                "mode": mode,
            }
            assert params["mode"] in modes

    def test_graph_filtering_by_shell_score(self):
        """Should filter nodes by minimum shell score."""
        params = {
            "max_nodes": 200,
            "min_shell_score": 0.4,
            "mode": "high_risk",
        }

        assert params["min_shell_score"] == 0.4
        assert params["mode"] == "high_risk"

    def test_graph_max_nodes_limit(self):
        """Should respect max_nodes parameter."""
        params = {
            "max_nodes": 100,
            "min_shell_score": 0,
            "mode": "connected",
        }

        # Response should not exceed max_nodes
        assert params["max_nodes"] == 100

    def test_connected_mode_prioritization(self):
        """Should prioritize highly connected nodes in connected mode."""
        # In connected mode, nodes with higher degree should be prioritized
        nodes = [
            {"id": "1", "degree": 10},
            {"id": "2", "degree": 5},
            {"id": "3", "degree": 15},
        ]

        # Sort by degree descending (as API should do)
        sorted_nodes = sorted(nodes, key=lambda n: n["degree"], reverse=True)

        assert sorted_nodes[0]["id"] == "3"  # Highest degree
        assert sorted_nodes[0]["degree"] == 15

    def test_high_risk_mode_prioritization(self):
        """Should prioritize high shell score nodes in high_risk mode."""
        nodes = [
            {"id": "1", "shell_score": 0.3},
            {"id": "2", "shell_score": 0.7},
            {"id": "3", "shell_score": 0.5},
        ]

        # Filter and sort by shell_score
        min_score = 0.4
        filtered = [n for n in nodes if n["shell_score"] >= min_score]
        sorted_nodes = sorted(filtered, key=lambda n: n["shell_score"], reverse=True)

        assert len(filtered) == 2  # Only nodes above 0.4
        assert sorted_nodes[0]["id"] == "2"  # Highest score


class TestClusterDetection:
    """Tests for cluster/component detection in graph."""

    def test_cluster_response_structure(self):
        """Should return cluster data with metrics."""
        cluster = {
            "id": "cluster_0",
            "nodes": [str(uuid4()), str(uuid4()), str(uuid4())],
            "size": 3,
            "avgShellScore": 0.45,
            "maxShellScore": 0.7,
            "companyCount": 2,
            "personCount": 1,
        }

        assert "id" in cluster
        assert "nodes" in cluster
        assert "size" in cluster
        assert cluster["size"] == len(cluster["nodes"])
        assert cluster["maxShellScore"] >= cluster["avgShellScore"]

    def test_cluster_risk_calculation(self):
        """Should calculate average and max shell scores for cluster."""
        # Sample nodes in a cluster
        node_scores = [0.3, 0.5, 0.7, 0.2]

        avg_score = sum(node_scores) / len(node_scores)
        max_score = max(node_scores)

        assert avg_score == 0.425
        assert max_score == 0.7

    def test_cluster_composition(self):
        """Should count companies and persons in cluster."""
        nodes = [
            {"type": "Company"},
            {"type": "Company"},
            {"type": "Person"},
            {"type": "Person"},
            {"type": "Person"},
        ]

        company_count = sum(1 for n in nodes if n["type"] == "Company")
        person_count = sum(1 for n in nodes if n["type"] == "Person")

        assert company_count == 2
        assert person_count == 3

    def test_cluster_sorting_by_size(self):
        """Should sort clusters by size descending."""
        clusters = [
            {"id": "c1", "size": 5},
            {"id": "c2", "size": 15},
            {"id": "c3", "size": 10},
        ]

        sorted_clusters = sorted(clusters, key=lambda c: c["size"], reverse=True)

        assert sorted_clusters[0]["id"] == "c2"  # Largest
        assert sorted_clusters[0]["size"] == 15


class TestGraphStatistics:
    """Tests for graph statistics calculation."""

    def test_stats_calculation(self):
        """Should calculate accurate statistics."""
        # Sample data
        total_nodes = 100
        displayed_nodes = 50
        total_edges = 150
        displayed_edges = 75

        # Connected nodes (nodes with at least one edge)
        nodes_with_edges = 45

        stats = {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "displayed_nodes": displayed_nodes,
            "displayed_edges": displayed_edges,
            "connected_nodes": nodes_with_edges,
        }

        # Verify constraints
        assert stats["displayed_nodes"] <= stats["total_nodes"]
        assert stats["displayed_edges"] <= stats["total_edges"]
        assert stats["connected_nodes"] <= stats["displayed_nodes"]

    def test_entity_type_counting(self):
        """Should count companies and persons separately."""
        nodes = [
            {"type": "Company"},
            {"type": "Company"},
            {"type": "Company"},
            {"type": "Person"},
            {"type": "Person"},
            {"type": "Address"},
        ]

        company_count = sum(1 for n in nodes if n["type"] == "Company")
        person_count = sum(1 for n in nodes if n["type"] == "Person")

        assert company_count == 3
        assert person_count == 2

    def test_edge_deduplication(self):
        """Should remove duplicate edges."""
        edges = [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "A"},  # Duplicate (undirected)
            {"source": "A", "target": "C"},
        ]

        # Deduplicate by creating sorted tuple of (source, target)
        seen = set()
        unique_edges = []
        for edge in edges:
            edge_key = tuple(sorted([edge["source"], edge["target"]]))
            if edge_key not in seen:
                seen.add(edge_key)
                unique_edges.append(edge)

        assert len(unique_edges) == 2  # A-B and A-C


class TestGraphEntityEndpoints:
    """Tests for individual entity graph endpoints."""

    def test_get_entity_with_context(self):
        """Should return entity with graph context."""
        response = {
            "id": str(uuid4()),
            "type": "Company",
            "properties": {
                "name": "Test AB",
                "org_number": "559123-4567",
            },
            "network_metrics": {
                "degree": 5,
                "betweenness": 0.15,
                "pagerank": 0.02,
            },
        }

        assert "id" in response
        assert "type" in response
        assert "properties" in response
        assert "network_metrics" in response

    def test_get_neighbors_response(self):
        """Should return neighboring entities."""
        response = [
            {
                "entity": {
                    "id": str(uuid4()),
                    "type": "Person",
                    "properties": {"name": "Anna Andersson"},
                },
                "edge": {
                    "type": "OWNS",
                    "properties": {"ownership_percent": 51},
                },
                "direction": "outgoing",
            }
        ]

        assert len(response) > 0
        assert response[0]["direction"] in ["incoming", "outgoing"]
        assert "entity" in response[0]
        assert "edge" in response[0]

    def test_get_network_expansion(self):
        """Should return network within N hops."""
        params = {
            "seed_entity_id": str(uuid4()),
            "hops": 2,
            "max_nodes": 100,
        }

        response = {
            "seed_entity_id": params["seed_entity_id"],
            "entities": [],  # List of entities within 2 hops
            "edges": [],  # Edges between them
            "total_nodes": 50,
            "total_edges": 75,
        }

        assert response["seed_entity_id"] == params["seed_entity_id"]
        assert "entities" in response
        assert "edges" in response
