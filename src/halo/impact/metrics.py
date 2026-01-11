"""
Impact metrics and KPI calculations.

Provides aggregated metrics and statistics from impact tracking
for reporting and effectiveness measurement.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from halo.impact.tracker import ImpactTracker, ImpactType

logger = logging.getLogger(__name__)


@dataclass
class ImpactMetrics:
    """Aggregated impact metrics for a time period."""

    period_start: datetime
    period_end: datetime

    # Counts by type
    investigations_opened: int = 0
    investigations_closed: int = 0
    charges_filed: int = 0
    convictions: int = 0
    acquittals: int = 0
    settlements: int = 0

    # Financial metrics (SEK)
    assets_seized_sek: float = 0.0
    tax_recovered_sek: float = 0.0
    fines_imposed_sek: float = 0.0
    fraud_prevented_sek: float = 0.0

    # Prevention metrics
    activities_disrupted: int = 0
    licenses_revoked: int = 0
    sanctions_applied: int = 0

    # Derived metrics
    conviction_rate: float = 0.0
    total_financial_impact_sek: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
            "investigations": {
                "opened": self.investigations_opened,
                "closed": self.investigations_closed,
            },
            "legal_outcomes": {
                "charges_filed": self.charges_filed,
                "convictions": self.convictions,
                "acquittals": self.acquittals,
                "settlements": self.settlements,
                "conviction_rate": round(self.conviction_rate, 3),
            },
            "financial_impact": {
                "assets_seized_sek": self.assets_seized_sek,
                "tax_recovered_sek": self.tax_recovered_sek,
                "fines_imposed_sek": self.fines_imposed_sek,
                "fraud_prevented_sek": self.fraud_prevented_sek,
                "total_sek": self.total_financial_impact_sek,
            },
            "prevention": {
                "activities_disrupted": self.activities_disrupted,
                "licenses_revoked": self.licenses_revoked,
                "sanctions_applied": self.sanctions_applied,
            },
        }


@dataclass
class AuthorityMetrics:
    """Metrics broken down by authority."""

    authority: str
    total_referrals: int = 0
    outcomes_recorded: int = 0
    convictions: int = 0
    total_value_sek: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "authority": self.authority,
            "total_referrals": self.total_referrals,
            "outcomes_recorded": self.outcomes_recorded,
            "convictions": self.convictions,
            "total_value_sek": self.total_value_sek,
        }


class MetricsCalculator:
    """
    Calculates impact metrics from tracker data.

    Provides various aggregations and statistics for reporting.
    """

    def __init__(self, tracker: ImpactTracker):
        self.tracker = tracker

    def calculate_period_metrics(
        self,
        start: datetime,
        end: Optional[datetime] = None,
    ) -> ImpactMetrics:
        """
        Calculate metrics for a time period.

        Args:
            start: Start of period
            end: End of period (defaults to now)

        Returns:
            Aggregated metrics for the period
        """
        end = end or datetime.utcnow()

        metrics = ImpactMetrics(period_start=start, period_end=end)

        # Filter records by period
        period_records = [
            r for r in self.tracker.records.values()
            if start <= r.occurred_at <= end
        ]

        # Count by type
        for record in period_records:
            match record.impact_type:
                case ImpactType.INVESTIGATION_OPENED:
                    metrics.investigations_opened += 1
                case ImpactType.INVESTIGATION_CLOSED:
                    metrics.investigations_closed += 1
                case ImpactType.CHARGES_FILED:
                    metrics.charges_filed += 1
                case ImpactType.CONVICTION:
                    metrics.convictions += 1
                case ImpactType.ACQUITTAL:
                    metrics.acquittals += 1
                case ImpactType.SETTLEMENT:
                    metrics.settlements += 1
                case ImpactType.ASSETS_SEIZED:
                    metrics.assets_seized_sek += record.value_sek
                case ImpactType.TAX_RECOVERED:
                    metrics.tax_recovered_sek += record.value_sek
                case ImpactType.FINES_IMPOSED:
                    metrics.fines_imposed_sek += record.value_sek
                case ImpactType.FRAUD_PREVENTED:
                    metrics.fraud_prevented_sek += record.value_sek
                case ImpactType.ACTIVITY_DISRUPTED:
                    metrics.activities_disrupted += 1
                case ImpactType.LICENSE_REVOKED:
                    metrics.licenses_revoked += 1
                case ImpactType.SANCTIONS_APPLIED:
                    metrics.sanctions_applied += 1

        # Calculate derived metrics
        total_cases = metrics.convictions + metrics.acquittals
        if total_cases > 0:
            metrics.conviction_rate = metrics.convictions / total_cases

        metrics.total_financial_impact_sek = (
            metrics.assets_seized_sek +
            metrics.tax_recovered_sek +
            metrics.fines_imposed_sek +
            metrics.fraud_prevented_sek
        )

        return metrics

    def calculate_authority_metrics(
        self,
        since: Optional[datetime] = None,
    ) -> list[AuthorityMetrics]:
        """
        Calculate metrics broken down by authority.

        Args:
            since: Only include records after this date

        Returns:
            List of metrics per authority
        """
        authority_data: dict[str, AuthorityMetrics] = {}

        for record in self.tracker.records.values():
            if since and record.occurred_at < since:
                continue

            authority = record.authority
            if authority not in authority_data:
                authority_data[authority] = AuthorityMetrics(authority=authority)

            am = authority_data[authority]
            am.outcomes_recorded += 1
            am.total_value_sek += record.value_sek

            if record.impact_type == ImpactType.CONVICTION:
                am.convictions += 1

        return list(authority_data.values())

    def get_monthly_summary(
        self,
        months: int = 12,
    ) -> list[ImpactMetrics]:
        """
        Get monthly metrics for the past N months.

        Args:
            months: Number of months to include

        Returns:
            List of monthly metrics
        """
        summaries = []
        now = datetime.utcnow()

        for i in range(months):
            # Calculate month boundaries
            month_end = now.replace(day=1) - timedelta(days=i * 30)
            month_start = month_end - timedelta(days=30)

            metrics = self.calculate_period_metrics(month_start, month_end)
            summaries.append(metrics)

        return list(reversed(summaries))

    def get_referral_effectiveness(
        self,
        since: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """
        Calculate referral effectiveness metrics.

        Args:
            since: Only include records after this date

        Returns:
            Effectiveness statistics
        """
        total_referrals = 0
        referrals_with_outcome = 0
        positive_outcomes = 0

        # Get unique referral IDs
        referral_ids = set()
        for record in self.tracker.records.values():
            if since and record.occurred_at < since:
                continue
            if record.referral_id:
                referral_ids.add(record.referral_id)

        total_referrals = len(referral_ids)

        for referral_id in referral_ids:
            records = self.tracker.get_by_referral(referral_id)
            if records:
                referrals_with_outcome += 1
                # Check for positive outcomes
                for r in records:
                    if r.impact_type in [
                        ImpactType.CONVICTION,
                        ImpactType.SETTLEMENT,
                        ImpactType.ASSETS_SEIZED,
                        ImpactType.TAX_RECOVERED,
                        ImpactType.FRAUD_PREVENTED,
                    ]:
                        positive_outcomes += 1
                        break

        outcome_rate = (
            referrals_with_outcome / total_referrals
            if total_referrals > 0
            else 0.0
        )

        success_rate = (
            positive_outcomes / total_referrals
            if total_referrals > 0
            else 0.0
        )

        return {
            "total_referrals": total_referrals,
            "referrals_with_outcome": referrals_with_outcome,
            "positive_outcomes": positive_outcomes,
            "outcome_rate": round(outcome_rate, 3),
            "success_rate": round(success_rate, 3),
        }
