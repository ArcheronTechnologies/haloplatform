"""
Shell company indicator calculation.

Identifies indicators that a company may be a shell company:
- No employees
- Minimal revenue
- Generic industry (holding, consulting)
- Recently formed
- Non-physical address
- High director turnover
- Missing filings
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class ShellIndicators:
    """Shell company indicators for a company."""

    company_id: UUID
    orgnummer: str
    company_name: str

    # Individual indicators (True if present)
    no_employees: bool = False
    minimal_revenue: bool = False
    generic_sni_code: bool = False
    recently_formed: bool = False
    no_physical_address: bool = False
    high_director_turnover: bool = False
    no_annual_reports: bool = False
    foreign_director: bool = False
    multiple_directors_shared: bool = False
    dormant: bool = False  # No activity in 12+ months

    # Metadata
    indicator_count: int = 0
    shell_score: float = 0.0
    computed_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Calculate indicator count and score after initialization."""
        self._update_counts()

    def _update_counts(self):
        """Update indicator count and shell score."""
        indicators = [
            self.no_employees,
            self.minimal_revenue,
            self.generic_sni_code,
            self.recently_formed,
            self.no_physical_address,
            self.high_director_turnover,
            self.no_annual_reports,
            self.foreign_director,
            self.multiple_directors_shared,
            self.dormant,
        ]
        self.indicator_count = sum(1 for i in indicators if i)
        # Score is weighted sum (some indicators more significant)
        self.shell_score = self._calculate_score()

    def _calculate_score(self) -> float:
        """Calculate weighted shell score."""
        weights = {
            "no_employees": 0.15,
            "minimal_revenue": 0.15,
            "generic_sni_code": 0.15,
            "recently_formed": 0.1,
            "no_physical_address": 0.15,
            "high_director_turnover": 0.1,
            "no_annual_reports": 0.1,
            "foreign_director": 0.05,
            "multiple_directors_shared": 0.1,
            "dormant": 0.1,
        }

        score = 0.0
        if self.no_employees:
            score += weights["no_employees"]
        if self.minimal_revenue:
            score += weights["minimal_revenue"]
        if self.generic_sni_code:
            score += weights["generic_sni_code"]
        if self.recently_formed:
            score += weights["recently_formed"]
        if self.no_physical_address:
            score += weights["no_physical_address"]
        if self.high_director_turnover:
            score += weights["high_director_turnover"]
        if self.no_annual_reports:
            score += weights["no_annual_reports"]
        if self.foreign_director:
            score += weights["foreign_director"]
        if self.multiple_directors_shared:
            score += weights["multiple_directors_shared"]
        if self.dormant:
            score += weights["dormant"]

        return min(score, 1.0)

    @property
    def is_shell_like(self) -> bool:
        """Check if company has enough indicators to be shell-like."""
        return self.indicator_count >= 3 or self.shell_score >= 0.4

    def to_list(self) -> list[str]:
        """Get list of active indicator names."""
        indicators = []
        if self.no_employees:
            indicators.append("no_employees")
        if self.minimal_revenue:
            indicators.append("minimal_revenue")
        if self.generic_sni_code:
            indicators.append("generic_sni_code")
        if self.recently_formed:
            indicators.append("recently_formed")
        if self.no_physical_address:
            indicators.append("no_physical_address")
        if self.high_director_turnover:
            indicators.append("high_director_turnover")
        if self.no_annual_reports:
            indicators.append("no_annual_reports")
        if self.foreign_director:
            indicators.append("foreign_director")
        if self.multiple_directors_shared:
            indicators.append("multiple_directors_shared")
        if self.dormant:
            indicators.append("dormant")
        return indicators

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "company_id": str(self.company_id),
            "orgnummer": self.orgnummer,
            "company_name": self.company_name,
            "indicators": self.to_list(),
            "indicator_count": self.indicator_count,
            "shell_score": round(self.shell_score, 3),
            "is_shell_like": self.is_shell_like,
            "computed_at": self.computed_at.isoformat(),
        }


class ShellIndicatorCalculator:
    """
    Calculate shell company indicators for companies.

    Uses company attributes and relationships to identify
    shell company patterns.
    """

    # SNI codes commonly used by shell companies
    SHELL_SNI_CODES = {
        "64200": "Holding company activities",
        "64300": "Trusts, funds and similar financial entities",
        "70100": "Activities of head offices",
        "70220": "Business and other management consultancy",
        "82110": "Combined office administrative service activities",
        "82990": "Other business support service activities",
        "46900": "Non-specialised wholesale trade",
    }

    # Thresholds
    MINIMAL_REVENUE_THRESHOLD = 100_000  # SEK
    RECENTLY_FORMED_DAYS = 365
    HIGH_TURNOVER_THRESHOLD = 2.0  # Director changes per year

    def calculate(
        self,
        company_id: UUID,
        orgnummer: str,
        company_name: str,
        employees: Optional[int] = None,
        revenue: Optional[int] = None,
        sni_code: Optional[str] = None,
        registration_date: Optional[date] = None,
        address: Optional[str] = None,
        address_type: Optional[str] = None,
        director_velocity: float = 0.0,
        has_annual_reports: bool = True,
        has_foreign_director: bool = False,
        shared_director_count: int = 0,
        last_activity_date: Optional[date] = None,
    ) -> ShellIndicators:
        """
        Calculate shell indicators for a company.

        Args:
            company_id: Company entity ID
            orgnummer: Organization number
            company_name: Company name
            employees: Number of employees (None = unknown)
            revenue: Annual revenue in SEK (None = unknown)
            sni_code: Primary SNI code
            registration_date: Company registration date
            address: Registered address string
            address_type: Type of address ("physical", "c_o", "po_box")
            director_velocity: Director changes per year
            has_annual_reports: Whether annual reports filed
            has_foreign_director: Whether any director is non-Swedish
            shared_director_count: Directors shared with other companies
            last_activity_date: Date of last known activity

        Returns:
            ShellIndicators with all detected indicators
        """
        indicators = ShellIndicators(
            company_id=company_id,
            orgnummer=orgnummer,
            company_name=company_name,
        )

        # No employees
        if employees is None or employees == 0:
            indicators.no_employees = True

        # Minimal revenue
        if revenue is not None and revenue < self.MINIMAL_REVENUE_THRESHOLD:
            indicators.minimal_revenue = True
        elif revenue is None:
            # Unknown revenue is also suspicious for established companies
            if registration_date and (date.today() - registration_date).days > 365 * 2:
                indicators.minimal_revenue = True

        # Generic SNI code
        if sni_code and sni_code in self.SHELL_SNI_CODES:
            indicators.generic_sni_code = True

        # Recently formed
        if registration_date:
            days_old = (date.today() - registration_date).days
            if days_old < self.RECENTLY_FORMED_DAYS:
                indicators.recently_formed = True

        # Non-physical address
        if address_type in ["c_o", "po_box"]:
            indicators.no_physical_address = True
        elif address:
            addr_lower = address.lower()
            if "c/o" in addr_lower or "box" in addr_lower or "postbox" in addr_lower:
                indicators.no_physical_address = True

        # High director turnover
        if director_velocity > self.HIGH_TURNOVER_THRESHOLD:
            indicators.high_director_turnover = True

        # Missing annual reports
        if not has_annual_reports:
            indicators.no_annual_reports = True

        # Foreign director
        if has_foreign_director:
            indicators.foreign_director = True

        # Multiple shared directors
        if shared_director_count >= 2:
            indicators.multiple_directors_shared = True

        # Dormant (no activity in 12+ months)
        if last_activity_date:
            days_since_activity = (date.today() - last_activity_date).days
            if days_since_activity > 365:
                indicators.dormant = True

        # Recalculate counts
        indicators._update_counts()

        return indicators

    def calculate_batch(
        self,
        companies: list[dict[str, Any]],
    ) -> list[ShellIndicators]:
        """
        Calculate shell indicators for multiple companies.

        Args:
            companies: List of company data dictionaries

        Returns:
            List of ShellIndicators results
        """
        results = []
        for company in companies:
            result = self.calculate(
                company_id=company.get("id") or company.get("company_id"),
                orgnummer=company.get("orgnummer", ""),
                company_name=company.get("name", ""),
                employees=company.get("employees"),
                revenue=company.get("revenue"),
                sni_code=company.get("sni_code"),
                registration_date=company.get("registration_date"),
                address=company.get("address"),
                address_type=company.get("address_type"),
                director_velocity=company.get("director_velocity", 0.0),
                has_annual_reports=company.get("has_annual_reports", True),
                has_foreign_director=company.get("has_foreign_director", False),
                shared_director_count=company.get("shared_director_count", 0),
                last_activity_date=company.get("last_activity_date"),
            )
            results.append(result)

        return results

    def find_shell_companies(
        self,
        companies: list[dict[str, Any]],
        min_score: float = 0.4,
    ) -> list[ShellIndicators]:
        """
        Find companies that appear to be shell companies.

        Args:
            companies: List of company data dictionaries
            min_score: Minimum shell score to include

        Returns:
            List of shell-like companies sorted by score
        """
        all_indicators = self.calculate_batch(companies)

        shell_companies = [
            ind for ind in all_indicators
            if ind.shell_score >= min_score
        ]

        # Sort by shell score descending
        shell_companies.sort(key=lambda x: x.shell_score, reverse=True)

        return shell_companies
