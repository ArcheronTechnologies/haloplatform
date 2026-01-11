"""
Risk score computation for entities.

Computes risk scores based on:
- Entity attributes
- Network connections
- Historical patterns
- Shell indicators
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class RiskFactors:
    """Risk factors contributing to a risk score."""

    # Person-specific factors
    high_company_count: float = 0.0  # Many directorships
    shell_company_associations: float = 0.0  # Connected to shell companies
    high_director_velocity: float = 0.0  # Frequent director changes
    vulnerable_area_connections: float = 0.0  # Connected to vulnerable areas
    network_cluster_risk: float = 0.0  # Part of high-risk network

    # Company-specific factors
    no_employees: float = 0.0  # Zero or null employees
    minimal_revenue: float = 0.0  # Very low revenue
    generic_sni_code: float = 0.0  # Holding/consulting/generic industry
    recently_formed: float = 0.0  # New company < 12 months
    no_physical_address: float = 0.0  # C/O or PO Box address
    high_director_turnover: float = 0.0  # Many director changes
    no_annual_reports: float = 0.0  # Missing filings
    foreign_ownership: float = 0.0  # Foreign shareholders
    circular_ownership: float = 0.0  # Ownership loops

    # Address-specific factors
    registration_hub: float = 0.0  # Many companies registered
    vulnerable_area: float = 0.0  # In vulnerable area
    high_turnover_address: float = 0.0  # Companies frequently move away

    def total_score(self) -> float:
        """Calculate total risk score (0-1)."""
        factors = [
            self.high_company_count,
            self.shell_company_associations,
            self.high_director_velocity,
            self.vulnerable_area_connections,
            self.network_cluster_risk,
            self.no_employees,
            self.minimal_revenue,
            self.generic_sni_code,
            self.recently_formed,
            self.no_physical_address,
            self.high_director_turnover,
            self.no_annual_reports,
            self.foreign_ownership,
            self.circular_ownership,
            self.registration_hub,
            self.vulnerable_area,
            self.high_turnover_address,
        ]
        return min(sum(factors), 1.0)

    def to_list(self) -> list[str]:
        """Get list of active risk factor names."""
        factors = []
        if self.high_company_count > 0:
            factors.append("high_company_count")
        if self.shell_company_associations > 0:
            factors.append("shell_company_associations")
        if self.high_director_velocity > 0:
            factors.append("high_director_velocity")
        if self.vulnerable_area_connections > 0:
            factors.append("vulnerable_area_connections")
        if self.network_cluster_risk > 0:
            factors.append("network_cluster_risk")
        if self.no_employees > 0:
            factors.append("no_employees")
        if self.minimal_revenue > 0:
            factors.append("minimal_revenue")
        if self.generic_sni_code > 0:
            factors.append("generic_sni_code")
        if self.recently_formed > 0:
            factors.append("recently_formed")
        if self.no_physical_address > 0:
            factors.append("no_physical_address")
        if self.high_director_turnover > 0:
            factors.append("high_director_turnover")
        if self.no_annual_reports > 0:
            factors.append("no_annual_reports")
        if self.foreign_ownership > 0:
            factors.append("foreign_ownership")
        if self.circular_ownership > 0:
            factors.append("circular_ownership")
        if self.registration_hub > 0:
            factors.append("registration_hub")
        if self.vulnerable_area > 0:
            factors.append("vulnerable_area")
        if self.high_turnover_address > 0:
            factors.append("high_turnover_address")
        return factors

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "high_company_count": self.high_company_count,
            "shell_company_associations": self.shell_company_associations,
            "high_director_velocity": self.high_director_velocity,
            "vulnerable_area_connections": self.vulnerable_area_connections,
            "network_cluster_risk": self.network_cluster_risk,
            "no_employees": self.no_employees,
            "minimal_revenue": self.minimal_revenue,
            "generic_sni_code": self.generic_sni_code,
            "recently_formed": self.recently_formed,
            "no_physical_address": self.no_physical_address,
            "high_director_turnover": self.high_director_turnover,
            "no_annual_reports": self.no_annual_reports,
            "foreign_ownership": self.foreign_ownership,
            "circular_ownership": self.circular_ownership,
            "registration_hub": self.registration_hub,
            "vulnerable_area": self.vulnerable_area,
            "high_turnover_address": self.high_turnover_address,
            "total_score": self.total_score(),
        }


@dataclass
class RiskScoreResult:
    """Result of risk score computation."""

    entity_id: UUID
    entity_type: str
    risk_score: float
    factors: RiskFactors
    computed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_id": str(self.entity_id),
            "entity_type": self.entity_type,
            "risk_score": self.risk_score,
            "factors": self.factors.to_dict(),
            "factor_list": self.factors.to_list(),
            "computed_at": self.computed_at.isoformat(),
        }


class PersonRiskScorer:
    """
    Compute risk scores for person entities.

    Factors considered:
    - Number of companies directed
    - Shell company associations
    - Director velocity in connected companies
    - Network cluster risk
    - Vulnerable area connections
    """

    # Thresholds for risk factors
    HIGH_COMPANY_COUNT_THRESHOLD = 5
    SHELL_ASSOCIATION_WEIGHT = 0.3
    DIRECTOR_VELOCITY_THRESHOLD = 2.0  # Changes per year
    NETWORK_CLUSTER_WEIGHT = 0.2

    def compute(
        self,
        person_id: UUID,
        company_count: int,
        active_directorship_count: int,
        shell_company_count: int = 0,
        avg_director_velocity: float = 0.0,
        vulnerable_area_count: int = 0,
        network_cluster_risk: float = 0.0,
    ) -> RiskScoreResult:
        """
        Compute risk score for a person.

        Args:
            person_id: The person entity ID
            company_count: Total companies associated
            active_directorship_count: Current active directorships
            shell_company_count: Number of shell-like companies directed
            avg_director_velocity: Average director changes in directed companies
            vulnerable_area_count: Connections to vulnerable areas
            network_cluster_risk: Risk score of network cluster

        Returns:
            Risk score result with factors
        """
        factors = RiskFactors()

        # High company count risk
        if active_directorship_count >= self.HIGH_COMPANY_COUNT_THRESHOLD:
            factors.high_company_count = min(
                0.1 + 0.05 * (active_directorship_count - self.HIGH_COMPANY_COUNT_THRESHOLD),
                0.3,
            )

        # Shell company associations
        if shell_company_count > 0:
            factors.shell_company_associations = min(
                self.SHELL_ASSOCIATION_WEIGHT * shell_company_count,
                0.5,
            )

        # High director velocity in directed companies
        if avg_director_velocity > self.DIRECTOR_VELOCITY_THRESHOLD:
            factors.high_director_velocity = min(
                0.1 * (avg_director_velocity - self.DIRECTOR_VELOCITY_THRESHOLD),
                0.2,
            )

        # Vulnerable area connections
        if vulnerable_area_count > 0:
            factors.vulnerable_area_connections = min(
                0.05 * vulnerable_area_count,
                0.15,
            )

        # Network cluster risk
        factors.network_cluster_risk = network_cluster_risk * self.NETWORK_CLUSTER_WEIGHT

        return RiskScoreResult(
            entity_id=person_id,
            entity_type="PERSON",
            risk_score=factors.total_score(),
            factors=factors,
        )


class CompanyRiskScorer:
    """
    Compute risk scores for company entities.

    Factors considered:
    - Employee count (zero employees)
    - Revenue (minimal or none)
    - SNI code (generic industries)
    - Age (recently formed)
    - Address type (C/O, PO Box)
    - Director changes (turnover)
    - Filing compliance (annual reports)
    - Ownership structure
    """

    # SNI codes commonly used by shell companies
    SHELL_SNI_CODES = {
        "64200",  # Holding company
        "70100",  # Head office activities
        "70220",  # Business and management consultancy
        "82990",  # Other business support
        "46900",  # Non-specialized wholesale
    }

    # Thresholds
    MINIMAL_REVENUE_THRESHOLD = 100_000  # SEK
    RECENTLY_FORMED_MONTHS = 12
    HIGH_TURNOVER_THRESHOLD = 2.0  # Directors per year

    def compute(
        self,
        company_id: UUID,
        employees: Optional[int],
        revenue: Optional[int],
        sni_code: Optional[str],
        registration_date: Optional[date],
        address_type: Optional[str],  # "physical", "c_o", "po_box"
        director_velocity: float = 0.0,
        has_annual_reports: bool = True,
        foreign_ownership_pct: float = 0.0,
        has_circular_ownership: bool = False,
    ) -> RiskScoreResult:
        """
        Compute risk score for a company.

        Returns:
            Risk score result with factors
        """
        factors = RiskFactors()

        # No employees
        if employees is None or employees == 0:
            factors.no_employees = 0.15

        # Minimal revenue
        if revenue is None or revenue < self.MINIMAL_REVENUE_THRESHOLD:
            factors.minimal_revenue = 0.15

        # Generic SNI code
        if sni_code and sni_code in self.SHELL_SNI_CODES:
            factors.generic_sni_code = 0.15

        # Recently formed
        if registration_date:
            months_old = (date.today() - registration_date).days / 30
            if months_old < self.RECENTLY_FORMED_MONTHS:
                factors.recently_formed = 0.1 * (1 - months_old / self.RECENTLY_FORMED_MONTHS)

        # Non-physical address
        if address_type in ["c_o", "po_box"]:
            factors.no_physical_address = 0.15

        # High director turnover
        if director_velocity > self.HIGH_TURNOVER_THRESHOLD:
            factors.high_director_turnover = min(
                0.1 * (director_velocity - self.HIGH_TURNOVER_THRESHOLD),
                0.2,
            )

        # Missing annual reports
        if not has_annual_reports:
            factors.no_annual_reports = 0.15

        # Foreign ownership
        if foreign_ownership_pct > 0.5:
            factors.foreign_ownership = min(foreign_ownership_pct * 0.2, 0.2)

        # Circular ownership
        if has_circular_ownership:
            factors.circular_ownership = 0.2

        return RiskScoreResult(
            entity_id=company_id,
            entity_type="COMPANY",
            risk_score=factors.total_score(),
            factors=factors,
        )


class AddressRiskScorer:
    """
    Compute risk scores for address entities.

    Factors considered:
    - Registration hub status
    - Vulnerable area classification
    - Company turnover rate
    """

    HUB_THRESHOLD = 10  # Companies at same address
    HIGH_TURNOVER_THRESHOLD = 0.3  # 30% companies left in a year

    def compute(
        self,
        address_id: UUID,
        company_count: int,
        person_count: int,
        is_vulnerable_area: bool,
        vulnerability_level: Optional[str],
        company_turnover_rate: float = 0.0,
    ) -> RiskScoreResult:
        """
        Compute risk score for an address.

        Returns:
            Risk score result with factors
        """
        factors = RiskFactors()

        # Registration hub
        if company_count >= self.HUB_THRESHOLD:
            # More risk if many companies but few people
            ratio = company_count / max(person_count, 1)
            factors.registration_hub = min(0.1 + 0.05 * ratio, 0.4)

        # Vulnerable area
        if is_vulnerable_area:
            if vulnerability_level == "PARTICULARLY":
                factors.vulnerable_area = 0.3
            elif vulnerability_level == "RISK":
                factors.vulnerable_area = 0.2
            else:
                factors.vulnerable_area = 0.1

        # High turnover
        if company_turnover_rate > self.HIGH_TURNOVER_THRESHOLD:
            factors.high_turnover_address = min(
                company_turnover_rate * 0.3,
                0.2,
            )

        return RiskScoreResult(
            entity_id=address_id,
            entity_type="ADDRESS",
            risk_score=factors.total_score(),
            factors=factors,
        )
