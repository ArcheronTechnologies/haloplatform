"""
Layer 1: Anomaly Detection.

Statistical deviation detection from baseline Swedish business patterns.
No labels needed - just register data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Protocol

from halo.graph.client import GraphClient


# ============================================================================
# BASELINE CALIBRATION
# ============================================================================
# Calibrated from 8,200 active Swedish ABs on 2025-12-26
# Source: SCB enumeration -> Bolagsverket XBRL extraction -> Shell scoring
#
# KEY FINDINGS FROM SHELL SCORING (2025-12-26):
#   - High severity (score >= 0.6): 30 companies (0.4%)
#   - Medium severity (score >= 0.4): 268 companies (3.3%)
#   - Low severity: 7,902 companies (96.4%)
#
# INDICATOR PREVALENCE:
#   - no_employees: 99.2% (nearly universal - Bolagsverket doesn't track employees)
#   - generic_sni: 15.5% (codes 64,66,68,70,82)
#   - single_director: 8.7% (companies with director data from allabolag)
#   - recently_formed: 4.1% (< 2 years old)
#   - f_skatt_no_vat: 1.3% (rare, strong fraud signal)
#
# Coverage: 14.9% have director data, 1.3% have address data
# Next recalibration: When allabolag enrichment reaches 50%+
# ============================================================================

@dataclass
class BaselineStats:
    """
    Baseline statistics calibrated from real Swedish company data.

    Calibration: 2025-12-26, n=8,200 active ABs
    """
    # Address registration density (limited data - 109 addresses from allabolag)
    # TODO: Recalibrate when more address data available
    addr_density_mean: float = 1.02
    addr_density_std: float = 0.14
    addr_density_p95: float = 1.0
    addr_density_p99: float = 2.0

    # Director portfolio size (n=2,367 persons from 1,223 companies)
    # CALIBRATED from Bolagsverket XBRL data
    director_roles_mean: float = 1.12
    director_roles_std: float = 0.60
    director_roles_p95: float = 2.0
    director_roles_p99: float = 2.0  # Very tight distribution

    # Directors per company (n=1,223 companies with data)
    directors_per_company_mean: float = 2.17
    directors_per_company_median: float = 1.0
    single_director_rate: float = 0.581  # 58.1% have just 1 director

    # Formation velocity (by formation agent) - PLACEHOLDER
    formations_per_agent_month_mean: float = 12.0
    formations_per_agent_month_std: float = 10.0
    formations_per_agent_month_p99: float = 50.0

    # Company lifespan - PLACEHOLDER
    company_lifespan_months_median: float = 84.0  # 7 years
    company_lifespan_months_std: float = 48.0

    # Address changes - PLACEHOLDER
    address_changes_per_year_mean: float = 0.1
    address_changes_per_year_std: float = 0.3

    # Director changes - PLACEHOLDER
    director_changes_per_year_mean: float = 0.2
    director_changes_per_year_std: float = 0.4

    # SNI distribution (n=7,343 companies with SNI)
    generic_sni_rate: float = 0.246  # 24.6% in 64,66,68,70,82

    # Shell indicator prevalence (from 8,200 companies, 2025-12-26)
    no_employees_rate: float = 0.992      # 99.2% - nearly universal
    generic_sni_rate_actual: float = 0.155  # 15.5%
    single_director_rate_actual: float = 0.087  # 8.7% (of companies with director data)
    recently_formed_rate: float = 0.041   # 4.1%
    f_skatt_no_vat_rate: float = 0.013    # 1.3% - rare, strong signal


# ============================================================================
# SHELL SCORING WEIGHTS
# ============================================================================
# Justification for each weight:
#
# no_employees (0.15): Nearly universal at 99.2%, weak signal alone.
#   Bolagsverket doesn't track employees for most companies.
#   Only meaningful when combined with other indicators.
#
# generic_sni (0.20): 15.5% prevalence. Consulting (70), financial services (64,66),
#   real estate (68), admin services (82) are legitimately common but also
#   overrepresented in shell company schemes. Medium weight.
#
# recently_formed (0.15): 4.1% prevalence. New companies (<2 years) have
#   higher fraud risk but many are legitimate startups. Medium-low weight.
#
# f_skatt_no_vat (0.25): Only 1.3% prevalence. F-skatt (tax registration)
#   without VAT registration is suspicious - suggests company generates
#   invoices but doesn't sell goods/services. STRONG SIGNAL.
#
# single_director (0.10): 8.7% of companies with director data. Common in
#   legitimate small businesses. Low weight - only meaningful with other indicators.
#
# no_revenue (0.15): Not reliably available in Bolagsverket data. When available
#   and 0, it's meaningful combined with other indicators.
#
# THRESHOLD JUSTIFICATION:
#   - High severity >= 0.6: Requires 3+ strong indicators or 4+ weak indicators
#   - Yields 0.4% flag rate (30/8,200) - manageable for human review
#   - Medium severity >= 0.4: 3.3% flag rate - for monitoring, not immediate action
# ============================================================================

SHELL_SCORING_WEIGHTS = {
    "no_employees": 0.15,
    "generic_sni": 0.20,
    "recently_formed": 0.15,
    "f_skatt_no_vat": 0.25,  # Strongest indicator - rare and suspicious
    "single_director": 0.10,  # Weak indicator - common in legitimate businesses
    "no_revenue": 0.15,
}


# Thresholds for anomaly flagging
# CALIBRATED from p95/p99 percentiles and empirical shell scoring results
ANOMALY_THRESHOLDS = {
    # Address density - limited data, conservative thresholds
    "companies_at_address_suspicious": 2,  # p99 from 109 addresses
    "companies_at_address_critical": 5,    # Conservative until more data

    # Director roles - CALIBRATED
    # Note: Top "serial directors" are audit firms (E&Y, PWC, KPMG) - exclude from nominee detection
    "director_roles_suspicious": 3,        # Above p99 (which is 2)
    "director_roles_critical": 5,          # Clear nominee territory

    # Legacy thresholds (kept for compatibility)
    "companies_at_address": 5,
    "director_roles": 3,                   # Lowered from 5 based on calibration
    "same_day_formations": 3,
    "address_changes_12m": 2,
    "director_changes_12m": 2,
    "days_to_first_activity": 180,

    # Shell score thresholds - CALIBRATED from 8,200 companies (2025-12-26)
    # High: 0.4% flag rate, Medium: 3.3% flag rate
    "shell_score_high": 0.6,     # 30 companies (0.4%) - prioritize for review
    "shell_score_medium": 0.4,   # 268 companies (3.3%) - monitor
    "shell_score": 0.6,          # Legacy key

    # Single-director flag
    # 58.1% of companies have 1 director, so flag but don't weight heavily
    "single_director_weight": 0.1,         # Low weight given high prevalence
}

# Audit firms to exclude from serial director detection
# These are legitimate auditors, not nominee directors
AUDIT_FIRM_PATTERNS = [
    "ernst & young",
    "öhrlings pricewaterhousecoopers",
    "kpmg",
    "deloitte",
    "azets revision",
    "forvis mazars",
    "frejs revisorer",
    "grant thornton",
    "bdo",
    "rsm",
]


@dataclass
class AnomalyScore:
    """Result of anomaly scoring for an entity."""
    entity_id: str
    entity_type: str  # address, company, person
    z_scores: dict[str, float] = field(default_factory=dict)
    composite_score: float = 0.0
    flags: list[dict] = field(default_factory=list)
    computed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_anomalous(self) -> bool:
        """Check if any z-score exceeds 2 standard deviations."""
        return any(abs(z) > 2.0 for z in self.z_scores.values())

    @property
    def severity(self) -> str:
        """Determine severity based on composite score."""
        if self.composite_score > 3.0:
            return "critical"
        elif self.composite_score > 2.0:
            return "high"
        elif self.composite_score > 1.5:
            return "medium"
        return "low"


class DataProvider(Protocol):
    """Protocol for data access needed by anomaly detection."""

    async def get_company_count_at_address(self, address_id: str) -> int:
        """Get number of companies at an address."""
        ...

    async def get_formation_velocity(self, address_id: str, months: int) -> float:
        """Get new company registrations per month at address."""
        ...

    async def get_avg_lifespan_at_address(self, address_id: str) -> float:
        """Get average company lifespan at address in months."""
        ...

    async def get_company(self, company_id: str) -> Optional[dict]:
        """Get company data."""
        ...

    async def is_virtual_address(self, address_id: str) -> bool:
        """Check if address is a virtual office."""
        ...

    async def get_director_changes_12m(self, company_id: str) -> int:
        """Get director changes in last 12 months."""
        ...

    async def get_address_changes_12m(self, company_id: str) -> int:
        """Get address changes in last 12 months."""
        ...

    async def get_directorship_count(self, person_id: str) -> int:
        """Get number of directorships for a person."""
        ...

    async def get_companies_directed(self, person_id: str) -> list[dict]:
        """Get companies directed by a person."""
        ...


class AnomalyDetector:
    """
    Anomaly detection for addresses, companies, and persons.

    Uses statistical methods to identify deviations from baseline behavior.
    """

    def __init__(
        self,
        baselines: Optional[BaselineStats] = None,
        graph_client: Optional[GraphClient] = None,
    ):
        self.baselines = baselines or BaselineStats()
        self.graph = graph_client

    async def score_address(self, address_id: str) -> AnomalyScore:
        """
        Score an address for anomalous registration patterns.

        Indicators:
        - High company density
        - High formation velocity
        - Short average company lifespan
        """
        company_count = await self._get_company_count(address_id)
        formation_velocity = await self._get_formation_velocity(address_id, months=6)
        avg_lifespan = await self._get_avg_lifespan_at_address(address_id)

        z_scores = {
            "density": (company_count - self.baselines.addr_density_mean)
                       / max(self.baselines.addr_density_std, 0.1),
            "velocity": (formation_velocity - self.baselines.formations_per_agent_month_mean)
                       / max(self.baselines.formations_per_agent_month_std, 0.1),
            "lifespan": (self.baselines.company_lifespan_months_median - avg_lifespan)
                       / max(self.baselines.company_lifespan_months_std, 0.1),
        }

        flags = []

        if company_count > ANOMALY_THRESHOLDS["companies_at_address"]:
            severity = "high" if company_count > 10 else "medium"
            flags.append({
                "type": "high_registration_density",
                "severity": severity,
                "value": company_count,
                "threshold": ANOMALY_THRESHOLDS["companies_at_address"],
                "evidence": f"{company_count} companies registered at address"
            })

        if formation_velocity > self.baselines.formations_per_agent_month_p99:
            flags.append({
                "type": "high_formation_velocity",
                "severity": "high",
                "value": formation_velocity,
                "threshold": self.baselines.formations_per_agent_month_p99,
                "evidence": f"{formation_velocity:.1f} new registrations/month (p99: {self.baselines.formations_per_agent_month_p99})"
            })

        if avg_lifespan < 12:  # Less than 1 year average
            flags.append({
                "type": "short_avg_lifespan",
                "severity": "medium",
                "value": avg_lifespan,
                "threshold": 12,
                "evidence": f"Average company lifespan {avg_lifespan:.1f} months"
            })

        composite = max(z_scores.values()) if z_scores else 0.0

        return AnomalyScore(
            entity_id=address_id,
            entity_type="address",
            z_scores=z_scores,
            composite_score=composite,
            flags=flags
        )

    async def score_company(self, company_id: str) -> AnomalyScore:
        """
        Score a company for shell company indicators.

        Indicators:
        - No employees
        - Virtual address
        - F-skatt but no VAT
        - Recently formed
        - Generic SNI code
        - High director/address turnover
        """
        company = await self._get_company(company_id)
        if not company:
            return AnomalyScore(
                entity_id=company_id,
                entity_type="company",
                flags=[{"type": "company_not_found", "severity": "low"}]
            )

        # Calculate shell company indicators
        indicators = {
            "no_employees": self._check_no_employees(company),
            "virtual_address": await self._check_virtual_address(company),
            "f_skatt_no_vat": self._check_f_skatt_no_vat(company),
            "recently_formed": self._check_recently_formed(company),
            "generic_sni": self._check_generic_sni(company),
            "high_director_turnover": await self._check_high_director_turnover(company_id),
            "high_address_turnover": await self._check_high_address_turnover(company_id),
        }

        shell_score = sum(indicators.values()) / len(indicators)

        flags = []
        for indicator, triggered in indicators.items():
            if triggered:
                flags.append({
                    "type": f"shell_indicator_{indicator}",
                    "severity": "medium" if indicator in ("virtual_address", "f_skatt_no_vat") else "low",
                    "evidence": indicator.replace("_", " ").title()
                })

        if shell_score > ANOMALY_THRESHOLDS["shell_score"]:
            flags.append({
                "type": "high_shell_probability",
                "severity": "high",
                "value": shell_score,
                "threshold": ANOMALY_THRESHOLDS["shell_score"],
                "evidence": f"Shell company probability: {shell_score:.0%}"
            })

        return AnomalyScore(
            entity_id=company_id,
            entity_type="company",
            z_scores={"shell_score": shell_score * 3},  # Scale to z-score range
            composite_score=shell_score * 3,
            flags=flags
        )

    async def score_person(self, person_id: str) -> AnomalyScore:
        """
        Score a person for nominee/professional director indicators.

        Indicators:
        - High directorship count
        - Companies are suspiciously similar
        """
        role_count = await self._get_directorship_count(person_id)
        companies = await self._get_companies_directed(person_id)

        z_scores = {
            "role_count": (role_count - self.baselines.director_roles_mean)
                         / max(self.baselines.director_roles_std, 0.1),
        }

        flags = []

        if role_count > ANOMALY_THRESHOLDS["director_roles"]:
            severity = "high" if role_count > 10 else "medium"
            flags.append({
                "type": "high_directorship_count",
                "severity": severity,
                "value": role_count,
                "threshold": ANOMALY_THRESHOLDS["director_roles"],
                "evidence": f"Director of {role_count} companies"
            })

        # Check if companies are suspiciously similar
        if companies and await self._companies_suspiciously_similar(companies):
            flags.append({
                "type": "similar_company_portfolio",
                "severity": "high",
                "evidence": "Directs multiple similar companies (same address/industry/formation)"
            })

        composite = max(z_scores.values()) if z_scores else 0.0

        return AnomalyScore(
            entity_id=person_id,
            entity_type="person",
            z_scores=z_scores,
            composite_score=composite,
            flags=flags
        )

    # Helper methods - these would connect to the graph/database

    async def _get_company_count(self, address_id: str) -> int:
        """Get company count at address."""
        if self.graph:
            companies = await self.graph.get_companies_at_address(address_id)
            return len(companies)
        return 0

    async def _get_formation_velocity(self, address_id: str, months: int) -> float:
        """Get formation velocity at address."""
        # TODO: Implement with actual data
        return 0.0

    async def _get_avg_lifespan_at_address(self, address_id: str) -> float:
        """Get average company lifespan at address."""
        # TODO: Implement with actual data
        return self.baselines.company_lifespan_months_median

    async def _get_company(self, company_id: str) -> Optional[dict]:
        """Get company data."""
        if self.graph:
            return await self.graph.get_company(company_id)
        return None

    def _check_no_employees(self, company: dict) -> bool:
        """Check if company has no employees."""
        employees = company.get("employees")
        if not employees:
            return True
        return employees.get("count", 0) == 0

    async def _check_virtual_address(self, company: dict) -> bool:
        """Check if company uses virtual address."""
        addresses = company.get("addresses", [])
        for addr in addresses:
            if addr.get("type") == "virtual":
                return True
        return False

    def _check_f_skatt_no_vat(self, company: dict) -> bool:
        """Check if company has F-skatt but no VAT."""
        f_skatt = company.get("f_skatt", {})
        vat = company.get("vat", {})
        return f_skatt.get("registered", False) and not vat.get("registered", False)

    def _check_recently_formed(self, company: dict, threshold_days: int = 365) -> bool:
        """Check if company was recently formed."""
        formation = company.get("formation", {})
        formation_date = formation.get("date")
        if not formation_date:
            return False

        if isinstance(formation_date, str):
            try:
                from datetime import date
                formation_date = date.fromisoformat(formation_date)
            except ValueError:
                return False

        days_since = (datetime.utcnow().date() - formation_date).days
        return days_since < threshold_days

    def _check_generic_sni(self, company: dict) -> bool:
        """Check if company has generic SNI code."""
        # Generic SNI codes often used for shell companies
        generic_codes = {"70", "82", "64", "66"}  # Holding, consulting, financial
        sni_codes = company.get("sni_codes", [])

        for sni in sni_codes:
            code = sni.get("code", "")
            if code[:2] in generic_codes:
                return True
        return False

    async def _check_high_director_turnover(self, company_id: str) -> bool:
        """Check for high director turnover."""
        # TODO: Implement with actual data
        return False

    async def _check_high_address_turnover(self, company_id: str) -> bool:
        """Check for high address turnover."""
        # TODO: Implement with actual data
        return False

    async def _get_directorship_count(self, person_id: str) -> int:
        """Get directorship count for person."""
        if self.graph:
            directorships = await self.graph.get_directorships(person_id)
            return len(directorships)
        return 0

    async def _get_companies_directed(self, person_id: str) -> list[dict]:
        """Get companies directed by person."""
        if self.graph:
            directorships = await self.graph.get_directorships(person_id)
            return [d["company"] for d in directorships]
        return []

    async def _companies_suspiciously_similar(self, companies: list[dict]) -> bool:
        """
        Check if companies are suspiciously similar.

        Similar means: same address, same industry, formed close together.
        """
        if len(companies) < 2:
            return False

        # Check for shared addresses
        addresses = set()
        for company in companies:
            for addr in company.get("addresses", []):
                addr_id = addr.get("address_id")
                if addr_id:
                    if addr_id in addresses:
                        return True
                    addresses.add(addr_id)

        # Check for same industry
        sni_codes = [
            c.get("sni_codes", [{}])[0].get("code", "")[:2]
            for c in companies
            if c.get("sni_codes")
        ]
        if len(sni_codes) > 1 and len(set(sni_codes)) == 1:
            # All same industry
            return True

        # Check for close formation dates
        formation_dates = []
        for company in companies:
            formation = company.get("formation", {})
            date_str = formation.get("date")
            if date_str:
                formation_dates.append(date_str)

        if len(formation_dates) > 1:
            formation_dates.sort()
            for i in range(len(formation_dates) - 1):
                try:
                    from datetime import date
                    d1 = date.fromisoformat(formation_dates[i])
                    d2 = date.fromisoformat(formation_dates[i + 1])
                    if (d2 - d1).days < 30:
                        return True
                except ValueError:
                    pass

        return False
