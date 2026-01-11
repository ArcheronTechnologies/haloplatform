"""
Alert review workflow for human-in-loop compliance.

Implements the tiered output system based on Brottsdatalagen requirements.
"""

from enum import IntEnum
from typing import Optional

from halo.config import settings


class AlertTier(IntEnum):
    """
    Alert tiers for human-in-loop review.

    Tier 0: Data retrieval - No review needed
    Tier 1: Enrichment - No review needed (human asked the question)
    Tier 2: Pattern detection - Acknowledgment required before export
    Tier 3: Actionable intelligence - Approval with justification required
    """

    DATA_RETRIEVAL = 0
    ENRICHMENT = 1
    PATTERN_DETECTION = 2
    ACTIONABLE_INTELLIGENCE = 3


def classify_alert_tier(
    confidence: float,
    affects_person: bool,
    alert_type: Optional[str] = None,
) -> int:
    """
    Classify alert tier based on confidence score and impact.

    Higher confidence = more certain = higher tier = more review needed.

    This seems counterintuitive but makes sense:
    - Low confidence alerts are informational (might be noise)
    - High confidence alerts are actionable (might affect people)
    - Actionable outputs affecting people need human approval

    Args:
        confidence: Confidence score from 0.0 to 1.0
        affects_person: Whether alert affects an identifiable person
        alert_type: Optional alert type for special handling

    Returns:
        Tier level (1, 2, or 3)
    """
    # Entity-only alerts (no person affected) max out at Tier 1
    if not affects_person:
        return AlertTier.ENRICHMENT

    # High confidence = actionable = needs explicit approval
    if confidence >= settings.tier_3_threshold:
        return AlertTier.ACTIONABLE_INTELLIGENCE

    # Medium confidence = pattern = needs acknowledgment
    if confidence >= settings.tier_2_threshold:
        return AlertTier.PATTERN_DETECTION

    # Low confidence = informational only
    return AlertTier.ENRICHMENT


def get_tier_requirements(tier: int) -> dict:
    """
    Get the review requirements for a given tier.

    Returns:
        Dict with review requirements
    """
    requirements = {
        AlertTier.DATA_RETRIEVAL: {
            "name": "Data Retrieval",
            "review_required": False,
            "can_export_immediately": True,
            "description": "Basic data lookup, no review needed",
        },
        AlertTier.ENRICHMENT: {
            "name": "Enrichment",
            "review_required": False,
            "can_export_immediately": True,
            "description": "Enriched data, human is already in loop by asking",
        },
        AlertTier.PATTERN_DETECTION: {
            "name": "Pattern Detection",
            "review_required": True,
            "requires_acknowledgment": True,
            "requires_approval": False,
            "can_batch_review": True,
            "can_export_immediately": False,
            "description": "Pattern detected, human must acknowledge before export",
        },
        AlertTier.ACTIONABLE_INTELLIGENCE: {
            "name": "Actionable Intelligence",
            "review_required": True,
            "requires_acknowledgment": True,
            "requires_approval": True,
            "requires_justification": True,
            "can_batch_review": False,
            "can_export_immediately": False,
            "description": "High confidence finding, requires explicit approval with justification",
        },
    }

    return requirements.get(tier, requirements[AlertTier.ENRICHMENT])


def can_export(
    tier: int,
    acknowledged_by: Optional[str] = None,
    approval_decision: Optional[str] = None,
) -> bool:
    """
    Check if an alert can be exported/actioned based on review status.

    Args:
        tier: Alert tier level
        acknowledged_by: User who acknowledged (Tier 2)
        approval_decision: Approval decision (Tier 3)

    Returns:
        True if alert can be exported
    """
    if tier <= AlertTier.ENRICHMENT:
        return True

    if tier == AlertTier.PATTERN_DETECTION:
        return acknowledged_by is not None

    if tier == AlertTier.ACTIONABLE_INTELLIGENCE:
        return approval_decision == "approved"

    return False


def get_review_status(
    tier: int,
    acknowledged_by: Optional[str] = None,
    approval_decision: Optional[str] = None,
) -> str:
    """
    Get human-readable review status for an alert.

    Args:
        tier: Alert tier level
        acknowledged_by: User who acknowledged
        approval_decision: Approval decision

    Returns:
        Status string
    """
    if tier <= AlertTier.ENRICHMENT:
        return "no_review_needed"

    if tier == AlertTier.PATTERN_DETECTION:
        if acknowledged_by:
            return "acknowledged"
        return "pending_acknowledgment"

    if tier == AlertTier.ACTIONABLE_INTELLIGENCE:
        if approval_decision:
            return f"decision_{approval_decision}"
        return "pending_approval"

    return "unknown"
