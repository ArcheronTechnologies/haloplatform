"""
Tests for the predictive module (Layer 3).
"""

import pytest
import numpy as np
from datetime import datetime

from halo.intelligence.predictive import (
    RiskPredictor,
    FraudPrediction,
    NetworkRiskAnalyzer,
    extract_graph_features,
    propagate_risk,
    PROXY_LABELS,
    CONSTRUCTION_SIGNALS,
)
from halo.graph.client import GraphClient


class TestProxyLabels:
    """Tests for proxy labels."""

    def test_proxy_labels_defined(self):
        """Test proxy labels are defined."""
        assert len(PROXY_LABELS) >= 5

        # Negative outcomes should be positive weights
        assert PROXY_LABELS["konkurs_within_24m"] > 0
        assert PROXY_LABELS["ekobrottsmyndigheten"] > 0

        # Survival signals should be negative
        assert PROXY_LABELS["active_5y_with_employees"] < 0


class TestConstructionSignals:
    """Tests for construction signals."""

    def test_construction_signals_defined(self):
        """Test construction signals are defined."""
        assert len(CONSTRUCTION_SIGNALS) >= 5

        # Check key signals exist
        assert "virtual_address" in CONSTRUCTION_SIGNALS
        assert "generic_sni" in CONSTRUCTION_SIGNALS
        assert "ownership_layering" in CONSTRUCTION_SIGNALS
        assert "no_arsredovisning" in CONSTRUCTION_SIGNALS


class TestFraudPrediction:
    """Tests for FraudPrediction."""

    def test_fraud_prediction_creation(self):
        """Test fraud prediction creation."""
        prediction = FraudPrediction(
            entity_id="company-123",
            entity_type="Company",
            risk_level="high",
            probability=0.75,
            confidence=0.85,
            rationale="High fraud indicators detected",
            construction_signals=["virtual_address", "generic_sni"],
            recommended_action="monitor_closely"
        )

        assert prediction.entity_id == "company-123"
        assert prediction.risk_level == "high"
        assert prediction.probability == 0.75
        assert len(prediction.construction_signals) == 2
        assert prediction.predicted_at is not None

    def test_fraud_prediction_to_dict(self):
        """Test fraud prediction serialization."""
        prediction = FraudPrediction(
            entity_id="company-123",
            entity_type="Company",
            risk_level="medium",
            probability=0.5,
            confidence=0.7,
            rationale="Some indicators"
        )

        data = prediction.to_dict()

        assert data["entity_id"] == "company-123"
        assert data["risk_level"] == "medium"
        assert "predicted_at" in data


class TestExtractGraphFeatures:
    """Tests for feature extraction."""

    def test_extract_features_empty(self):
        """Test feature extraction with empty data."""
        features = extract_graph_features({}, "entity-1", [])

        assert features["degree_in"] == 0.0
        assert features["degree_out"] == 0.0
        assert features["avg_neighbor_risk"] == 0.0

    def test_extract_features_with_network_metrics(self):
        """Test feature extraction with network metrics."""
        graph_data = {
            "network_metrics": {
                "betweenness": 0.5,
                "clustering": 0.3,
                "pagerank": 0.02
            }
        }

        features = extract_graph_features(graph_data, "entity-1", [])

        assert features["betweenness_centrality"] == 0.5
        assert features["clustering_coefficient"] == 0.3
        assert features["pagerank"] == 0.02

    def test_extract_features_with_neighbors(self):
        """Test feature extraction with neighbors."""
        graph_data = {}
        neighbors = [
            {
                "m": {"id": "n1", "risk_score": 0.8, "flags": ["flag1"], "shell_score": 0.7},
                "edge": {"from_id": "n1", "to_id": "entity-1"}
            },
            {
                "m": {"id": "n2", "risk_score": 0.2, "flags": [], "shell_score": 0.1},
                "edge": {"from_id": "entity-1", "to_id": "n2"}
            }
        ]

        features = extract_graph_features(graph_data, "entity-1", neighbors)

        assert features["degree_in"] == 1.0
        assert features["degree_out"] == 1.0
        assert features["avg_neighbor_risk"] == 0.5
        assert features["pct_neighbors_flagged"] == 0.5
        assert features["max_neighbor_shell_score"] == 0.7


class TestPropagateRisk:
    """Tests for risk propagation."""

    def test_propagate_risk_empty(self):
        """Test risk propagation with empty network."""
        risk = propagate_risk({}, [])
        assert risk == {}

    def test_propagate_risk_single_node(self):
        """Test risk propagation with single node."""
        nodes = {"node-1": {"risk_score": 0.5}}
        edges = []

        risk = propagate_risk(nodes, edges)

        assert "node-1" in risk
        assert risk["node-1"] == 0.5  # No propagation

    def test_propagate_risk_connected_nodes(self):
        """Test risk propagation through connected nodes."""
        nodes = {
            "high-risk": {"risk_score": 0.9},
            "medium-risk": {"risk_score": 0.5},
            "low-risk": {"risk_score": 0.1}
        }
        edges = [
            {"from": "high-risk", "to": "medium-risk"},
            {"from": "medium-risk", "to": "low-risk"}
        ]

        risk = propagate_risk(nodes, edges, iterations=10)

        # All nodes should have propagated risk values
        assert "high-risk" in risk
        assert "medium-risk" in risk
        assert "low-risk" in risk
        # Risk values should be bounded
        assert all(0 <= r <= 1 for r in risk.values())

    def test_propagate_risk_cycle(self):
        """Test risk propagation with cycle."""
        nodes = {
            "a": {"risk_score": 0.9},
            "b": {"risk_score": 0.1},
            "c": {"risk_score": 0.1}
        }
        edges = [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c"},
            {"from": "c", "to": "a"}  # Cycle
        ]

        risk = propagate_risk(nodes, edges, iterations=10)

        # All should converge to similar values due to cycle
        assert all(0 < risk[n] < 1 for n in nodes)


class TestRiskPredictor:
    """Tests for RiskPredictor."""

    @pytest.fixture
    def predictor(self):
        """Create a risk predictor."""
        return RiskPredictor()

    @pytest.fixture
    def predictor_with_graph(self):
        """Create a risk predictor with graph."""
        client = GraphClient()
        return RiskPredictor(graph_client=client)

    def test_predictor_creation(self, predictor):
        """Test predictor creation."""
        assert predictor.model is None  # No trained model yet

    @pytest.mark.asyncio
    async def test_predict_no_graph(self, predictor):
        """Test prediction without graph data."""
        prediction = await predictor.predict("company-123")

        assert prediction.entity_id == "company-123"
        assert prediction.entity_type in ["Company", "Person", "Unknown"]
        assert prediction.risk_level in ["low", "medium", "high", "critical"]
        assert 0 <= prediction.probability <= 1
        assert prediction.recommended_action is not None

    @pytest.mark.asyncio
    async def test_predict_batch(self, predictor):
        """Test batch prediction."""
        predictions = await predictor.predict_batch(["c1", "c2", "c3"])

        assert len(predictions) == 3
        for pred in predictions:
            assert pred.entity_id in ["c1", "c2", "c3"]
            assert pred.risk_level in ["low", "medium", "high", "critical"]

    @pytest.mark.asyncio
    async def test_explain_prediction(self, predictor):
        """Test prediction explanation."""
        prediction = FraudPrediction(
            entity_id="company-123",
            entity_type="Company",
            risk_level="high",
            probability=0.8,
            confidence=0.9,
            rationale="High risk indicators",
            construction_signals=["virtual_address", "generic_sni"],
            top_features=[{"name": "network_risk", "value": 0.8}]
        )

        explanation = await predictor.explain_prediction("company-123", prediction)

        assert "entity_id" in explanation
        assert "summary" in explanation
        assert "signals_detected" in explanation
        assert "recommended_actions" in explanation
        assert len(explanation["recommended_actions"]) > 0


class TestNetworkRiskAnalyzer:
    """Tests for NetworkRiskAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create a network risk analyzer."""
        client = GraphClient()
        return NetworkRiskAnalyzer(client)

    @pytest.mark.asyncio
    async def test_analyze_network_risk(self, analyzer):
        """Test network risk analysis."""
        async with analyzer.graph:
            # Create a simple network
            from halo.graph.schema import Company
            from halo.graph.edges import OwnsEdge

            for i in range(3):
                company = Company(id=f"company-{i}", risk_score=0.3 * i)
                await analyzer.graph.add_company(company)

            await analyzer.graph.add_ownership(OwnsEdge(
                from_id="company-0", from_type="company", to_id="company-1"
            ))
            await analyzer.graph.add_ownership(OwnsEdge(
                from_id="company-1", from_type="company", to_id="company-2"
            ))

            result = await analyzer.analyze_network_risk("company-0", hops=2)

            assert result["seed_entity"] == "company-0"
            assert result["network_size"] >= 2
            assert "risk_scores" in result
            assert "risk_propagation" in result

    @pytest.mark.asyncio
    async def test_analyze_empty_network(self, analyzer):
        """Test analysis of empty/nonexistent network."""
        async with analyzer.graph:
            result = await analyzer.analyze_network_risk("nonexistent", hops=2)

            assert result["network_size"] == 0
            assert result["high_risk_entities"] == []
