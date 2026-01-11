"""
Database-backed derivation service.

Connects the derivation calculators to the ontology database tables
for nightly batch computation of derived facts.

Target: <4 hours for full graph recomputation.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any, Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from halo.derivation.risk_score import (
    PersonRiskScorer,
    CompanyRiskScorer,
    AddressRiskScorer,
    RiskScoreResult,
)
from halo.derivation.velocity import DirectorVelocityCalculator, DirectorChange
from halo.derivation.shell_indicators import ShellIndicatorCalculator, ShellIndicators

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# SQL Queries for derivation jobs
FETCH_ACTIVE_PERSONS_QUERY = """
SELECT
    e.id as entity_id,
    e.canonical_name,
    pa.company_count,
    pa.active_directorship_count,
    pa.risk_score as current_risk_score,
    pa.risk_factors
FROM onto_entities e
JOIN onto_person_attributes pa ON pa.entity_id = e.id
WHERE e.entity_type = 'PERSON'
AND e.status = 'ACTIVE'
LIMIT :batch_size OFFSET :offset;
"""

FETCH_PERSON_SHELL_ASSOCIATIONS_QUERY = """
SELECT COUNT(*) as shell_count
FROM onto_facts f
JOIN onto_company_attributes ca ON ca.entity_id = f.object_id
WHERE f.subject_id = :person_id
AND f.predicate = 'DIRECTOR_OF'
AND f.superseded_by IS NULL
AND f.valid_to IS NULL
AND ca.shell_indicators IS NOT NULL
AND array_length(ca.shell_indicators, 1) >= 3;
"""

FETCH_ACTIVE_COMPANIES_QUERY = """
SELECT
    e.id as entity_id,
    e.canonical_name,
    ei.identifier_value as orgnummer,
    ca.status,
    ca.registration_date,
    ca.latest_employees,
    ca.latest_revenue,
    ca.sni_primary,
    ca.director_change_velocity,
    ca.shell_indicators,
    ca.risk_score as current_risk_score
FROM onto_entities e
JOIN onto_company_attributes ca ON ca.entity_id = e.id
LEFT JOIN onto_entity_identifiers ei ON ei.entity_id = e.id AND ei.identifier_type = 'ORGANISATIONSNUMMER'
WHERE e.entity_type = 'COMPANY'
AND e.status = 'ACTIVE'
LIMIT :batch_size OFFSET :offset;
"""

FETCH_COMPANY_ADDRESS_TYPE_QUERY = """
SELECT
    aa.street,
    aa.city
FROM onto_facts f
JOIN onto_address_attributes aa ON aa.entity_id = f.object_id
WHERE f.subject_id = :company_id
AND f.predicate = 'REGISTERED_AT'
AND f.superseded_by IS NULL
LIMIT 1;
"""

FETCH_ACTIVE_ADDRESSES_QUERY = """
SELECT
    e.id as entity_id,
    aa.street,
    aa.postal_code,
    aa.city,
    aa.company_count,
    aa.person_count,
    aa.vulnerable_area,
    aa.vulnerability_level,
    aa.is_registration_hub
FROM onto_entities e
JOIN onto_address_attributes aa ON aa.entity_id = e.id
WHERE e.entity_type = 'ADDRESS'
AND e.status = 'ACTIVE'
LIMIT :batch_size OFFSET :offset;
"""

FETCH_DIRECTOR_CHANGES_QUERY = """
SELECT
    f.object_id as company_id,
    f.subject_id as person_id,
    e.canonical_name as person_name,
    f.valid_from,
    f.valid_to,
    f.relationship_attributes->>'role_title' as role
FROM onto_facts f
JOIN onto_entities e ON e.id = f.subject_id
WHERE f.predicate = 'DIRECTOR_OF'
AND f.valid_from >= :start_date
ORDER BY f.valid_from;
"""

UPDATE_PERSON_RISK_SCORE_QUERY = """
UPDATE onto_person_attributes
SET risk_score = :risk_score,
    risk_factors = :risk_factors,
    updated_at = NOW()
WHERE entity_id = :entity_id;
"""

UPDATE_COMPANY_ATTRIBUTES_QUERY = """
UPDATE onto_company_attributes
SET risk_score = :risk_score,
    risk_factors = :risk_factors,
    shell_indicators = :shell_indicators,
    director_change_velocity = :velocity,
    updated_at = NOW()
WHERE entity_id = :entity_id;
"""

UPDATE_ADDRESS_ATTRIBUTES_QUERY = """
UPDATE onto_address_attributes
SET company_count = :company_count,
    person_count = :person_count,
    is_registration_hub = :is_hub,
    updated_at = NOW()
WHERE entity_id = :entity_id;
"""

LOG_DERIVATION_RUN_QUERY = """
INSERT INTO onto_derivation_runs (id, rule_id, started_at, completed_at, entities_processed, status, error_message)
VALUES (:id, :rule_id, :started_at, :completed_at, :entities_processed, :status, :error_message);
"""

GET_DERIVATION_RULE_ID_QUERY = """
SELECT id FROM onto_derivation_rules WHERE rule_name = :rule_name AND active = TRUE;
"""


@dataclass
class DerivationJobStats:
    """Statistics from a derivation job run."""

    job_type: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    entities_processed: int = 0
    entities_updated: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class DerivationDBService:
    """
    Database-backed derivation service.

    Runs derivation jobs against the ontology tables (onto_*).
    """

    BATCH_SIZE = 1000

    def __init__(self, session: "AsyncSession"):
        self.session = session
        self.person_scorer = PersonRiskScorer()
        self.company_scorer = CompanyRiskScorer()
        self.address_scorer = AddressRiskScorer()
        self.velocity_calculator = DirectorVelocityCalculator()
        self.shell_calculator = ShellIndicatorCalculator()

    async def run_full_derivation(self) -> dict[str, DerivationJobStats]:
        """
        Run full nightly derivation job.

        Sequence:
        1. Load director changes for velocity calculation
        2. Compute company shell indicators
        3. Compute company risk scores
        4. Compute person risk scores
        5. Compute address statistics

        Returns:
            Dictionary of stats by job type
        """
        logger.info("Starting full derivation job")
        stats = {}

        # 1. Load director changes for velocity
        await self._load_director_changes()

        # 2. Company derivations (shell indicators + velocity + risk)
        stats["company_derivation"] = await self.compute_company_derivations()

        # 3. Person risk scores
        stats["person_risk"] = await self.compute_person_risk_scores()

        # 4. Address statistics
        stats["address_stats"] = await self.compute_address_statistics()

        total_entities = sum(s.entities_processed for s in stats.values())
        total_updated = sum(s.entities_updated for s in stats.values())

        logger.info(
            f"Full derivation complete: {total_entities} entities processed, "
            f"{total_updated} updated"
        )

        return stats

    async def _load_director_changes(self) -> None:
        """Load director changes from database for velocity calculation."""
        from sqlalchemy import text
        from datetime import timedelta

        # Get changes from last 2 years
        start_date = date.today() - timedelta(days=365 * 2)

        result = await self.session.execute(
            text(FETCH_DIRECTOR_CHANGES_QUERY),
            {"start_date": start_date}
        )
        rows = result.fetchall()

        self.velocity_calculator.clear()

        for row in rows:
            # A fact with valid_from creates an "added" event
            self.velocity_calculator.add_change(DirectorChange(
                company_id=row.company_id,
                person_id=row.person_id,
                person_name=row.person_name or "",
                change_type="added",
                change_date=row.valid_from,
                role=row.role or "director",
            ))

            # If valid_to is set, that's a "removed" event
            if row.valid_to:
                self.velocity_calculator.add_change(DirectorChange(
                    company_id=row.company_id,
                    person_id=row.person_id,
                    person_name=row.person_name or "",
                    change_type="removed",
                    change_date=row.valid_to,
                    role=row.role or "director",
                ))

        logger.info(f"Loaded {len(rows)} director change records")

    async def compute_company_derivations(self) -> DerivationJobStats:
        """
        Compute shell indicators, velocity, and risk for all companies.
        """
        from sqlalchemy import text

        stats = DerivationJobStats(
            job_type="company_derivation",
            started_at=datetime.utcnow(),
        )

        offset = 0
        while True:
            result = await self.session.execute(
                text(FETCH_ACTIVE_COMPANIES_QUERY),
                {"batch_size": self.BATCH_SIZE, "offset": offset}
            )
            rows = result.fetchall()

            if not rows:
                break

            for row in rows:
                try:
                    # Calculate velocity
                    velocity_result = self.velocity_calculator.calculate_company_velocity(
                        row.entity_id
                    )

                    # Calculate shell indicators
                    # Get address type
                    addr_result = await self.session.execute(
                        text(FETCH_COMPANY_ADDRESS_TYPE_QUERY),
                        {"company_id": row.entity_id}
                    )
                    addr_row = addr_result.fetchone()
                    address_type = None
                    if addr_row and addr_row.street:
                        addr_lower = addr_row.street.lower()
                        if "c/o" in addr_lower or "box" in addr_lower:
                            address_type = "c_o"

                    shell_indicators = self.shell_calculator.calculate(
                        company_id=row.entity_id,
                        orgnummer=row.orgnummer or "",
                        company_name=row.canonical_name or "",
                        employees=row.latest_employees,
                        revenue=row.latest_revenue,
                        sni_code=row.sni_primary,
                        registration_date=row.registration_date,
                        address_type=address_type,
                        director_velocity=velocity_result.velocity,
                    )

                    # Calculate company risk
                    risk_result = self.company_scorer.compute(
                        company_id=row.entity_id,
                        employees=row.latest_employees,
                        revenue=row.latest_revenue,
                        sni_code=row.sni_primary,
                        registration_date=row.registration_date,
                        address_type=address_type,
                        director_velocity=velocity_result.velocity,
                    )

                    # Update company attributes
                    await self.session.execute(
                        text(UPDATE_COMPANY_ATTRIBUTES_QUERY),
                        {
                            "entity_id": row.entity_id,
                            "risk_score": risk_result.risk_score,
                            "risk_factors": risk_result.factors.to_list(),
                            "shell_indicators": shell_indicators.to_list(),
                            "velocity": velocity_result.velocity,
                        }
                    )
                    stats.entities_updated += 1

                except Exception as e:
                    stats.errors.append(f"Company {row.entity_id}: {str(e)}")
                    logger.error(f"Error processing company {row.entity_id}: {e}")

                stats.entities_processed += 1

            await self.session.commit()
            offset += self.BATCH_SIZE

            logger.debug(f"Processed {stats.entities_processed} companies")

        stats.completed_at = datetime.utcnow()
        logger.info(
            f"Company derivation complete: {stats.entities_processed} processed, "
            f"{stats.entities_updated} updated in {stats.duration_seconds:.1f}s"
        )

        return stats

    async def compute_person_risk_scores(self) -> DerivationJobStats:
        """Compute risk scores for all persons."""
        from sqlalchemy import text

        stats = DerivationJobStats(
            job_type="person_risk",
            started_at=datetime.utcnow(),
        )

        offset = 0
        while True:
            result = await self.session.execute(
                text(FETCH_ACTIVE_PERSONS_QUERY),
                {"batch_size": self.BATCH_SIZE, "offset": offset}
            )
            rows = result.fetchall()

            if not rows:
                break

            for row in rows:
                try:
                    # Get shell company associations
                    shell_result = await self.session.execute(
                        text(FETCH_PERSON_SHELL_ASSOCIATIONS_QUERY),
                        {"person_id": row.entity_id}
                    )
                    shell_row = shell_result.fetchone()
                    shell_count = shell_row.shell_count if shell_row else 0

                    # Calculate person risk
                    risk_result = self.person_scorer.compute(
                        person_id=row.entity_id,
                        company_count=row.company_count or 0,
                        active_directorship_count=row.active_directorship_count or 0,
                        shell_company_count=shell_count,
                    )

                    # Update person attributes
                    await self.session.execute(
                        text(UPDATE_PERSON_RISK_SCORE_QUERY),
                        {
                            "entity_id": row.entity_id,
                            "risk_score": risk_result.risk_score,
                            "risk_factors": risk_result.factors.to_list(),
                        }
                    )
                    stats.entities_updated += 1

                except Exception as e:
                    stats.errors.append(f"Person {row.entity_id}: {str(e)}")
                    logger.error(f"Error processing person {row.entity_id}: {e}")

                stats.entities_processed += 1

            await self.session.commit()
            offset += self.BATCH_SIZE

        stats.completed_at = datetime.utcnow()
        logger.info(
            f"Person risk computation complete: {stats.entities_processed} processed, "
            f"{stats.entities_updated} updated in {stats.duration_seconds:.1f}s"
        )

        return stats

    async def compute_address_statistics(self) -> DerivationJobStats:
        """Compute address statistics (company count, hub detection)."""
        from sqlalchemy import text

        stats = DerivationJobStats(
            job_type="address_stats",
            started_at=datetime.utcnow(),
        )

        # Query to count companies at each address
        count_query = """
        SELECT
            f.object_id as address_id,
            COUNT(DISTINCT f.subject_id) as company_count,
            COUNT(DISTINCT dir.subject_id) as person_count
        FROM onto_facts f
        LEFT JOIN onto_facts dir ON dir.object_id = f.subject_id
            AND dir.predicate = 'DIRECTOR_OF'
            AND dir.superseded_by IS NULL
        WHERE f.predicate = 'REGISTERED_AT'
        AND f.superseded_by IS NULL
        GROUP BY f.object_id
        """

        result = await self.session.execute(text(count_query))
        rows = result.fetchall()

        for row in rows:
            try:
                is_hub = row.company_count >= 10 and row.person_count < row.company_count / 2

                await self.session.execute(
                    text(UPDATE_ADDRESS_ATTRIBUTES_QUERY),
                    {
                        "entity_id": row.address_id,
                        "company_count": row.company_count,
                        "person_count": row.person_count,
                        "is_hub": is_hub,
                    }
                )
                stats.entities_updated += 1

            except Exception as e:
                stats.errors.append(f"Address {row.address_id}: {str(e)}")

            stats.entities_processed += 1

        await self.session.commit()

        stats.completed_at = datetime.utcnow()
        logger.info(
            f"Address stats complete: {stats.entities_processed} processed, "
            f"{stats.entities_updated} updated"
        )

        return stats

    async def log_derivation_run(
        self,
        rule_name: str,
        stats: DerivationJobStats,
    ) -> None:
        """Log a derivation run to the database."""
        from sqlalchemy import text

        # Get rule ID
        result = await self.session.execute(
            text(GET_DERIVATION_RULE_ID_QUERY),
            {"rule_name": rule_name}
        )
        row = result.fetchone()

        if not row:
            logger.warning(f"Derivation rule '{rule_name}' not found")
            return

        status = "COMPLETED" if not stats.errors else "COMPLETED_WITH_ERRORS"

        await self.session.execute(
            text(LOG_DERIVATION_RUN_QUERY),
            {
                "id": uuid4(),
                "rule_id": row.id,
                "started_at": stats.started_at,
                "completed_at": stats.completed_at,
                "entities_processed": stats.entities_processed,
                "status": status,
                "error_message": "; ".join(stats.errors[:10]) if stats.errors else None,
            }
        )
        await self.session.commit()


async def run_nightly_derivation(session: "AsyncSession") -> dict[str, Any]:
    """
    Convenience function to run the full nightly derivation job.

    Args:
        session: SQLAlchemy async session

    Returns:
        Summary statistics dictionary
    """
    service = DerivationDBService(session)
    stats = await service.run_full_derivation()

    # Log runs
    for job_type, job_stats in stats.items():
        await service.log_derivation_run(job_type, job_stats)

    return {
        job_type: {
            "processed": s.entities_processed,
            "updated": s.entities_updated,
            "duration_seconds": s.duration_seconds,
            "errors": len(s.errors),
        }
        for job_type, s in stats.items()
    }
