"""
Human-in-Loop Review module for Brottsdatalagen compliance.

This module implements the tiered review system required by
Brottsdatalagen 2 kap. 19 § which prohibits decisions that
"significantly affect" individuals from being based "solely
on automated processing."
"""

from halo.review.workflow import AlertTier, classify_alert_tier
from halo.review.validation import validate_justification
from halo.review.stats import ReviewStats, check_rubber_stamping

__all__ = [
    "AlertTier",
    "classify_alert_tier",
    "validate_justification",
    "ReviewStats",
    "check_rubber_stamping",
]
