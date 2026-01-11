"""
Konkurs (Bankruptcy) Prediction.

Predict bankruptcy probability from network structure + behavior.
Uses network contagion, director signals, and company trajectory.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from halo.graph.client import GraphClient


@dataclass
class KonkursPrediction:
    """Bankruptcy prediction result."""
    company_id: str
    konkurs_probability: float  # 0-1
    horizon_months: int  # prediction horizon
    risk_level: str  # low, medium, high, critical
    confidence: float  # model confidence

    # Contributing factors
    top_risk_factors: list[dict] = field(default_factory=list)
    network_contagion_risk: float = 0.0
    director_risk_score: float = 0.0
    financial_health_score: float = 0.0

    # Signals
    distress_signals: list[str] = field(default_factory=list)
    survival_signals: list[str] = field(default_factory=list)

    predicted_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "company_id": self.company_id,
            "konkurs_probability": self.konkurs_probability,
            "horizon_months": self.horizon_months,
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "top_risk_factors": self.top_risk_factors,
            "network_contagion_risk": self.network_contagion_risk,
            "director_risk_score": self.director_risk_score,
            "financial_health_score": self.financial_health_score,
            "distress_signals": self.distress_signals,
            "survival_signals": self.survival_signals,
            "predicted_at": self.predicted_at.isoformat(),
        }


# Feature definitions for konkurs prediction
KONKURS_FEATURES = {
    # Network contagion features
    "network": [
        "pct_counterparties_in_distress",
        "avg_counterparty_risk_score",
        "exposure_to_failing_companies",
        "network_density",
        "isolation_score",
    ],

    # Director signals
    "director": [
        "director_previous_konkurser",
        "director_portfolio_risk",
        "recent_director_changes",
        "director_age",
        "director_other_failures",
    ],

    # Company trajectory
    "trajectory": [
        "employee_trend_12m",
        "revenue_trend_12m",
        "arsredovisning_delays",
        "address_changes_12m",
        "sni_changes_12m",
        "capital_changes_12m",
    ],

    # Industry factors
    "industry": [
        "industry_failure_rate",
        "industry_trend",
        "industry_competition_index",
    ],

    # Age/lifecycle
    "lifecycle": [
        "company_age_months",
        "months_since_last_activity",
        "filing_regularity_score",
    ],

    # Financial indicators (when available)
    "financial": [
        "debt_to_equity",
        "current_ratio",
        "quick_ratio",
        "revenue_per_employee",
        "profit_margin",
    ],
}


class KonkursPredictor:
    """
    Predict bankruptcy probability from network structure and behavior.

    Uses multiple signal categories:
    - Network contagion (if neighbors are failing, risk increases)
    - Director history (directors with previous bankruptcies)
    - Company trajectory (declining metrics)
    - Industry factors
    """

    def __init__(self, graph_client: Optional[GraphClient] = None):
        self.graph = graph_client
        self.model = None  # Would be a trained ML model

    async def predict(
        self,
        company_id: str,
        horizon_months: int = 12
    ) -> KonkursPrediction:
        """
        Predict bankruptcy probability for a company.

        Args:
            company_id: Company to predict for
            horizon_months: Prediction horizon (default 12 months)
        """
        # Get company data
        company = await self._get_company(company_id)
        if not company:
            return KonkursPrediction(
                company_id=company_id,
                konkurs_probability=0.0,
                horizon_months=horizon_months,
                risk_level="unknown",
                confidence=0.0,
                distress_signals=["Company not found"]
            )

        # Extract features
        features = await self._extract_features(company_id, company)

        # Calculate component scores
        network_score = self._calculate_network_contagion(features)
        director_score = self._calculate_director_risk(features)
        trajectory_score = self._calculate_trajectory_risk(features)
        financial_score = self._calculate_financial_health(features)

        # Combine into overall probability
        # Weighted combination (would be learned in production)
        probability = (
            network_score * 0.25 +
            director_score * 0.25 +
            trajectory_score * 0.30 +
            (1 - financial_score) * 0.20  # Invert health to risk
        )
        probability = min(max(probability, 0.0), 1.0)

        # Identify distress and survival signals
        distress_signals = self._identify_distress_signals(features, company)
        survival_signals = self._identify_survival_signals(features, company)

        # Get top risk factors
        risk_factors = self._get_top_risk_factors(features)

        # Determine risk level
        if probability > 0.7:
            risk_level = "critical"
        elif probability > 0.5:
            risk_level = "high"
        elif probability > 0.3:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Calculate confidence (based on data availability)
        data_completeness = self._calculate_data_completeness(features)
        confidence = min(data_completeness, 0.95)

        return KonkursPrediction(
            company_id=company_id,
            konkurs_probability=probability,
            horizon_months=horizon_months,
            risk_level=risk_level,
            confidence=confidence,
            top_risk_factors=risk_factors,
            network_contagion_risk=network_score,
            director_risk_score=director_score,
            financial_health_score=financial_score,
            distress_signals=distress_signals,
            survival_signals=survival_signals
        )

    async def predict_batch(
        self,
        company_ids: list[str],
        horizon_months: int = 12
    ) -> list[KonkursPrediction]:
        """Predict for multiple companies."""
        predictions = []
        for company_id in company_ids:
            pred = await self.predict(company_id, horizon_months)
            predictions.append(pred)
        return predictions

    async def find_at_risk_companies(
        self,
        min_probability: float = 0.5,
        limit: int = 100
    ) -> list[KonkursPrediction]:
        """
        Find companies at risk of bankruptcy.
        """
        # Get active companies
        company_ids = await self._get_active_companies(limit=limit * 2)

        predictions = []
        for company_id in company_ids:
            pred = await self.predict(company_id)
            if pred.konkurs_probability >= min_probability:
                predictions.append(pred)

            if len(predictions) >= limit:
                break

        # Sort by probability
        predictions.sort(key=lambda p: p.konkurs_probability, reverse=True)
        return predictions[:limit]

    async def analyze_contagion_risk(self, company_id: str) -> dict:
        """
        Analyze how bankruptcy of this company would affect its network.
        """
        if not self.graph:
            return {"contagion_risk": 0.0, "affected_entities": []}

        # Expand network
        network = await self.graph.expand_network([company_id], hops=2)
        nodes = network.get("nodes", {})
        edges = network.get("edges", [])

        if not nodes:
            return {"contagion_risk": 0.0, "affected_entities": []}

        affected = []

        for node_id, node_data in nodes.items():
            if node_id == company_id:
                continue

            # Calculate exposure
            exposure = self._calculate_exposure(company_id, node_id, edges)

            if exposure > 0:
                # Get current health
                current_pred = await self.predict(node_id)

                # Estimate impact
                impact = exposure * 0.3  # Simplified impact model

                affected.append({
                    "entity_id": node_id,
                    "entity_type": node_data.get("_type", "Unknown"),
                    "name": node_data.get("display_name", "Unknown"),
                    "exposure": exposure,
                    "current_risk": current_pred.konkurs_probability,
                    "estimated_impact": impact,
                    "post_event_risk": min(current_pred.konkurs_probability + impact, 1.0)
                })

        # Sort by impact
        affected.sort(key=lambda x: x["estimated_impact"], reverse=True)

        # Calculate overall contagion risk
        total_impact = sum(a["estimated_impact"] for a in affected)
        contagion_risk = min(total_impact / len(affected), 1.0) if affected else 0.0

        return {
            "source_company": company_id,
            "contagion_risk": contagion_risk,
            "affected_entities": affected[:20],
            "total_affected": len(affected),
            "high_risk_count": sum(1 for a in affected if a["post_event_risk"] > 0.5)
        }

    async def _extract_features(self, company_id: str, company: dict) -> dict:
        """Extract all features for prediction."""
        features = {}

        # Network features
        if self.graph:
            neighbors = await self.graph.backend.get_neighbors(company_id)

            distress_count = 0
            risk_scores = []

            for neighbor in neighbors:
                node = neighbor.get("m", {})
                if node.get("status", {}).get("code", "").lower() in ("konkurs", "distressed"):
                    distress_count += 1
                risk_scores.append(node.get("risk_score", 0.0))

            features["pct_counterparties_in_distress"] = (
                distress_count / len(neighbors) if neighbors else 0.0
            )
            features["avg_counterparty_risk_score"] = (
                float(np.mean(risk_scores)) if risk_scores else 0.0
            )
            features["network_size"] = len(neighbors)
        else:
            features["pct_counterparties_in_distress"] = 0.0
            features["avg_counterparty_risk_score"] = 0.0
            features["network_size"] = 0

        # Director features
        directors = company.get("directors", [])
        features["director_count"] = len(directors)
        features["director_previous_konkurser"] = await self._count_director_failures(directors)
        features["recent_director_changes"] = company.get("director_changes_12m", 0)

        # Trajectory features
        features["employee_trend_12m"] = self._calculate_trend(
            company.get("employee_history", [])
        )
        features["revenue_trend_12m"] = self._calculate_trend(
            company.get("revenue_history", [])
        )
        features["arsredovisning_delays"] = company.get("arsredovisning_delays", 0)
        features["address_changes_12m"] = company.get("address_changes_12m", 0)

        # Lifecycle features
        formation_date = company.get("formation", {}).get("date")
        if formation_date:
            try:
                if isinstance(formation_date, str):
                    from datetime import date
                    formation_date = date.fromisoformat(formation_date)
                age_days = (datetime.utcnow().date() - formation_date).days
                features["company_age_months"] = age_days / 30
            except (ValueError, TypeError):
                features["company_age_months"] = 0
        else:
            features["company_age_months"] = 0

        # Financial features (if available)
        financials = company.get("financials", {})
        features["debt_to_equity"] = financials.get("debt_to_equity", 0.5)
        features["current_ratio"] = financials.get("current_ratio", 1.0)
        features["profit_margin"] = financials.get("profit_margin", 0.0)

        # Industry features
        sni = company.get("sni_codes", [{}])[0].get("code", "")[:2] if company.get("sni_codes") else ""
        features["industry_failure_rate"] = self._get_industry_failure_rate(sni)

        return features

    def _calculate_network_contagion(self, features: dict) -> float:
        """Calculate network contagion risk score."""
        distress_pct = features.get("pct_counterparties_in_distress", 0.0)
        avg_risk = features.get("avg_counterparty_risk_score", 0.0)

        # Combine into contagion score
        return (distress_pct * 0.6 + avg_risk * 0.4)

    def _calculate_director_risk(self, features: dict) -> float:
        """Calculate director-related risk."""
        failures = features.get("director_previous_konkurser", 0)
        changes = features.get("recent_director_changes", 0)

        # Directors with previous failures increase risk
        failure_risk = min(failures * 0.15, 0.6)

        # High turnover is a warning sign
        turnover_risk = min(changes * 0.1, 0.3)

        return failure_risk + turnover_risk

    def _calculate_trajectory_risk(self, features: dict) -> float:
        """Calculate risk from company trajectory."""
        emp_trend = features.get("employee_trend_12m", 0.0)
        rev_trend = features.get("revenue_trend_12m", 0.0)
        delays = features.get("arsredovisning_delays", 0)
        addr_changes = features.get("address_changes_12m", 0)

        # Declining trends increase risk
        trend_risk = 0.0
        if emp_trend < -0.2:  # >20% decline
            trend_risk += 0.2
        if rev_trend < -0.2:
            trend_risk += 0.2

        # Filing delays are a warning
        delay_risk = min(delays * 0.1, 0.3)

        # Address instability
        instability_risk = min(addr_changes * 0.05, 0.2)

        return min(trend_risk + delay_risk + instability_risk, 1.0)

    def _calculate_financial_health(self, features: dict) -> float:
        """Calculate financial health score (higher = healthier)."""
        debt_equity = features.get("debt_to_equity", 0.5)
        current_ratio = features.get("current_ratio", 1.0)
        margin = features.get("profit_margin", 0.0)

        # Score each metric
        de_score = max(0, 1 - debt_equity) if debt_equity < 2 else 0.0
        cr_score = min(current_ratio / 2, 1.0)  # 2.0 is healthy
        margin_score = 0.5 + margin if margin > -0.5 else 0.0

        return (de_score + cr_score + margin_score) / 3

    def _identify_distress_signals(self, features: dict, company: dict) -> list[str]:
        """Identify distress warning signals."""
        signals = []

        if features.get("pct_counterparties_in_distress", 0) > 0.2:
            signals.append("High exposure to distressed counterparties")

        if features.get("director_previous_konkurser", 0) > 0:
            signals.append("Directors with previous bankruptcy history")

        if features.get("employee_trend_12m", 0) < -0.3:
            signals.append("Significant employee decline (>30%)")

        if features.get("revenue_trend_12m", 0) < -0.3:
            signals.append("Significant revenue decline (>30%)")

        if features.get("arsredovisning_delays", 0) > 0:
            signals.append("Late annual report filings")

        if features.get("recent_director_changes", 0) > 2:
            signals.append("High director turnover")

        if features.get("company_age_months", 100) < 24:
            signals.append("Young company (<2 years)")

        status = company.get("status", {}).get("code", "")
        if status.lower() in ("liquidation", "likvidation"):
            signals.append("Currently in liquidation")

        return signals

    def _identify_survival_signals(self, features: dict, company: dict) -> list[str]:
        """Identify positive survival signals."""
        signals = []

        if features.get("company_age_months", 0) > 60:
            signals.append("Established company (>5 years)")

        if features.get("employee_trend_12m", 0) > 0.1:
            signals.append("Growing workforce")

        if features.get("revenue_trend_12m", 0) > 0.1:
            signals.append("Growing revenue")

        if features.get("pct_counterparties_in_distress", 1) < 0.05:
            signals.append("Healthy network - few distressed counterparties")

        if features.get("current_ratio", 0) > 1.5:
            signals.append("Strong liquidity position")

        if features.get("arsredovisning_delays", 1) == 0:
            signals.append("Consistent filing compliance")

        return signals

    def _get_top_risk_factors(self, features: dict) -> list[dict]:
        """Get top contributing risk factors."""
        factors = []

        # Check each feature category
        if features.get("pct_counterparties_in_distress", 0) > 0.1:
            factors.append({
                "category": "network",
                "factor": "Counterparty distress",
                "value": features["pct_counterparties_in_distress"],
                "importance": 0.25
            })

        if features.get("director_previous_konkurser", 0) > 0:
            factors.append({
                "category": "director",
                "factor": "Director bankruptcy history",
                "value": features["director_previous_konkurser"],
                "importance": 0.20
            })

        if features.get("employee_trend_12m", 0) < -0.2:
            factors.append({
                "category": "trajectory",
                "factor": "Employee decline",
                "value": features["employee_trend_12m"],
                "importance": 0.15
            })

        # Sort by importance
        factors.sort(key=lambda x: x["importance"], reverse=True)
        return factors[:5]

    def _calculate_data_completeness(self, features: dict) -> float:
        """Calculate how complete the feature data is."""
        total_features = len(KONKURS_FEATURES["network"]) + \
                        len(KONKURS_FEATURES["director"]) + \
                        len(KONKURS_FEATURES["trajectory"])

        available = sum(1 for v in features.values() if v != 0 and v is not None)
        return min(available / total_features, 1.0)

    def _calculate_trend(self, history: list[dict]) -> float:
        """Calculate trend from historical data."""
        if not history or len(history) < 2:
            return 0.0

        # Sort by date
        history = sorted(history, key=lambda x: x.get("date", ""))

        # Get first and last values
        first = history[0].get("value", 0)
        last = history[-1].get("value", 0)

        if first == 0:
            return 0.0

        return (last - first) / first

    def _get_industry_failure_rate(self, sni_code: str) -> float:
        """Get historical failure rate for industry."""
        # Simplified - would use actual Swedish bankruptcy statistics
        high_risk_industries = {"55", "56", "47", "43"}  # Hospitality, retail, construction
        medium_risk_industries = {"70", "82", "64"}  # Holding, consulting, financial

        if sni_code in high_risk_industries:
            return 0.08  # 8% annual failure rate
        elif sni_code in medium_risk_industries:
            return 0.05
        else:
            return 0.03  # Average

    def _calculate_exposure(
        self,
        source_id: str,
        target_id: str,
        edges: list[dict]
    ) -> float:
        """Calculate exposure between two entities."""
        # Count direct connections
        direct_edges = sum(
            1 for e in edges
            if (e.get("from") == source_id and e.get("to") == target_id) or
               (e.get("from") == target_id and e.get("to") == source_id)
        )

        # Exposure based on connection strength
        return min(direct_edges * 0.2, 1.0)

    async def _count_director_failures(self, directors: list[dict]) -> int:
        """Count how many directors have previous bankruptcy involvement."""
        count = 0
        for director in directors:
            director_id = director.get("id")
            if director_id and self.graph:
                # Query for director's previous company bankruptcies
                # Simplified - would query graph
                pass
        return count

    async def _get_company(self, company_id: str) -> Optional[dict]:
        """Get company data."""
        if self.graph:
            return await self.graph.get_company(company_id)
        return None

    async def _get_active_companies(self, limit: int = 100) -> list[str]:
        """Get list of active company IDs."""
        if self.graph:
            try:
                query = """
                MATCH (c:Company)
                WHERE c.status.code IN ['active', 'aktiv']
                RETURN c.id as id
                LIMIT $limit
                """
                results = await self.graph.execute_cypher(query, {"limit": limit})
                return [r.get("id") for r in results if r.get("id")]
            except Exception:
                pass
        return []
