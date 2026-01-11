"""
Shell company network detection.

Detects patterns of shell companies:
- Persons directing multiple low-activity companies
- Registration mills (addresses with many companies)
- Circular ownership structures

Supports both:
1. In-memory detection (for testing/small datasets)
2. Database-backed detection (PostgreSQL with ontology tables)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class ShellNetworkParams:
    """Parameters for shell network detection."""

    min_companies: int = 3  # Minimum companies per person
    max_employees: int = 2  # Maximum employees per company
    max_revenue: int = 500_000  # Maximum revenue per company (SEK)
    include_dissolved: bool = False  # Include dissolved companies
    min_address_density: int = 5  # Minimum companies per address for mill detection
    lookback_days: int = 365  # How far back to look for formations


@dataclass
class ShellCompany:
    """A company identified as potentially shell."""

    id: UUID
    orgnummer: str
    name: str
    status: str
    registration_date: Optional[datetime] = None
    employees: Optional[int] = None
    revenue: Optional[int] = None
    address: Optional[str] = None
    shell_indicators: list[str] = field(default_factory=list)
    risk_score: float = 0.0


@dataclass
class ShellNetworkMatch:
    """A detected shell company network."""

    person_id: UUID
    person_name: str
    companies: list[ShellCompany]
    company_ids: list[UUID] = field(default_factory=list)
    company_names: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    indicators: list[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.utcnow)
    total_companies: int = 0
    active_companies: int = 0
    total_revenue: int = 0
    common_addresses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "person_id": str(self.person_id),
            "person_name": self.person_name,
            "company_ids": [str(c) for c in self.company_ids],
            "company_names": self.company_names,
            "risk_score": self.risk_score,
            "indicators": self.indicators,
            "detected_at": self.detected_at.isoformat(),
            "total_companies": self.total_companies,
            "active_companies": self.active_companies,
            "total_revenue": self.total_revenue,
            "common_addresses": self.common_addresses,
        }


@dataclass
class RegistrationMillMatch:
    """A detected registration mill (address with many companies)."""

    address_id: UUID
    address: str
    postal_code: str
    city: str
    company_count: int
    companies: list[ShellCompany]
    shared_directors: list[tuple[UUID, str]]  # (person_id, name)
    risk_score: float = 0.0
    indicators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "address_id": str(self.address_id),
            "address": self.address,
            "postal_code": self.postal_code,
            "city": self.city,
            "company_count": self.company_count,
            "shared_directors": [
                {"id": str(d[0]), "name": d[1]} for d in self.shared_directors
            ],
            "risk_score": self.risk_score,
            "indicators": self.indicators,
        }


class ShellNetworkDetector:
    """
    Detect shell company network patterns.

    Works with either:
    1. Direct database queries (PostgreSQL with entity tables)
    2. In-memory graph (for testing or small datasets)
    """

    # Shell company indicators and their weights
    SHELL_INDICATORS = {
        "no_employees": 0.2,
        "minimal_revenue": 0.15,
        "generic_sni_code": 0.15,  # Holding company, consulting, etc.
        "recently_formed": 0.1,
        "no_physical_address": 0.2,
        "foreign_director": 0.1,
        "multiple_companies_same_director": 0.3,
        "rapid_director_changes": 0.2,
        "no_annual_reports": 0.15,
        "c_o_address": 0.1,  # c/o address
    }

    # SNI codes commonly associated with shell companies
    SHELL_SNI_CODES = {
        "64200": "Holding company",
        "70100": "Head office activities",
        "70220": "Business and management consultancy",
        "82990": "Other business support service activities",
        "46900": "Non-specialized wholesale trade",
    }

    def __init__(self):
        self._persons: dict[UUID, dict] = {}
        self._companies: dict[UUID, dict] = {}
        self._addresses: dict[UUID, dict] = {}
        self._directorships: list[tuple[UUID, UUID]] = []  # (person_id, company_id)
        self._registrations: list[tuple[UUID, UUID]] = []  # (company_id, address_id)

    def add_person(self, person_id: UUID, name: str, **attributes) -> None:
        """Add a person to the detector."""
        self._persons[person_id] = {"id": person_id, "name": name, **attributes}

    def add_company(self, company_id: UUID, name: str, orgnummer: str, **attributes) -> None:
        """Add a company to the detector."""
        self._companies[company_id] = {
            "id": company_id,
            "name": name,
            "orgnummer": orgnummer,
            **attributes,
        }

    def add_address(self, address_id: UUID, address: str, **attributes) -> None:
        """Add an address to the detector."""
        self._addresses[address_id] = {"id": address_id, "address": address, **attributes}

    def add_directorship(self, person_id: UUID, company_id: UUID) -> None:
        """Add a directorship relationship."""
        self._directorships.append((person_id, company_id))

    def add_registration(self, company_id: UUID, address_id: UUID) -> None:
        """Add a company registration at address."""
        self._registrations.append((company_id, address_id))

    def detect(self, params: Optional[ShellNetworkParams] = None) -> list[ShellNetworkMatch]:
        """
        Detect shell company networks.

        Finds persons directing multiple shell-like companies.
        """
        params = params or ShellNetworkParams()
        matches = []

        # Build person -> companies mapping
        person_companies: dict[UUID, list[UUID]] = {}
        for person_id, company_id in self._directorships:
            if person_id not in person_companies:
                person_companies[person_id] = []
            person_companies[person_id].append(company_id)

        # Build company -> address mapping
        company_addresses: dict[UUID, UUID] = {}
        for company_id, address_id in self._registrations:
            company_addresses[company_id] = address_id

        # Find persons with multiple companies meeting criteria
        for person_id, company_ids in person_companies.items():
            if len(company_ids) < params.min_companies:
                continue

            person_data = self._persons.get(person_id, {})
            shell_companies = []
            addresses_used = []

            for company_id in company_ids:
                company_data = self._companies.get(company_id, {})

                # Check shell criteria
                if not self._is_shell_like(company_data, params):
                    continue

                indicators = self._get_shell_indicators(company_data)
                risk = self._calculate_company_risk(indicators)

                shell = ShellCompany(
                    id=company_id,
                    orgnummer=company_data.get("orgnummer", ""),
                    name=company_data.get("name", ""),
                    status=company_data.get("status", "unknown"),
                    registration_date=company_data.get("registration_date"),
                    employees=company_data.get("employees"),
                    revenue=company_data.get("revenue"),
                    shell_indicators=indicators,
                    risk_score=risk,
                )
                shell_companies.append(shell)

                # Track address
                if company_id in company_addresses:
                    addr_id = company_addresses[company_id]
                    addr_data = self._addresses.get(addr_id, {})
                    addresses_used.append(addr_data.get("address", ""))

            if len(shell_companies) >= params.min_companies:
                # Calculate overall risk
                avg_risk = sum(c.risk_score for c in shell_companies) / len(shell_companies)

                # Count address reuse
                address_counts = {}
                for addr in addresses_used:
                    address_counts[addr] = address_counts.get(addr, 0) + 1

                common_addresses = [
                    addr for addr, count in address_counts.items() if count > 1
                ]

                indicators = [
                    f"directs_{len(shell_companies)}_shell_companies",
                ]
                if common_addresses:
                    indicators.append(f"uses_{len(common_addresses)}_shared_addresses")

                match = ShellNetworkMatch(
                    person_id=person_id,
                    person_name=person_data.get("name", ""),
                    companies=shell_companies,
                    company_ids=[c.id for c in shell_companies],
                    company_names=[c.name for c in shell_companies],
                    risk_score=min(avg_risk + 0.1 * len(shell_companies), 1.0),
                    indicators=indicators,
                    total_companies=len(shell_companies),
                    active_companies=sum(
                        1 for c in shell_companies if c.status == "active"
                    ),
                    total_revenue=sum(c.revenue or 0 for c in shell_companies),
                    common_addresses=common_addresses,
                )
                matches.append(match)

        # Sort by risk score
        matches.sort(key=lambda m: m.risk_score, reverse=True)

        logger.info(f"Detected {len(matches)} shell networks")
        return matches

    def detect_registration_mills(
        self, params: Optional[ShellNetworkParams] = None
    ) -> list[RegistrationMillMatch]:
        """
        Detect registration mills (addresses with many companies).
        """
        params = params or ShellNetworkParams()
        matches = []

        # Build address -> companies mapping
        address_companies: dict[UUID, list[UUID]] = {}
        for company_id, address_id in self._registrations:
            if address_id not in address_companies:
                address_companies[address_id] = []
            address_companies[address_id].append(company_id)

        # Build company -> directors mapping
        company_directors: dict[UUID, list[UUID]] = {}
        for person_id, company_id in self._directorships:
            if company_id not in company_directors:
                company_directors[company_id] = []
            company_directors[company_id].append(person_id)

        for address_id, company_ids in address_companies.items():
            if len(company_ids) < params.min_address_density:
                continue

            address_data = self._addresses.get(address_id, {})
            shell_companies = []
            all_directors: dict[UUID, str] = {}

            for company_id in company_ids:
                company_data = self._companies.get(company_id, {})

                indicators = self._get_shell_indicators(company_data)
                risk = self._calculate_company_risk(indicators)

                shell = ShellCompany(
                    id=company_id,
                    orgnummer=company_data.get("orgnummer", ""),
                    name=company_data.get("name", ""),
                    status=company_data.get("status", "unknown"),
                    shell_indicators=indicators,
                    risk_score=risk,
                )
                shell_companies.append(shell)

                # Track directors
                for director_id in company_directors.get(company_id, []):
                    person_data = self._persons.get(director_id, {})
                    all_directors[director_id] = person_data.get("name", "")

            # Find shared directors (directors with 2+ companies at this address)
            director_company_count: dict[UUID, int] = {}
            for company_id in company_ids:
                for director_id in company_directors.get(company_id, []):
                    director_company_count[director_id] = (
                        director_company_count.get(director_id, 0) + 1
                    )

            shared_directors = [
                (d_id, all_directors.get(d_id, ""))
                for d_id, count in director_company_count.items()
                if count >= 2
            ]

            indicators = [
                f"{len(company_ids)}_companies_at_address",
            ]
            if shared_directors:
                indicators.append(f"{len(shared_directors)}_shared_directors")

            risk = min(
                0.3
                + 0.05 * len(company_ids)
                + 0.1 * len(shared_directors),
                1.0,
            )

            match = RegistrationMillMatch(
                address_id=address_id,
                address=address_data.get("address", ""),
                postal_code=address_data.get("postal_code", ""),
                city=address_data.get("city", ""),
                company_count=len(company_ids),
                companies=shell_companies,
                shared_directors=shared_directors,
                risk_score=risk,
                indicators=indicators,
            )
            matches.append(match)

        matches.sort(key=lambda m: m.risk_score, reverse=True)

        logger.info(f"Detected {len(matches)} registration mills")
        return matches

    def _is_shell_like(self, company: dict, params: ShellNetworkParams) -> bool:
        """Check if company meets shell-like criteria."""
        # Check employees
        employees = company.get("employees")
        if employees is not None and employees > params.max_employees:
            return False

        # Check revenue
        revenue = company.get("revenue")
        if revenue is not None and revenue > params.max_revenue:
            return False

        # Check status
        status = company.get("status", "").lower()
        if not params.include_dissolved and status in [
            "dissolved",
            "bankrupt",
            "konkurs",
            "avregistrerad",
        ]:
            return False

        return True

    def _get_shell_indicators(self, company: dict) -> list[str]:
        """Get shell company indicators for a company."""
        indicators = []

        if company.get("employees") in [None, 0]:
            indicators.append("no_employees")

        if company.get("revenue", 0) < 100_000:
            indicators.append("minimal_revenue")

        sni = company.get("sni_code", "")
        if sni in self.SHELL_SNI_CODES:
            indicators.append("generic_sni_code")

        address = company.get("address", "").lower()
        if "c/o" in address or "box" in address:
            indicators.append("c_o_address")

        if not company.get("has_annual_report", True):
            indicators.append("no_annual_reports")

        return indicators

    def _calculate_company_risk(self, indicators: list[str]) -> float:
        """Calculate risk score from indicators."""
        score = 0.0
        for indicator in indicators:
            score += self.SHELL_INDICATORS.get(indicator, 0.0)
        return min(score, 1.0)

    def clear(self) -> None:
        """Clear all data."""
        self._persons.clear()
        self._companies.clear()
        self._addresses.clear()
        self._directorships.clear()
        self._registrations.clear()


# SQL Queries for database-backed detection (uses onto_ prefixed tables)
SHELL_NETWORK_QUERY = """
-- Find persons directing multiple low-activity companies
-- From Archeron Ontology Spec v2
WITH director_companies AS (
    SELECT
        f.subject_id as person_id,
        f.object_id as company_id
    FROM onto_facts f
    WHERE f.predicate = 'DIRECTOR_OF'
    AND f.valid_to IS NULL
    AND f.superseded_by IS NULL
),
company_stats AS (
    SELECT
        dc.person_id,
        dc.company_id,
        ca.status,
        ca.latest_employees,
        ca.latest_revenue,
        ca.shell_indicators,
        ca.sni_primary
    FROM director_companies dc
    JOIN onto_company_attributes ca ON ca.entity_id = dc.company_id
    WHERE ca.status = 'ACTIVE'
    AND (ca.latest_employees IS NULL OR ca.latest_employees < :max_employees)
    AND (ca.latest_revenue IS NULL OR ca.latest_revenue < :max_revenue)
)
SELECT
    cs.person_id,
    e.canonical_name as person_name,
    array_agg(cs.company_id) as shell_company_ids,
    count(*) as shell_count,
    sum(cs.latest_revenue) as total_revenue,
    array_agg(DISTINCT cs.sni_primary) FILTER (WHERE cs.sni_primary IS NOT NULL) as sni_codes
FROM company_stats cs
JOIN onto_entities e ON e.id = cs.person_id
GROUP BY cs.person_id, e.canonical_name
HAVING count(*) >= :min_companies
ORDER BY count(*) DESC
LIMIT :limit;
"""

SHELL_COMPANY_DETAILS_QUERY = """
-- Get details for shell companies
SELECT
    e.id,
    e.canonical_name as name,
    ei.identifier_value as orgnummer,
    ca.status,
    ca.registration_date,
    ca.latest_employees as employees,
    ca.latest_revenue as revenue,
    ca.shell_indicators,
    ca.risk_score,
    aa.street || ' ' || COALESCE(aa.street_number, '') || ', ' || aa.postal_code || ' ' || aa.city as address
FROM onto_entities e
LEFT JOIN onto_entity_identifiers ei ON ei.entity_id = e.id AND ei.identifier_type = 'ORGANISATIONSNUMMER'
LEFT JOIN onto_company_attributes ca ON ca.entity_id = e.id
LEFT JOIN onto_facts f ON f.subject_id = e.id AND f.predicate = 'REGISTERED_AT' AND f.superseded_by IS NULL
LEFT JOIN onto_address_attributes aa ON aa.entity_id = f.object_id
WHERE e.id = ANY(:company_ids);
"""

REGISTRATION_MILL_QUERY = """
-- Find addresses with many companies (registration mills)
WITH company_registrations AS (
    SELECT
        f.object_id as address_id,
        f.subject_id as company_id
    FROM onto_facts f
    WHERE f.predicate = 'REGISTERED_AT'
    AND f.valid_to IS NULL
    AND f.superseded_by IS NULL
),
address_company_counts AS (
    SELECT
        cr.address_id,
        aa.street,
        aa.street_number,
        aa.postal_code,
        aa.city,
        count(DISTINCT cr.company_id) as company_count,
        array_agg(cr.company_id) as company_ids
    FROM company_registrations cr
    JOIN onto_address_attributes aa ON aa.entity_id = cr.address_id
    GROUP BY cr.address_id, aa.street, aa.street_number, aa.postal_code, aa.city
    HAVING count(DISTINCT cr.company_id) >= :min_companies
)
SELECT
    acc.address_id,
    acc.street || ' ' || COALESCE(acc.street_number, '') as address,
    acc.postal_code,
    acc.city,
    acc.company_count,
    acc.company_ids
FROM address_company_counts acc
ORDER BY acc.company_count DESC
LIMIT :limit;
"""

SHARED_DIRECTORS_QUERY = """
-- Find directors shared across companies at an address
WITH address_companies AS (
    SELECT f.subject_id as company_id
    FROM onto_facts f
    WHERE f.predicate = 'REGISTERED_AT'
    AND f.object_id = :address_id
    AND f.superseded_by IS NULL
),
company_directors AS (
    SELECT
        f.subject_id as director_id,
        f.object_id as company_id,
        e.canonical_name as director_name
    FROM onto_facts f
    JOIN onto_entities e ON e.id = f.subject_id
    WHERE f.predicate = 'DIRECTOR_OF'
    AND f.object_id IN (SELECT company_id FROM address_companies)
    AND f.superseded_by IS NULL
)
SELECT
    director_id,
    director_name,
    count(DISTINCT company_id) as company_count
FROM company_directors
GROUP BY director_id, director_name
HAVING count(DISTINCT company_id) >= 2
ORDER BY count(DISTINCT company_id) DESC;
"""


@dataclass
class ShellNetworkDBResult:
    """Result from database shell network query."""

    person_id: UUID
    person_name: str
    shell_company_ids: list[UUID]
    shell_count: int
    total_revenue: Optional[int] = None
    sni_codes: list[str] = field(default_factory=list)
    companies: list[ShellCompany] = field(default_factory=list)
    risk_score: float = 0.0

    def to_match(self) -> ShellNetworkMatch:
        """Convert to ShellNetworkMatch for API compatibility."""
        return ShellNetworkMatch(
            person_id=self.person_id,
            person_name=self.person_name,
            companies=self.companies,
            company_ids=self.shell_company_ids,
            company_names=[c.name for c in self.companies],
            risk_score=self.risk_score,
            indicators=[f"directs_{self.shell_count}_shell_companies"],
            total_companies=self.shell_count,
            active_companies=len([c for c in self.companies if c.status == "ACTIVE"]),
            total_revenue=self.total_revenue or 0,
        )


class ShellNetworkQueryService:
    """
    Database-backed shell network detection.

    Uses the ontology tables (onto_facts, onto_entities, onto_company_attributes)
    to detect shell company networks with the SQL queries from the spec.

    Target performance: <10s for pattern matching on full graph.
    """

    def __init__(self, session: "AsyncSession"):
        self.session = session

    async def detect_shell_networks(
        self,
        params: Optional[ShellNetworkParams] = None,
        limit: int = 100,
    ) -> list[ShellNetworkDBResult]:
        """
        Detect shell company networks from the database.

        Args:
            params: Detection parameters
            limit: Maximum number of results

        Returns:
            List of shell network detections with company details
        """
        from sqlalchemy import text

        params = params or ShellNetworkParams()

        # Execute shell network query
        result = await self.session.execute(
            text(SHELL_NETWORK_QUERY),
            {
                "min_companies": params.min_companies,
                "max_employees": params.max_employees,
                "max_revenue": params.max_revenue,
                "limit": limit,
            }
        )
        rows = result.fetchall()

        if not rows:
            logger.info("No shell networks detected")
            return []

        results = []
        for row in rows:
            # Fetch company details for this network
            company_ids = row.shell_company_ids

            details_result = await self.session.execute(
                text(SHELL_COMPANY_DETAILS_QUERY),
                {"company_ids": company_ids}
            )
            company_rows = details_result.fetchall()

            companies = []
            for c in company_rows:
                shell_indicators = c.shell_indicators or []
                risk = self._calculate_company_risk(shell_indicators)

                companies.append(ShellCompany(
                    id=c.id,
                    orgnummer=c.orgnummer or "",
                    name=c.name or "",
                    status=c.status or "unknown",
                    registration_date=c.registration_date,
                    employees=c.employees,
                    revenue=c.revenue,
                    address=c.address,
                    shell_indicators=shell_indicators,
                    risk_score=risk,
                ))

            # Calculate overall risk
            avg_risk = sum(c.risk_score for c in companies) / len(companies) if companies else 0.0
            network_risk = min(avg_risk + 0.1 * row.shell_count, 1.0)

            results.append(ShellNetworkDBResult(
                person_id=row.person_id,
                person_name=row.person_name or "",
                shell_company_ids=company_ids,
                shell_count=row.shell_count,
                total_revenue=row.total_revenue,
                sni_codes=row.sni_codes or [],
                companies=companies,
                risk_score=network_risk,
            ))

        logger.info(f"Detected {len(results)} shell networks from database")
        return results

    async def detect_registration_mills(
        self,
        params: Optional[ShellNetworkParams] = None,
        limit: int = 100,
    ) -> list[RegistrationMillMatch]:
        """
        Detect registration mills (addresses with many companies).

        Args:
            params: Detection parameters
            limit: Maximum number of results

        Returns:
            List of registration mill detections
        """
        from sqlalchemy import text

        params = params or ShellNetworkParams()

        # Execute registration mill query
        result = await self.session.execute(
            text(REGISTRATION_MILL_QUERY),
            {
                "min_companies": params.min_address_density,
                "limit": limit,
            }
        )
        rows = result.fetchall()

        if not rows:
            logger.info("No registration mills detected")
            return []

        results = []
        for row in rows:
            # Get shared directors for this address
            directors_result = await self.session.execute(
                text(SHARED_DIRECTORS_QUERY),
                {"address_id": row.address_id}
            )
            director_rows = directors_result.fetchall()

            shared_directors = [
                (d.director_id, d.director_name)
                for d in director_rows
            ]

            # Get company details
            company_ids = row.company_ids
            details_result = await self.session.execute(
                text(SHELL_COMPANY_DETAILS_QUERY),
                {"company_ids": company_ids}
            )
            company_rows = details_result.fetchall()

            companies = []
            for c in company_rows:
                companies.append(ShellCompany(
                    id=c.id,
                    orgnummer=c.orgnummer or "",
                    name=c.name or "",
                    status=c.status or "unknown",
                    shell_indicators=c.shell_indicators or [],
                    risk_score=c.risk_score or 0.0,
                ))

            # Calculate risk
            risk = min(
                0.3
                + 0.05 * row.company_count
                + 0.1 * len(shared_directors),
                1.0,
            )

            indicators = [
                f"{row.company_count}_companies_at_address",
            ]
            if shared_directors:
                indicators.append(f"{len(shared_directors)}_shared_directors")

            results.append(RegistrationMillMatch(
                address_id=row.address_id,
                address=row.address or "",
                postal_code=row.postal_code or "",
                city=row.city or "",
                company_count=row.company_count,
                companies=companies,
                shared_directors=shared_directors,
                risk_score=risk,
                indicators=indicators,
            ))

        logger.info(f"Detected {len(results)} registration mills from database")
        return results

    def _calculate_company_risk(self, indicators: list[str]) -> float:
        """Calculate risk score from shell indicators."""
        score = 0.0
        for indicator in indicators:
            score += ShellNetworkDetector.SHELL_INDICATORS.get(indicator, 0.0)
        return min(score, 1.0)


async def detect_shell_networks_db(
    session: "AsyncSession",
    params: Optional[ShellNetworkParams] = None,
    limit: int = 100,
) -> list[ShellNetworkMatch]:
    """
    Convenience function for database-backed shell network detection.

    Args:
        session: SQLAlchemy async session
        params: Detection parameters
        limit: Maximum results

    Returns:
        List of ShellNetworkMatch objects
    """
    service = ShellNetworkQueryService(session)
    results = await service.detect_shell_networks(params, limit)
    return [r.to_match() for r in results]


async def detect_registration_mills_db(
    session: "AsyncSession",
    params: Optional[ShellNetworkParams] = None,
    limit: int = 100,
) -> list[RegistrationMillMatch]:
    """
    Convenience function for database-backed registration mill detection.

    Args:
        session: SQLAlchemy async session
        params: Detection parameters
        limit: Maximum results

    Returns:
        List of RegistrationMillMatch objects
    """
    service = ShellNetworkQueryService(session)
    return await service.detect_registration_mills(params, limit)
