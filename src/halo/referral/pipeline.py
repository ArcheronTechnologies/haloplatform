"""
Referral pipeline for generating and tracking prosecution referrals.

Converts detected patterns and intelligence into actionable referrals
for Swedish authorities.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class ReferralStatus(str, Enum):
    """Status of a referral in the pipeline."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    CLOSED_ACTION_TAKEN = "closed_action_taken"
    CLOSED_NO_ACTION = "closed_no_action"
    REJECTED = "rejected"


@dataclass
class ReferralRequest:
    """Request to create a referral from detection results."""

    case_id: UUID
    detection_ids: list[UUID]
    target_authority: str  # Authority code (EBM, SKV, FK, etc.)
    priority: str = "normal"  # low, normal, high, urgent
    summary: str = ""
    evidence_ids: list[UUID] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReferralResult:
    """Result of referral generation."""

    referral_id: UUID
    status: ReferralStatus
    authority: str
    confidence: float
    evidence_package_id: Optional[UUID] = None
    submitted_at: Optional[datetime] = None
    tracking_reference: Optional[str] = None
    errors: list[str] = field(default_factory=list)


class ReferralPipeline:
    """
    Pipeline for generating and submitting referrals to authorities.

    Workflow:
    1. Receive detection results and evidence
    2. Route to appropriate authority based on thresholds
    3. Format referral in authority-specific format
    4. Generate evidence package
    5. Submit or queue for review
    6. Track outcome
    """

    def __init__(self):
        self.pending_referrals: dict[UUID, ReferralRequest] = {}

    async def create_referral(
        self,
        request: ReferralRequest,
        auto_submit: bool = False,
    ) -> ReferralResult:
        """
        Create a new referral from detection results.

        Args:
            request: The referral request with case and detection info
            auto_submit: If True, automatically submit high-confidence referrals

        Returns:
            ReferralResult with status and tracking info
        """
        referral_id = uuid4()

        logger.info(
            f"Creating referral {referral_id} for case {request.case_id} "
            f"to authority {request.target_authority}"
        )

        # Store pending referral
        self.pending_referrals[referral_id] = request

        # Calculate confidence based on evidence quality
        confidence = self._calculate_confidence(request)

        # Determine initial status
        if auto_submit and confidence >= 0.90:
            status = ReferralStatus.SUBMITTED
        elif confidence >= 0.75:
            status = ReferralStatus.PENDING_REVIEW
        else:
            status = ReferralStatus.DRAFT

        return ReferralResult(
            referral_id=referral_id,
            status=status,
            authority=request.target_authority,
            confidence=confidence,
        )

    async def submit_referral(
        self,
        referral_id: UUID,
    ) -> ReferralResult:
        """
        Submit a referral to the target authority.

        Args:
            referral_id: ID of the referral to submit

        Returns:
            Updated ReferralResult with submission status
        """
        if referral_id not in self.pending_referrals:
            raise ValueError(f"Referral {referral_id} not found")

        request = self.pending_referrals[referral_id]

        # Generate tracking reference
        tracking_ref = self._generate_tracking_reference(request.target_authority)

        logger.info(
            f"Submitting referral {referral_id} to {request.target_authority} "
            f"with tracking reference {tracking_ref}"
        )

        return ReferralResult(
            referral_id=referral_id,
            status=ReferralStatus.SUBMITTED,
            authority=request.target_authority,
            confidence=self._calculate_confidence(request),
            submitted_at=datetime.utcnow(),
            tracking_reference=tracking_ref,
        )

    async def get_referral_status(
        self,
        referral_id: UUID,
    ) -> Optional[ReferralResult]:
        """Get the current status of a referral."""
        if referral_id not in self.pending_referrals:
            return None

        request = self.pending_referrals[referral_id]

        return ReferralResult(
            referral_id=referral_id,
            status=ReferralStatus.PENDING_REVIEW,  # TODO: Track actual status
            authority=request.target_authority,
            confidence=self._calculate_confidence(request),
        )

    def _calculate_confidence(self, request: ReferralRequest) -> float:
        """Calculate confidence score based on evidence quality."""
        # Base confidence from number of detections
        base_confidence = min(0.5 + len(request.detection_ids) * 0.1, 0.8)

        # Boost for evidence
        evidence_boost = min(len(request.evidence_ids) * 0.05, 0.15)

        return min(base_confidence + evidence_boost, 1.0)

    def _generate_tracking_reference(self, authority: str) -> str:
        """Generate a tracking reference for authority submissions."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"HALO-{authority}-{timestamp}"
