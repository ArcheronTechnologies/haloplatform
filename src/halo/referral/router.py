"""
Authority routing for referrals.

Routes detected patterns to the appropriate Swedish authority based on:
- Crime type
- Value thresholds
- Confidence levels
- Jurisdictional rules
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class Authority(str, Enum):
    """Swedish authorities that receive referrals."""

    EBM = "EBM"  # Ekobrottsmyndigheten - Economic crime
    SKV = "SKV"  # Skatteverket - Tax fraud
    FK = "FK"  # Försäkringskassan - Welfare/insurance fraud
    IVO = "IVO"  # Inspektionen för vård och omsorg - Healthcare fraud
    FIU = "FIU"  # Financial Intelligence Unit - Money laundering
    POL = "POL"  # Polisen - General criminal activity
    TUL = "TUL"  # Tullverket - Customs fraud


@dataclass
class RoutingDecision:
    """Decision from the routing algorithm."""

    primary_authority: Authority
    secondary_authorities: list[Authority] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    value_threshold_met: bool = False
    requires_fiu_report: bool = False


@dataclass
class RoutingThreshold:
    """Thresholds for routing to a specific authority."""

    min_value_sek: float = 0
    min_confidence: float = 0.6
    crime_types: list[str] = field(default_factory=list)


class AuthorityRouter:
    """
    Routes detections to appropriate Swedish authorities.

    Routing rules based on:
    - Swedish Economic Crime Authority guidelines
    - FI reporting requirements
    - Värdebaserad prioritering (value-based prioritization)
    """

    # Default thresholds for each authority
    AUTHORITY_THRESHOLDS: dict[Authority, RoutingThreshold] = {
        Authority.EBM: RoutingThreshold(
            min_value_sek=500_000,  # 500k SEK for EBM jurisdiction
            min_confidence=0.7,
            crime_types=["economic_crime", "corporate_fraud", "tax_fraud"],
        ),
        Authority.SKV: RoutingThreshold(
            min_value_sek=50_000,
            min_confidence=0.6,
            crime_types=["tax_fraud", "vat_fraud", "undeclared_income"],
        ),
        Authority.FK: RoutingThreshold(
            min_value_sek=20_000,
            min_confidence=0.6,
            crime_types=["welfare_fraud", "sickness_benefit_fraud", "disability_fraud"],
        ),
        Authority.FIU: RoutingThreshold(
            min_value_sek=150_000,  # AMLD threshold
            min_confidence=0.5,
            crime_types=["money_laundering", "terrorist_financing", "suspicious_transaction"],
        ),
        Authority.IVO: RoutingThreshold(
            min_value_sek=10_000,
            min_confidence=0.6,
            crime_types=["healthcare_fraud", "care_home_fraud"],
        ),
        Authority.POL: RoutingThreshold(
            min_value_sek=0,
            min_confidence=0.7,
            crime_types=["organized_crime", "violence", "narcotics"],
        ),
    }

    def __init__(self, custom_thresholds: Optional[dict] = None):
        """
        Initialize router with optional custom thresholds.

        Args:
            custom_thresholds: Override default thresholds
        """
        self.thresholds = dict(self.AUTHORITY_THRESHOLDS)
        if custom_thresholds:
            for auth, threshold in custom_thresholds.items():
                if auth in Authority:
                    self.thresholds[Authority(auth)] = threshold

    def route(
        self,
        crime_type: str,
        estimated_value_sek: float,
        confidence: float,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RoutingDecision:
        """
        Determine which authority should receive a referral.

        Args:
            crime_type: Type of crime detected
            estimated_value_sek: Estimated value in SEK
            confidence: Detection confidence (0-1)
            metadata: Additional context for routing

        Returns:
            RoutingDecision with primary and secondary authorities
        """
        metadata = metadata or {}

        # Find all matching authorities
        candidates: list[tuple[Authority, float]] = []

        for authority, threshold in self.thresholds.items():
            if crime_type in threshold.crime_types:
                if confidence >= threshold.min_confidence:
                    # Calculate match score
                    score = self._calculate_authority_score(
                        authority,
                        threshold,
                        estimated_value_sek,
                        confidence,
                    )
                    candidates.append((authority, score))

        if not candidates:
            # Default to police for unmatched cases
            return RoutingDecision(
                primary_authority=Authority.POL,
                confidence=confidence,
                rationale="No specific authority match - defaulting to Polisen",
            )

        # Sort by score
        candidates.sort(key=lambda x: x[1], reverse=True)

        primary = candidates[0][0]
        primary_threshold = self.thresholds[primary]

        # Check if FIU report required
        requires_fiu = (
            estimated_value_sek >= 150_000
            and crime_type in ["money_laundering", "suspicious_transaction"]
        )

        return RoutingDecision(
            primary_authority=primary,
            secondary_authorities=[a for a, _ in candidates[1:3]],
            confidence=confidence,
            rationale=self._generate_rationale(
                primary, crime_type, estimated_value_sek, confidence
            ),
            value_threshold_met=estimated_value_sek >= primary_threshold.min_value_sek,
            requires_fiu_report=requires_fiu,
        )

    def _calculate_authority_score(
        self,
        authority: Authority,
        threshold: RoutingThreshold,
        value_sek: float,
        confidence: float,
    ) -> float:
        """Calculate match score for an authority."""
        score = confidence

        # Bonus if value exceeds threshold
        if value_sek >= threshold.min_value_sek:
            score += 0.2

        # Authority-specific adjustments
        if authority == Authority.EBM and value_sek >= 1_000_000:
            score += 0.1  # EBM prioritizes high-value cases

        return min(score, 1.0)

    def _generate_rationale(
        self,
        authority: Authority,
        crime_type: str,
        value_sek: float,
        confidence: float,
    ) -> str:
        """Generate human-readable rationale for routing decision."""
        threshold = self.thresholds[authority]

        parts = [
            f"Routed to {authority.value} based on:",
            f"- Crime type '{crime_type}' matches authority jurisdiction",
            f"- Confidence {confidence:.0%} meets threshold {threshold.min_confidence:.0%}",
        ]

        if value_sek >= threshold.min_value_sek:
            parts.append(
                f"- Value {value_sek:,.0f} SEK exceeds threshold {threshold.min_value_sek:,.0f} SEK"
            )
        else:
            parts.append(
                f"- Value {value_sek:,.0f} SEK below threshold {threshold.min_value_sek:,.0f} SEK"
            )

        return "\n".join(parts)
