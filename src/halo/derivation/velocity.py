"""
Director velocity calculation.

Tracks the rate of director changes for companies,
which is an indicator of potential fraud.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class DirectorChange:
    """A single director change event."""

    company_id: UUID
    person_id: UUID
    person_name: str
    change_type: str  # "added", "removed"
    change_date: date
    role: str = "director"


@dataclass
class VelocityResult:
    """Result of velocity calculation."""

    entity_id: UUID
    entity_type: str  # "COMPANY" or "PERSON"
    velocity: float  # Changes per year
    total_changes: int
    period_days: int
    changes: list[DirectorChange] = field(default_factory=list)
    computed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_high_velocity(self) -> bool:
        """Check if velocity is considered high (>2 per year)."""
        return self.velocity > 2.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "entity_id": str(self.entity_id),
            "entity_type": self.entity_type,
            "velocity": round(self.velocity, 2),
            "total_changes": self.total_changes,
            "period_days": self.period_days,
            "is_high_velocity": self.is_high_velocity,
            "computed_at": self.computed_at.isoformat(),
        }


class DirectorVelocityCalculator:
    """
    Calculate director change velocity for companies and persons.

    High velocity (frequent director changes) is associated with:
    - Shell companies (directors move frequently)
    - Phoenix fraud (directors abandon failing companies)
    - Nominee director arrangements
    """

    DEFAULT_PERIOD_DAYS = 365 * 2  # 2 years of history

    def __init__(self, period_days: int = DEFAULT_PERIOD_DAYS):
        self.period_days = period_days
        self._changes: list[DirectorChange] = []

    def add_change(self, change: DirectorChange) -> None:
        """Add a director change event."""
        self._changes.append(change)

    def add_changes(self, changes: list[DirectorChange]) -> None:
        """Add multiple director change events."""
        self._changes.extend(changes)

    def calculate_company_velocity(
        self,
        company_id: UUID,
        as_of_date: Optional[date] = None,
    ) -> VelocityResult:
        """
        Calculate director velocity for a company.

        Args:
            company_id: The company to calculate for
            as_of_date: Calculate as of this date (default: today)

        Returns:
            Velocity result with changes per year
        """
        as_of_date = as_of_date or date.today()
        cutoff_date = as_of_date - timedelta(days=self.period_days)

        # Filter changes for this company within period
        company_changes = [
            c for c in self._changes
            if c.company_id == company_id
            and cutoff_date <= c.change_date <= as_of_date
        ]

        # Calculate velocity (changes per year)
        total_changes = len(company_changes)
        years = self.period_days / 365
        velocity = total_changes / years if years > 0 else 0.0

        return VelocityResult(
            entity_id=company_id,
            entity_type="COMPANY",
            velocity=velocity,
            total_changes=total_changes,
            period_days=self.period_days,
            changes=company_changes,
        )

    def calculate_person_velocity(
        self,
        person_id: UUID,
        as_of_date: Optional[date] = None,
    ) -> VelocityResult:
        """
        Calculate directorship change velocity for a person.

        Measures how frequently a person gains/loses directorships.

        Args:
            person_id: The person to calculate for
            as_of_date: Calculate as of this date (default: today)

        Returns:
            Velocity result with changes per year
        """
        as_of_date = as_of_date or date.today()
        cutoff_date = as_of_date - timedelta(days=self.period_days)

        # Filter changes involving this person within period
        person_changes = [
            c for c in self._changes
            if c.person_id == person_id
            and cutoff_date <= c.change_date <= as_of_date
        ]

        # Calculate velocity
        total_changes = len(person_changes)
        years = self.period_days / 365
        velocity = total_changes / years if years > 0 else 0.0

        return VelocityResult(
            entity_id=person_id,
            entity_type="PERSON",
            velocity=velocity,
            total_changes=total_changes,
            period_days=self.period_days,
            changes=person_changes,
        )

    def calculate_average_velocity_for_person_companies(
        self,
        person_id: UUID,
        company_ids: list[UUID],
        as_of_date: Optional[date] = None,
    ) -> float:
        """
        Calculate average director velocity across companies a person directs.

        High average velocity suggests the person is involved with
        unstable or shell-like companies.
        """
        if not company_ids:
            return 0.0

        total_velocity = 0.0
        for company_id in company_ids:
            result = self.calculate_company_velocity(company_id, as_of_date)
            total_velocity += result.velocity

        return total_velocity / len(company_ids)

    def find_high_velocity_companies(
        self,
        threshold: float = 2.0,
        as_of_date: Optional[date] = None,
    ) -> list[VelocityResult]:
        """
        Find all companies with high director velocity.

        Args:
            threshold: Minimum velocity (changes/year) to include
            as_of_date: Calculate as of this date

        Returns:
            List of velocity results for high-velocity companies
        """
        as_of_date = as_of_date or date.today()

        # Get unique company IDs
        company_ids = set(c.company_id for c in self._changes)

        results = []
        for company_id in company_ids:
            result = self.calculate_company_velocity(company_id, as_of_date)
            if result.velocity >= threshold:
                results.append(result)

        # Sort by velocity descending
        results.sort(key=lambda r: r.velocity, reverse=True)

        return results

    def find_high_velocity_persons(
        self,
        threshold: float = 3.0,
        as_of_date: Optional[date] = None,
    ) -> list[VelocityResult]:
        """
        Find all persons with high directorship change velocity.

        Args:
            threshold: Minimum velocity (changes/year) to include
            as_of_date: Calculate as of this date

        Returns:
            List of velocity results for high-velocity persons
        """
        as_of_date = as_of_date or date.today()

        # Get unique person IDs
        person_ids = set(c.person_id for c in self._changes)

        results = []
        for person_id in person_ids:
            result = self.calculate_person_velocity(person_id, as_of_date)
            if result.velocity >= threshold:
                results.append(result)

        results.sort(key=lambda r: r.velocity, reverse=True)

        return results

    def clear(self) -> None:
        """Clear all stored changes."""
        self._changes.clear()

    def stats(self) -> dict:
        """Get statistics about stored changes."""
        if not self._changes:
            return {"total_changes": 0}

        company_ids = set(c.company_id for c in self._changes)
        person_ids = set(c.person_id for c in self._changes)

        dates = [c.change_date for c in self._changes]

        return {
            "total_changes": len(self._changes),
            "unique_companies": len(company_ids),
            "unique_persons": len(person_ids),
            "earliest_date": min(dates).isoformat() if dates else None,
            "latest_date": max(dates).isoformat() if dates else None,
            "additions": sum(1 for c in self._changes if c.change_type == "added"),
            "removals": sum(1 for c in self._changes if c.change_type == "removed"),
        }
