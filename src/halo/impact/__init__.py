"""
Impact tracking module for measuring system effectiveness.

Tracks outcomes of referrals and intelligence to measure:
- Investigation opens
- Charges filed
- Convictions
- Assets seized
- Referral success rates
"""

from halo.impact.tracker import (
    ImpactTracker,
    ImpactRecord,
    ImpactType,
    record_impact,
)
from halo.impact.metrics import (
    ImpactMetrics,
    AuthorityMetrics,
    MetricsCalculator,
)

__all__ = [
    "ImpactTracker",
    "ImpactRecord",
    "ImpactType",
    "record_impact",
    "ImpactMetrics",
    "AuthorityMetrics",
    "MetricsCalculator",
]
