"""
Risk scoring for entities and transactions.

Provides multi-factor risk assessment for:
- Entities (persons, companies)
- Transactions
- Relationships

Risk factors based on Swedish/EU AML regulations and FATF guidance.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Overall risk level classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    PROHIBITED = "prohibited"


class RiskCategory(str, Enum):
    """Categories of risk factors."""

    GEOGRAPHIC = "geographic"
    CUSTOMER = "customer"
    PRODUCT = "product"
    CHANNEL = "channel"
    TRANSACTION = "transaction"
    BEHAVIORAL = "behavioral"
    RELATIONSHIP = "relationship"


@dataclass
class RiskFactor:
    """Individual risk factor contributing to overall score."""

    category: RiskCategory
    name: str
    description: str
    score: float  # 0.0 to 1.0
    weight: float = 1.0  # Importance multiplier

    # Source of the risk factor
    source: str = "system"
    detected_at: datetime = field(default_factory=datetime.utcnow)

    # Evidence
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "name": self.name,
            "description": self.description,
            "score": self.score,
            "weight": self.weight,
            "weighted_score": self.weighted_score,
            "source": self.source,
            "detected_at": self.detected_at.isoformat(),
            "evidence": self.evidence,
        }


@dataclass
class RiskScore:
    """Complete risk assessment result."""

    entity_id: Optional[UUID] = None
    transaction_id: Optional[UUID] = None

    # Overall score and level
    total_score: float = 0.0
    overall_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW

    # Contributing factors
    factors: list[RiskFactor] = field(default_factory=list)

    # Breakdown by category
    category_scores: dict[str, float] = field(default_factory=dict)
    factor_scores: dict[str, float] = field(default_factory=dict)

    # Metadata
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "1.0"

    # Recommendations
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "transaction_id": str(self.transaction_id) if self.transaction_id else None,
            "total_score": self.total_score,
            "overall_score": self.overall_score,
            "risk_level": self.risk_level.value,
            "factors": [f.to_dict() for f in self.factors],
            "category_scores": self.category_scores,
            "factor_scores": self.factor_scores,
            "calculated_at": self.calculated_at.isoformat(),
            "model_version": self.model_version,
            "recommendations": self.recommendations,
        }


@dataclass
class EntityForScoring:
    """Entity data structure for risk scoring."""

    id: UUID
    name: str
    entity_type: str
    jurisdiction: str = "SE"
    industry: Optional[str] = None
    customer_type: str = "standard"
    is_pep: bool = False
    beneficial_owners: list[dict] = field(default_factory=list)
    years_in_business: int = 0
    has_sanctions_exposure: bool = False
    transaction_volume_monthly: Decimal = Decimal("0")
    cash_transaction_ratio: float = 0.0
    high_risk_country_ratio: float = 0.0


@dataclass
class TransactionForScoring:
    """Transaction data structure for risk scoring."""

    id: UUID
    amount: Decimal
    currency: str
    timestamp: datetime
    transaction_type: str
    is_cash: bool = False
    counterparty_country: str = "SE"
    counterparty_risk_level: RiskLevel = RiskLevel.LOW
    is_round_amount: bool = False
    entity_risk_level: RiskLevel = RiskLevel.LOW


class EntityRiskScorer:
    """
    Risk scoring for entities (persons and companies).

    Factors considered:
    - Geographic risk (country of registration, operations)
    - Customer type (PEP, sanctioned, high-risk industry)
    - Ownership structure (complex, opaque)
    - Transaction patterns (volume, velocity, counterparties)
    - Relationship network (connections to high-risk entities)
    """

    # High-risk countries (simplified list, should use FATF greylist)
    HIGH_RISK_COUNTRIES = {
        "IR", "KP", "SY", "MM",  # FATF blacklist
        "PK", "NG", "YE", "HT",  # High risk
    }

    MEDIUM_RISK_COUNTRIES = {
        "AE", "PA", "VG", "KY",  # Tax havens / offshore
        "RU", "BY", "VE",  # Sanctions-related
    }

    # High-risk industries (SNI codes)
    HIGH_RISK_INDUSTRIES = {
        "64.19": "Other monetary intermediation",
        "64.30": "Trusts, funds and similar",
        "66.19": "Other financial service activities",
        "92.00": "Gambling and betting",
        "96.09": "Other personal service activities",
    }

    # Risk thresholds
    THRESHOLDS = {
        RiskLevel.LOW: 0.25,
        RiskLevel.MEDIUM: 0.50,
        RiskLevel.HIGH: 0.75,
        RiskLevel.VERY_HIGH: 0.90,
    }

    def __init__(self):
        pass

    def score(
        self,
        entity: EntityForScoring | dict[str, Any],
        transactions: Optional[list[dict]] = None,
        relationships: Optional[list[dict]] = None,
        watchlist_hits: Optional[list[dict]] = None,
    ) -> RiskScore:
        """
        Calculate risk score for an entity (convenience wrapper).

        Accepts either an EntityForScoring dataclass or a dict.
        """
        if isinstance(entity, EntityForScoring):
            entity_dict = {
                "id": entity.id,
                "name": entity.name,
                "entity_type": entity.entity_type,
                "country": entity.jurisdiction,
                "industry_code": entity.industry,
                "customer_type": entity.customer_type,
                "is_pep": entity.is_pep,
                "beneficial_owners": entity.beneficial_owners,
                "years_in_business": entity.years_in_business,
                "is_sanctioned": entity.has_sanctions_exposure,
                "transaction_volume_monthly": entity.transaction_volume_monthly,
                "cash_transaction_ratio": entity.cash_transaction_ratio,
                "high_risk_country_ratio": entity.high_risk_country_ratio,
            }
        else:
            entity_dict = entity

        return self.score_entity(entity_dict, transactions, relationships, watchlist_hits)

    def score_entity(
        self,
        entity: dict[str, Any],
        transactions: Optional[list[dict]] = None,
        relationships: Optional[list[dict]] = None,
        watchlist_hits: Optional[list[dict]] = None,
    ) -> RiskScore:
        """
        Calculate risk score for an entity.

        Args:
            entity: Entity data dict with keys:
                - id, entity_type, name, identifier
                - country, industry_code (SNI)
                - is_pep, is_sanctioned
            transactions: Optional transaction history
            relationships: Optional relationship data
            watchlist_hits: Optional watchlist match results

        Returns:
            RiskScore with factors and recommendations
        """
        factors = []

        # Geographic risk
        geo_factor = self._assess_geographic_risk(entity)
        if geo_factor:
            factors.append(geo_factor)

        # Customer type risk
        customer_factors = self._assess_customer_risk(entity, watchlist_hits)
        factors.extend(customer_factors)

        # Industry risk
        industry_factor = self._assess_industry_risk(entity)
        if industry_factor:
            factors.append(industry_factor)

        # Ownership structure risk
        ownership_factor = self._assess_ownership_risk(entity)
        if ownership_factor:
            factors.append(ownership_factor)

        # Transaction pattern risk
        if transactions:
            txn_factors = self._assess_transaction_risk(transactions)
            factors.extend(txn_factors)

        # Relationship network risk
        if relationships:
            rel_factor = self._assess_relationship_risk(relationships)
            if rel_factor:
                factors.append(rel_factor)

        # Calculate overall score
        score = self._calculate_overall_score(factors)

        return score

    def _assess_geographic_risk(self, entity: dict) -> Optional[RiskFactor]:
        """Assess geographic risk based on country."""
        country = entity.get("country", "").upper()

        if country in self.HIGH_RISK_COUNTRIES:
            return RiskFactor(
                category=RiskCategory.GEOGRAPHIC,
                name="high_risk_country",
                description=f"Entity in FATF high-risk jurisdiction: {country}",
                score=0.9,
                weight=1.5,
                evidence={"country": country, "list": "fatf_high_risk"},
            )
        elif country in self.MEDIUM_RISK_COUNTRIES:
            return RiskFactor(
                category=RiskCategory.GEOGRAPHIC,
                name="medium_risk_country",
                description=f"Entity in elevated-risk jurisdiction: {country}",
                score=0.5,
                weight=1.2,
                evidence={"country": country, "list": "elevated_risk"},
            )

        return None

    def _assess_customer_risk(
        self,
        entity: dict,
        watchlist_hits: Optional[list[dict]],
    ) -> list[RiskFactor]:
        """Assess customer type risk."""
        factors = []

        # PEP check
        if entity.get("is_pep"):
            factors.append(RiskFactor(
                category=RiskCategory.CUSTOMER,
                name="pep",
                description="Politically Exposed Person or associate",
                score=0.7,
                weight=1.5,
                evidence={"pep_status": True},
            ))

        # Sanctions check
        if entity.get("is_sanctioned"):
            factors.append(RiskFactor(
                category=RiskCategory.CUSTOMER,
                name="sanctioned",
                description="Entity on sanctions list",
                score=1.0,
                weight=2.0,
                evidence={"sanctioned": True},
            ))

        # Watchlist hits
        if watchlist_hits:
            for hit in watchlist_hits:
                factors.append(RiskFactor(
                    category=RiskCategory.CUSTOMER,
                    name=f"watchlist_{hit.get('list_type', 'unknown')}",
                    description=f"Match on {hit.get('list_name', 'watchlist')}",
                    score=hit.get("match_score", 0.8),
                    weight=1.3,
                    evidence=hit,
                ))

        return factors

    def _assess_industry_risk(self, entity: dict) -> Optional[RiskFactor]:
        """Assess industry risk based on SNI code."""
        sni_code = entity.get("industry_code", "")

        for code, desc in self.HIGH_RISK_INDUSTRIES.items():
            if sni_code.startswith(code):
                return RiskFactor(
                    category=RiskCategory.CUSTOMER,
                    name="high_risk_industry",
                    description=f"High-risk industry: {desc}",
                    score=0.6,
                    weight=1.2,
                    evidence={"sni_code": sni_code, "industry": desc},
                )

        return None

    def _assess_ownership_risk(self, entity: dict) -> Optional[RiskFactor]:
        """Assess risk from ownership structure."""
        if entity.get("entity_type") != "company":
            return None

        # Check for shell company indicators
        indicators = []

        # No employees
        if entity.get("employee_count", 0) == 0:
            indicators.append("no_employees")

        # Recently formed
        reg_date = entity.get("registration_date")
        if reg_date:
            if isinstance(reg_date, str):
                try:
                    reg_date = datetime.fromisoformat(reg_date)
                except ValueError:
                    reg_date = None

            if reg_date and (datetime.utcnow() - reg_date).days < 365:
                indicators.append("recently_formed")

        # Minimal capital
        capital = entity.get("share_capital", 0)
        if capital and Decimal(str(capital)) <= Decimal("25000"):
            indicators.append("minimal_capital")

        # Foreign ownership
        if entity.get("has_foreign_owners"):
            indicators.append("foreign_ownership")

        # Complex structure
        if entity.get("ownership_layers", 0) >= 3:
            indicators.append("complex_structure")

        if indicators:
            score = min(1.0, 0.2 * len(indicators))
            return RiskFactor(
                category=RiskCategory.CUSTOMER,
                name="ownership_risk",
                description=f"Elevated ownership risk: {', '.join(indicators)}",
                score=score,
                weight=1.1,
                evidence={"indicators": indicators},
            )

        return None

    def _assess_transaction_risk(self, transactions: list[dict]) -> list[RiskFactor]:
        """Assess risk from transaction patterns."""
        factors = []

        if not transactions:
            return factors

        # Calculate metrics
        amounts = [Decimal(str(t.get("amount", 0))) for t in transactions]
        total_volume = sum(amounts)

        # High volume
        if total_volume >= Decimal("10000000"):  # 10M SEK
            factors.append(RiskFactor(
                category=RiskCategory.TRANSACTION,
                name="high_volume",
                description=f"High transaction volume: {total_volume:,.0f} SEK",
                score=0.6,
                weight=1.0,
                evidence={"total_volume": str(total_volume)},
            ))

        # Velocity (transactions per day)
        if len(transactions) >= 2:
            timestamps = [t.get("timestamp") for t in transactions if t.get("timestamp")]
            if timestamps:
                date_range = (max(timestamps) - min(timestamps)).days or 1
                velocity = len(transactions) / date_range

                if velocity >= 10:
                    factors.append(RiskFactor(
                        category=RiskCategory.TRANSACTION,
                        name="high_velocity",
                        description=f"High transaction velocity: {velocity:.1f}/day",
                        score=0.5,
                        weight=1.0,
                        evidence={"transactions_per_day": velocity},
                    ))

        # Round amounts (potential structuring)
        round_count = sum(1 for a in amounts if a % 1000 == 0 and a >= 10000)
        if round_count >= 5 and round_count / len(amounts) >= 0.5:
            factors.append(RiskFactor(
                category=RiskCategory.TRANSACTION,
                name="round_amounts",
                description="Unusual proportion of round-number transactions",
                score=0.4,
                weight=1.0,
                evidence={"round_count": round_count, "total_count": len(transactions)},
            ))

        return factors

    def _assess_relationship_risk(self, relationships: list[dict]) -> Optional[RiskFactor]:
        """Assess risk from entity relationships."""
        high_risk_connections = 0

        for rel in relationships:
            counterparty = rel.get("counterparty", {})
            if counterparty.get("risk_level") in ["high", "very_high"]:
                high_risk_connections += 1
            if counterparty.get("is_pep") or counterparty.get("is_sanctioned"):
                high_risk_connections += 1

        if high_risk_connections > 0:
            score = min(1.0, 0.2 * high_risk_connections)
            return RiskFactor(
                category=RiskCategory.RELATIONSHIP,
                name="high_risk_connections",
                description=f"{high_risk_connections} connection(s) to high-risk entities",
                score=score,
                weight=1.3,
                evidence={"high_risk_connections": high_risk_connections},
            )

        return None

    def _calculate_overall_score(self, factors: list[RiskFactor]) -> RiskScore:
        """Calculate overall risk score from factors."""
        if not factors:
            return RiskScore(
                overall_score=0.0,
                risk_level=RiskLevel.LOW,
                factors=[],
                recommendations=["Standard monitoring"],
            )

        # Weighted average
        total_weight = sum(f.weight for f in factors)
        weighted_sum = sum(f.weighted_score for f in factors)
        overall = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Check for automatic escalation factors
        if any(f.name == "sanctioned" for f in factors):
            overall = 1.0

        # Determine level
        if overall >= self.THRESHOLDS[RiskLevel.VERY_HIGH]:
            level = RiskLevel.VERY_HIGH
        elif overall >= self.THRESHOLDS[RiskLevel.HIGH]:
            level = RiskLevel.HIGH
        elif overall >= self.THRESHOLDS[RiskLevel.MEDIUM]:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        # Category breakdown
        category_scores = {}
        for cat in RiskCategory:
            cat_factors = [f for f in factors if f.category == cat]
            if cat_factors:
                cat_weight = sum(f.weight for f in cat_factors)
                cat_sum = sum(f.weighted_score for f in cat_factors)
                category_scores[cat.value] = cat_sum / cat_weight

        # Generate recommendations
        recommendations = self._generate_recommendations(level, factors)

        # Build factor_scores dict
        factor_scores = {}
        for cat in RiskCategory:
            cat_factors = [f for f in factors if f.category == cat]
            if cat_factors:
                cat_weight = sum(f.weight for f in cat_factors)
                cat_sum = sum(f.weighted_score for f in cat_factors)
                factor_scores[cat.value] = cat_sum / cat_weight

        return RiskScore(
            total_score=overall,
            overall_score=overall,
            risk_level=level,
            factors=factors,
            category_scores=category_scores,
            factor_scores=factor_scores,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        level: RiskLevel,
        factors: list[RiskFactor],
    ) -> list[str]:
        """Generate action recommendations based on risk assessment."""
        recommendations = []

        if level == RiskLevel.VERY_HIGH:
            recommendations.append("Escalate to compliance officer immediately")
            recommendations.append("Consider filing SAR")
            recommendations.append("Enhanced due diligence required")

        elif level == RiskLevel.HIGH:
            recommendations.append("Enhanced monitoring required")
            recommendations.append("Senior management approval for new transactions")
            recommendations.append("Quarterly relationship review")

        elif level == RiskLevel.MEDIUM:
            recommendations.append("Standard monitoring with heightened attention")
            recommendations.append("Annual relationship review")

        else:
            recommendations.append("Standard monitoring")

        # Specific recommendations based on factors
        factor_names = {f.name for f in factors}

        if "pep" in factor_names:
            recommendations.append("Verify source of funds for significant transactions")

        if "high_risk_country" in factor_names:
            recommendations.append("Verify business purpose for cross-border transactions")

        if "ownership_risk" in factor_names:
            recommendations.append("Obtain and verify beneficial ownership information")

        return recommendations


class TransactionRiskScorer:
    """
    Real-time risk scoring for individual transactions.

    Designed for fast evaluation at transaction time.
    """

    # Thresholds in SEK
    AMOUNT_THRESHOLDS = {
        "low": Decimal("50000"),
        "medium": Decimal("150000"),
        "high": Decimal("500000"),
        "very_high": Decimal("1000000"),
    }

    def __init__(self, entity_scorer: Optional[EntityRiskScorer] = None):
        self.entity_scorer = entity_scorer or EntityRiskScorer()

    def score(
        self,
        transaction: TransactionForScoring | dict[str, Any],
        sender_entity: Optional[dict] = None,
        receiver_entity: Optional[dict] = None,
        sender_history: Optional[list[dict]] = None,
    ) -> RiskScore:
        """
        Score a transaction (convenience wrapper).

        Accepts either a TransactionForScoring dataclass or a dict.
        """
        if isinstance(transaction, TransactionForScoring):
            txn_dict = {
                "id": transaction.id,
                "amount": transaction.amount,
                "currency": transaction.currency,
                "timestamp": transaction.timestamp,
                "type": transaction.transaction_type,
                "is_cash": transaction.is_cash,
                "counterparty_country": transaction.counterparty_country,
                "is_round_amount": transaction.is_round_amount,
            }
            # Create a minimal entity dict for entity risk
            if sender_entity is None:
                sender_entity = {
                    "country": "SE",
                    "risk_level": transaction.entity_risk_level.value,
                }
        else:
            txn_dict = transaction

        return self.score_transaction(txn_dict, sender_entity, receiver_entity, sender_history)

    def score_transaction(
        self,
        transaction: dict[str, Any],
        sender_entity: Optional[dict] = None,
        receiver_entity: Optional[dict] = None,
        sender_history: Optional[list[dict]] = None,
    ) -> RiskScore:
        """
        Score a single transaction.

        Args:
            transaction: Transaction data with amount, type, etc.
            sender_entity: Optional sender entity data
            receiver_entity: Optional receiver entity data
            sender_history: Optional sender's recent transactions

        Returns:
            RiskScore for the transaction
        """
        factors = []

        # Amount risk
        amount = Decimal(str(transaction.get("amount", 0)))
        amount_factor = self._assess_amount_risk(amount)
        if amount_factor:
            factors.append(amount_factor)

        # Transaction type risk
        type_factor = self._assess_type_risk(transaction)
        if type_factor:
            factors.append(type_factor)

        # Counterparty risk
        if sender_entity:
            sender_score = self.entity_scorer.score_entity(sender_entity)
            if sender_score.overall_score >= 0.5:
                factors.append(RiskFactor(
                    category=RiskCategory.CUSTOMER,
                    name="sender_risk",
                    description=f"Sender has {sender_score.risk_level.value} risk",
                    score=sender_score.overall_score,
                    weight=1.0,
                ))

        if receiver_entity:
            receiver_score = self.entity_scorer.score_entity(receiver_entity)
            if receiver_score.overall_score >= 0.5:
                factors.append(RiskFactor(
                    category=RiskCategory.CUSTOMER,
                    name="receiver_risk",
                    description=f"Receiver has {receiver_score.risk_level.value} risk",
                    score=receiver_score.overall_score,
                    weight=1.0,
                ))

        # Pattern risk (compared to history)
        if sender_history:
            pattern_factors = self._assess_pattern_risk(transaction, sender_history)
            factors.extend(pattern_factors)

        # Calculate overall score
        score = self._calculate_score(factors, transaction)

        return score

    def _assess_amount_risk(self, amount: Decimal) -> Optional[RiskFactor]:
        """Assess risk based on transaction amount."""
        if amount >= self.AMOUNT_THRESHOLDS["very_high"]:
            return RiskFactor(
                category=RiskCategory.TRANSACTION,
                name="very_high_amount",
                description=f"Very high transaction amount: {amount:,.0f} SEK",
                score=0.7,
                weight=1.2,
                evidence={"amount": str(amount)},
            )
        elif amount >= self.AMOUNT_THRESHOLDS["high"]:
            return RiskFactor(
                category=RiskCategory.TRANSACTION,
                name="high_amount",
                description=f"High transaction amount: {amount:,.0f} SEK",
                score=0.5,
                weight=1.0,
                evidence={"amount": str(amount)},
            )
        elif amount >= self.AMOUNT_THRESHOLDS["medium"]:
            return RiskFactor(
                category=RiskCategory.TRANSACTION,
                name="medium_amount",
                description=f"Elevated transaction amount: {amount:,.0f} SEK",
                score=0.3,
                weight=0.8,
                evidence={"amount": str(amount)},
            )
        return None

    def _assess_type_risk(self, transaction: dict) -> Optional[RiskFactor]:
        """Assess risk based on transaction type."""
        high_risk_types = {"cash", "crypto", "wire_international", "money_order"}
        medium_risk_types = {"wire_domestic", "check"}

        txn_type = transaction.get("transaction_type", "").lower()

        if txn_type in high_risk_types:
            return RiskFactor(
                category=RiskCategory.PRODUCT,
                name="high_risk_channel",
                description=f"High-risk transaction type: {txn_type}",
                score=0.6,
                weight=1.1,
                evidence={"type": txn_type},
            )
        elif txn_type in medium_risk_types:
            return RiskFactor(
                category=RiskCategory.PRODUCT,
                name="medium_risk_channel",
                description=f"Elevated-risk transaction type: {txn_type}",
                score=0.3,
                weight=0.9,
                evidence={"type": txn_type},
            )
        return None

    def _assess_pattern_risk(
        self,
        transaction: dict,
        history: list[dict],
    ) -> list[RiskFactor]:
        """Assess risk by comparing to historical patterns."""
        factors = []

        amount = Decimal(str(transaction.get("amount", 0)))

        # Calculate historical stats
        historical_amounts = [Decimal(str(t.get("amount", 0))) for t in history]
        if not historical_amounts:
            return factors

        avg_amount = sum(historical_amounts) / len(historical_amounts)
        max_amount = max(historical_amounts)

        # Unusual amount
        if amount > avg_amount * 5:
            factors.append(RiskFactor(
                category=RiskCategory.BEHAVIORAL,
                name="unusual_amount",
                description=f"Amount {amount / avg_amount:.1f}x higher than average",
                score=0.6,
                weight=1.0,
                evidence={
                    "amount": str(amount),
                    "average": str(avg_amount),
                    "ratio": float(amount / avg_amount),
                },
            ))

        # New high
        if amount > max_amount * 1.5:
            factors.append(RiskFactor(
                category=RiskCategory.BEHAVIORAL,
                name="new_high",
                description="Transaction significantly exceeds historical maximum",
                score=0.4,
                weight=0.8,
                evidence={
                    "amount": str(amount),
                    "previous_max": str(max_amount),
                },
            ))

        return factors

    def _calculate_score(
        self,
        factors: list[RiskFactor],
        transaction: dict,
    ) -> RiskScore:
        """Calculate overall transaction risk score."""
        if not factors:
            return RiskScore(
                transaction_id=transaction.get("id"),
                total_score=0.1,
                overall_score=0.1,
                risk_level=RiskLevel.LOW,
                factors=[],
                recommendations=["Standard processing"],
            )

        # Weighted average
        total_weight = sum(f.weight for f in factors)
        weighted_sum = sum(f.weighted_score for f in factors)
        overall = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Determine level
        if overall >= 0.75:
            level = RiskLevel.VERY_HIGH
        elif overall >= 0.5:
            level = RiskLevel.HIGH
        elif overall >= 0.25:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        # Recommendations
        if level in [RiskLevel.VERY_HIGH, RiskLevel.HIGH]:
            recommendations = ["Manual review required", "Hold for compliance approval"]
        elif level == RiskLevel.MEDIUM:
            recommendations = ["Enhanced monitoring", "Log for batch review"]
        else:
            recommendations = ["Standard processing"]

        return RiskScore(
            transaction_id=transaction.get("id"),
            total_score=overall,
            overall_score=overall,
            risk_level=level,
            factors=factors,
            recommendations=recommendations,
        )
