"""
Layer 3: Predictive (ML-Based) Risk Scoring.

Uses machine learning to predict fraud probability based on
graph structure, behavior patterns, and historical outcomes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np

from halo.graph.client import GraphClient


# Proxy labels - outcomes that correlate with fraud
PROXY_LABELS = {
    # Negative outcomes (proxy for fraud)
    "konkurs_within_24m": 0.6,      # went bankrupt quickly
    "tvangslikvidation": 0.8,       # forced liquidation
    "skatteverket_action": 0.9,     # tax authority action
    "ekobrottsmyndigheten": 1.0,    # economic crimes prosecution
    "sanctions_hit": 1.0,           # appeared on sanctions list

    # Survival signals (proxy for legitimate)
    "active_5y_with_employees": -0.3,
    "filed_arsredovisning_3_consecutive": -0.2,
}


# Leading indicators - signals that precede fraud
CONSTRUCTION_SIGNALS = {
    # Formation patterns
    "rapid_formations": "Multiple companies formed in short window",
    "nominee_director_added": "Known nominee or unusual director portfolio",
    "virtual_address": "Registered at known virtual office",
    "minimal_capital": "Minimum required share capital only",
    "generic_sni": "Vague industry classification (holding, consulting)",

    # Structural patterns
    "ownership_layering": "Ownership moved through multiple entities",
    "cross_border_parent": "Foreign parent company added",
    "signatory_change": "Signing rights modified",

    # Activity patterns
    "no_arsredovisning": "Annual report not filed on time",
    "no_employees_with_revenue": "Revenue but zero employees",
    "address_change": "Registered address changed",
}


@dataclass
class FraudPrediction:
    """Prediction of fraud probability for an entity."""
    entity_id: str
    entity_type: str
    risk_level: str  # low, medium, high, critical
    probability: float  # 0-1
    confidence: float  # model confidence
    rationale: str
    construction_signals: list[str] = field(default_factory=list)
    top_features: list[dict] = field(default_factory=list)
    recommended_action: str = "routine_monitoring"
    predicted_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "risk_level": self.risk_level,
            "probability": self.probability,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "construction_signals": self.construction_signals,
            "top_features": self.top_features,
            "recommended_action": self.recommended_action,
            "predicted_at": self.predicted_at.isoformat(),
        }


def extract_graph_features(
    graph_data: dict,
    entity_id: str,
    neighbors: list[dict]
) -> dict[str, float]:
    """
    Extract ML features from graph position and behavior.

    Args:
        graph_data: Entity's node data from graph
        entity_id: Entity ID
        neighbors: List of neighboring nodes

    Returns:
        Feature dictionary
    """
    features = {
        # Structural features
        "degree_in": 0.0,
        "degree_out": 0.0,
        "betweenness_centrality": 0.0,
        "clustering_coefficient": 0.0,
        "pagerank": 0.0,

        # Neighborhood features
        "avg_neighbor_risk": 0.0,
        "pct_neighbors_flagged": 0.0,
        "max_neighbor_shell_score": 0.0,

        # Temporal features
        "edge_creation_velocity_90d": 0.0,
        "edge_deletion_velocity_90d": 0.0,
        "network_age_days": 0.0,

        # Pattern match features
        "matches_registration_mill": 0.0,
        "matches_phoenix": 0.0,
        "ownership_depth": 0.0,

        # Cross-entity features
        "address_company_count": 0.0,
        "director_portfolio_size": 0.0,
        "shared_director_avg_risk": 0.0,
    }

    # Extract from network metrics if available
    network_metrics = graph_data.get("network_metrics", {})
    features["betweenness_centrality"] = network_metrics.get("betweenness", 0.0)
    features["clustering_coefficient"] = network_metrics.get("clustering", 0.0)
    features["pagerank"] = network_metrics.get("pagerank", 0.0)

    # Count edges
    in_edges = 0
    out_edges = 0
    for neighbor in neighbors:
        edge = neighbor.get("edge", {})
        if edge.get("from_id") == entity_id:
            out_edges += 1
        else:
            in_edges += 1

    features["degree_in"] = float(in_edges)
    features["degree_out"] = float(out_edges)

    # Neighbor analysis
    if neighbors:
        risk_scores = []
        flagged_count = 0
        shell_scores = []

        for neighbor in neighbors:
            node = neighbor.get("m", {})
            risk = node.get("risk_score", 0.0)
            risk_scores.append(risk)

            if node.get("flags"):
                flagged_count += 1

            shell = node.get("shell_score", 0.0)
            shell_scores.append(shell)

        features["avg_neighbor_risk"] = float(np.mean(risk_scores)) if risk_scores else 0.0
        features["pct_neighbors_flagged"] = flagged_count / len(neighbors)
        features["max_neighbor_shell_score"] = float(max(shell_scores)) if shell_scores else 0.0

    return features


def propagate_risk(
    nodes: dict[str, dict],
    edges: list[dict],
    iterations: int = 10,
    damping: float = 0.85
) -> dict[str, float]:
    """
    Propagate risk through network (similar to PageRank).

    If your neighbors are risky, you become riskier.

    Args:
        nodes: Dict mapping node_id to node data
        edges: List of edge dicts with from/to
        iterations: Number of propagation iterations
        damping: Damping factor (like PageRank)

    Returns:
        Dict mapping node_id to propagated risk score
    """
    # Build adjacency
    neighbors: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        from_id = edge.get("from")
        to_id = edge.get("to")
        if from_id in neighbors and to_id:
            neighbors[from_id].append(to_id)
        if to_id in neighbors and from_id:
            neighbors[to_id].append(from_id)

    # Initialize with intrinsic risk scores
    risk = {
        node_id: node.get("risk_score", 0.0)
        for node_id, node in nodes.items()
    }
    intrinsic = dict(risk)

    for _ in range(iterations):
        new_risk = {}
        for node_id in nodes:
            node_neighbors = neighbors.get(node_id, [])

            if node_neighbors:
                neighbor_risk = sum(risk.get(n, 0.0) for n in node_neighbors)
                new_risk[node_id] = (
                    (1 - damping) * intrinsic.get(node_id, 0.0) +
                    damping * (neighbor_risk / len(node_neighbors))
                )
            else:
                new_risk[node_id] = intrinsic.get(node_id, 0.0)

        risk = new_risk

    return risk


class RiskPredictor:
    """
    ML-based risk prediction for entities.

    Key insight: fraud networks have a CONSTRUCTION phase before
    OPERATION phase. If we detect construction, we're ahead of the fraud.
    """

    def __init__(self, graph_client: Optional[GraphClient] = None):
        self.graph = graph_client
        self.model = None  # Would be a trained sklearn/pytorch model

    async def predict(self, entity_id: str) -> FraudPrediction:
        """
        Predict if entity is building fraud infrastructure.
        """
        # Get entity data
        entity_data = await self._get_entity_data(entity_id)
        entity_type = entity_data.get("_type", "Company")

        # Check construction signals
        construction_score = 0
        matched_signals = []

        for signal_id, description in CONSTRUCTION_SIGNALS.items():
            if await self._has_signal(entity_id, signal_id, entity_data):
                construction_score += 1
                matched_signals.append(description)

        # Check if already in operation (fraud happening)
        operation_indicators = ["skatteverket_action", "debt_registered", "konkurs_filed"]
        operation_score = 0
        for outcome in operation_indicators:
            if await self._has_outcome(entity_id, outcome):
                operation_score += 1

        # Calculate probability
        total_signals = len(CONSTRUCTION_SIGNALS)
        probability = construction_score / total_signals

        # Determine risk level and action
        if construction_score >= 4 and operation_score == 0:
            risk_level = "critical"
            rationale = "Heavy infrastructure building pattern detected, no operation yet - likely preparing for fraud"
            action = "immediate_investigation"
        elif construction_score >= 3 and operation_score == 0:
            risk_level = "high"
            rationale = "Infrastructure building pattern detected, no operation yet"
            action = "monitor_closely"
        elif construction_score >= 2:
            risk_level = "medium"
            rationale = "Some concerning patterns detected"
            action = "flag_for_review"
        else:
            risk_level = "low"
            rationale = "No significant fraud indicators"
            action = "routine_monitoring"

        # Extract features for explainability
        neighbors = await self._get_neighbors(entity_id)
        features = extract_graph_features(entity_data, entity_id, neighbors)

        # Top contributing features
        top_features = sorted(
            [{"name": k, "value": v} for k, v in features.items() if v > 0],
            key=lambda x: x["value"],
            reverse=True
        )[:5]

        return FraudPrediction(
            entity_id=entity_id,
            entity_type=entity_type,
            risk_level=risk_level,
            probability=probability,
            confidence=1.0 - (0.1 * (total_signals - construction_score)),
            rationale=rationale,
            construction_signals=matched_signals,
            top_features=top_features,
            recommended_action=action
        )

    async def predict_batch(self, entity_ids: list[str]) -> list[FraudPrediction]:
        """Predict risk for multiple entities."""
        predictions = []
        for entity_id in entity_ids:
            prediction = await self.predict(entity_id)
            predictions.append(prediction)
        return predictions

    async def explain_prediction(
        self,
        entity_id: str,
        prediction: FraudPrediction
    ) -> dict:
        """
        Generate human-readable explanation of prediction.
        """
        explanation = {
            "entity_id": entity_id,
            "risk_level": prediction.risk_level,
            "summary": prediction.rationale,
            "signals_detected": [],
            "network_context": {},
            "recommended_actions": [],
        }

        # Explain each signal
        for signal in prediction.construction_signals:
            explanation["signals_detected"].append({
                "signal": signal,
                "importance": "high" if "nominee" in signal.lower() or "layering" in signal.lower() else "medium"
            })

        # Network context
        if prediction.top_features:
            explanation["network_context"] = {
                "high_risk_neighbors": prediction.top_features[0]["value"] > 0.5 if prediction.top_features else False,
                "unusual_structure": any(f["name"] == "ownership_depth" and f["value"] > 2 for f in prediction.top_features)
            }

        # Recommended actions based on risk level
        actions_map = {
            "critical": [
                "Escalate to compliance team immediately",
                "Document all network connections",
                "Prepare SAR if warranted",
                "Consider enhanced monitoring of related entities"
            ],
            "high": [
                "Assign to investigator for review",
                "Expand network analysis",
                "Check for additional pattern matches"
            ],
            "medium": [
                "Add to watchlist",
                "Schedule periodic review",
                "Monitor for changes"
            ],
            "low": [
                "Continue routine monitoring"
            ]
        }
        explanation["recommended_actions"] = actions_map.get(prediction.risk_level, [])

        return explanation

    async def _get_entity_data(self, entity_id: str) -> dict:
        """Get entity data from graph."""
        if self.graph:
            # Try company first
            data = await self.graph.get_company(entity_id)
            if data:
                return data
            # Then person
            data = await self.graph.get_person(entity_id)
            if data:
                return data
        return {"id": entity_id}

    async def _get_neighbors(self, entity_id: str) -> list[dict]:
        """Get neighbor nodes."""
        if self.graph:
            return await self.graph.backend.get_neighbors(entity_id)
        return []

    async def _has_signal(
        self,
        entity_id: str,
        signal_id: str,
        entity_data: dict
    ) -> bool:
        """Check if entity has a construction signal."""
        if signal_id == "virtual_address":
            addresses = entity_data.get("addresses", [])
            return any(a.get("type") == "virtual" for a in addresses)

        elif signal_id == "generic_sni":
            sni_codes = entity_data.get("sni_codes", [])
            generic = {"70", "82", "64", "66"}
            return any(str(s.get("code", ""))[:2] in generic for s in sni_codes)

        elif signal_id == "minimal_capital":
            # AB minimum is 25,000 SEK
            capital = entity_data.get("share_capital", 0)
            legal_form = entity_data.get("legal_form", "")
            return legal_form == "AB" and capital <= 25000

        elif signal_id == "no_arsredovisning":
            # Check if annual report is overdue
            return entity_data.get("arsredovisning_status") == "overdue"

        elif signal_id == "no_employees_with_revenue":
            employees = entity_data.get("employees") or {}
            revenue = entity_data.get("revenue") or {}
            return (
                employees.get("count", 0) == 0 and
                revenue.get("amount", 0) > 0
            )

        elif signal_id == "nominee_director_added":
            # Would check against known nominee database
            return False

        elif signal_id == "ownership_layering":
            # Check ownership depth
            if self.graph:
                chain = await self.graph.get_ownership_chain(entity_id)
                return len(chain) >= 3
            return False

        elif signal_id == "cross_border_parent":
            # Check for foreign owners
            owners = entity_data.get("owners", [])
            return any(o.get("jurisdiction") != "SE" for o in owners)

        elif signal_id == "rapid_formations":
            # Check if same person formed multiple companies recently
            return False  # Would need formation agent data

        elif signal_id == "signatory_change":
            # Check recent signatory changes
            return entity_data.get("recent_signatory_change", False)

        elif signal_id == "address_change":
            # Check recent address changes
            return entity_data.get("recent_address_change", False)

        return False

    async def _has_outcome(self, entity_id: str, outcome: str) -> bool:
        """Check if entity has a known outcome (for model training)."""
        if self.graph:
            entity = await self._get_entity_data(entity_id)
            status = entity.get("status", {}).get("code", "")

            if outcome == "konkurs_filed":
                return status in ("konkurs", "bankrupt")
            elif outcome == "skatteverket_action":
                return entity.get("skatteverket_action", False)
            elif outcome == "debt_registered":
                return entity.get("has_registered_debt", False)

        return False


class NetworkRiskAnalyzer:
    """
    Analyze risk propagation through networks.
    """

    def __init__(self, graph_client: GraphClient):
        self.graph = graph_client

    async def analyze_network_risk(
        self,
        seed_entity: str,
        hops: int = 2
    ) -> dict:
        """
        Analyze risk in a network starting from seed entity.
        """
        # Expand network
        network = await self.graph.expand_network([seed_entity], hops=hops)
        nodes = network.get("nodes", {})
        edges = network.get("edges", [])

        if not nodes:
            return {
                "seed_entity": seed_entity,
                "network_size": 0,
                "risk_scores": {},
                "high_risk_entities": [],
                "risk_propagation": {}
            }

        # Propagate risk
        risk_scores = propagate_risk(nodes, edges)

        # Find high risk entities
        high_risk = [
            {"entity_id": eid, "risk_score": score}
            for eid, score in risk_scores.items()
            if score > 0.5
        ]
        high_risk.sort(key=lambda x: x["risk_score"], reverse=True)

        # Calculate risk contagion
        seed_initial_risk = nodes.get(seed_entity, {}).get("risk_score", 0.0)
        seed_final_risk = risk_scores.get(seed_entity, 0.0)

        return {
            "seed_entity": seed_entity,
            "network_size": len(nodes),
            "risk_scores": risk_scores,
            "high_risk_entities": high_risk[:10],
            "risk_propagation": {
                "seed_initial_risk": seed_initial_risk,
                "seed_final_risk": seed_final_risk,
                "risk_increase": seed_final_risk - seed_initial_risk,
                "avg_network_risk": float(np.mean(list(risk_scores.values())))
            }
        }
