"""
Derivation job scheduler.

Orchestrates nightly batch jobs that recompute derived facts:
- Risk scores for all entities
- Network clusters
- Shell indicators
- Director velocity
- Address statistics
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class DerivationRuleType(str, Enum):
    """Types of derivation rules."""

    RISK_SCORE = "RISK_SCORE"
    NETWORK_CLUSTER = "NETWORK_CLUSTER"
    SHELL_INDICATOR = "SHELL_INDICATOR"
    VELOCITY = "VELOCITY"
    ADDRESS_STATS = "ADDRESS_STATS"


@dataclass
class DerivationRule:
    """A rule for computing derived facts."""

    id: UUID
    rule_name: str
    rule_type: DerivationRuleType
    rule_definition: dict[str, Any]
    version: int = 1
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DerivationJob:
    """A scheduled derivation job."""

    id: UUID
    job_type: str
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    entities_processed: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get job duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class DerivationResult:
    """Result of a derivation computation."""

    entity_id: UUID
    entity_type: str
    rule_name: str
    value: Any
    source_fact_ids: list[UUID] = field(default_factory=list)
    computed_at: datetime = field(default_factory=datetime.utcnow)


class DerivationScheduler:
    """
    Orchestrate nightly derivation jobs.

    Target: <4 hours for full graph recomputation.
    """

    def __init__(self):
        self._rules: dict[str, DerivationRule] = {}
        self._jobs: dict[UUID, DerivationJob] = {}
        self._handlers: dict[str, Callable] = {}

    def register_rule(self, rule: DerivationRule) -> None:
        """Register a derivation rule."""
        self._rules[rule.rule_name] = rule
        logger.info(f"Registered derivation rule: {rule.rule_name}")

    def register_handler(self, rule_type: str, handler: Callable) -> None:
        """Register a handler function for a rule type."""
        self._handlers[rule_type] = handler

    async def run_nightly_job(self) -> DerivationJob:
        """
        Run full nightly derivation job.

        Sequence:
        1. Risk scores for persons and companies
        2. Network clusters
        3. Shell indicators
        4. Director velocity
        5. Address statistics
        6. Validation
        """
        job = DerivationJob(
            id=uuid4(),
            job_type="nightly_full",
            status="running",
            started_at=datetime.utcnow(),
        )
        self._jobs[job.id] = job

        logger.info(f"Starting nightly derivation job {job.id}")

        try:
            # 1. Risk scores
            logger.info("Computing person risk scores...")
            person_count = await self._compute_person_risk_scores()
            job.entities_processed += person_count

            logger.info("Computing company risk scores...")
            company_count = await self._compute_company_risk_scores()
            job.entities_processed += company_count

            # 2. Network clusters
            logger.info("Computing network clusters...")
            cluster_count = await self._compute_network_clusters()
            job.metadata["clusters_computed"] = cluster_count

            # 3. Shell indicators
            logger.info("Computing shell indicators...")
            shell_count = await self._compute_shell_indicators()
            job.metadata["shell_companies_identified"] = shell_count

            # 4. Director velocity
            logger.info("Computing director velocity...")
            velocity_count = await self._compute_director_velocity()
            job.metadata["velocities_computed"] = velocity_count

            # 5. Address statistics
            logger.info("Computing address statistics...")
            address_count = await self._compute_address_statistics()
            job.entities_processed += address_count

            # 6. Validation
            logger.info("Validating derivation consistency...")
            await self._validate_derivation_consistency()

            job.status = "completed"
            job.completed_at = datetime.utcnow()

            logger.info(
                f"Nightly job {job.id} completed in {job.duration_seconds:.1f}s, "
                f"processed {job.entities_processed} entities"
            )

        except Exception as e:
            job.status = "failed"
            job.errors.append(str(e))
            job.completed_at = datetime.utcnow()
            logger.error(f"Nightly job {job.id} failed: {e}")
            raise

        return job

    async def run_incremental_job(
        self,
        entity_ids: list[UUID],
    ) -> DerivationJob:
        """
        Run incremental derivation for specific entities.

        Used for real-time updates when entities change.
        """
        job = DerivationJob(
            id=uuid4(),
            job_type="incremental",
            status="running",
            started_at=datetime.utcnow(),
            metadata={"target_entities": len(entity_ids)},
        )
        self._jobs[job.id] = job

        logger.info(f"Starting incremental derivation for {len(entity_ids)} entities")

        try:
            for entity_id in entity_ids:
                await self._recompute_entity_derivations(entity_id)
                job.entities_processed += 1

            job.status = "completed"
            job.completed_at = datetime.utcnow()

        except Exception as e:
            job.status = "failed"
            job.errors.append(str(e))
            job.completed_at = datetime.utcnow()
            raise

        return job

    async def _compute_person_risk_scores(self) -> int:
        """Compute risk scores for all active persons."""
        # In real implementation, this would query the database
        # and use PersonRiskScorer
        handler = self._handlers.get("person_risk_score")
        if handler:
            return await handler()
        return 0

    async def _compute_company_risk_scores(self) -> int:
        """Compute risk scores for all active companies."""
        handler = self._handlers.get("company_risk_score")
        if handler:
            return await handler()
        return 0

    async def _compute_network_clusters(self) -> int:
        """Compute network clusters using graph algorithms."""
        handler = self._handlers.get("network_cluster")
        if handler:
            return await handler()
        return 0

    async def _compute_shell_indicators(self) -> int:
        """Compute shell indicators for all companies."""
        handler = self._handlers.get("shell_indicator")
        if handler:
            return await handler()
        return 0

    async def _compute_director_velocity(self) -> int:
        """Compute director velocity for all companies."""
        handler = self._handlers.get("director_velocity")
        if handler:
            return await handler()
        return 0

    async def _compute_address_statistics(self) -> int:
        """Compute statistics for all addresses."""
        handler = self._handlers.get("address_stats")
        if handler:
            return await handler()
        return 0

    async def _validate_derivation_consistency(self) -> None:
        """Validate that derived facts are consistent with source facts."""
        handler = self._handlers.get("validate")
        if handler:
            await handler()

    async def _recompute_entity_derivations(self, entity_id: UUID) -> None:
        """Recompute all derivations for a single entity."""
        handler = self._handlers.get("recompute_entity")
        if handler:
            await handler(entity_id)

    def get_job(self, job_id: UUID) -> Optional[DerivationJob]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def get_recent_jobs(self, limit: int = 10) -> list[DerivationJob]:
        """Get recent jobs sorted by start time."""
        jobs = list(self._jobs.values())
        jobs.sort(
            key=lambda j: j.started_at or datetime.min,
            reverse=True,
        )
        return jobs[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Get scheduler statistics."""
        jobs = list(self._jobs.values())
        completed = [j for j in jobs if j.status == "completed"]
        failed = [j for j in jobs if j.status == "failed"]

        avg_duration = 0.0
        if completed:
            durations = [j.duration_seconds for j in completed if j.duration_seconds]
            avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_jobs": len(jobs),
            "completed_jobs": len(completed),
            "failed_jobs": len(failed),
            "registered_rules": len(self._rules),
            "registered_handlers": len(self._handlers),
            "average_duration_seconds": round(avg_duration, 1),
        }
