"""
Unit tests for human-in-loop review workflow.
"""

import pytest

from halo.review.workflow import (
    AlertTier,
    can_export,
    classify_alert_tier,
    get_review_status,
    get_tier_requirements,
)
from halo.review.validation import (
    is_rubber_stamp,
    validate_justification,
    validate_review_duration,
)
from halo.review.stats import (
    ReviewStats,
    check_rubber_stamping,
    generate_compliance_report,
)


class TestClassifyAlertTier:
    """Tests for alert tier classification."""

    def test_high_confidence_person_is_tier_3(self):
        """High confidence alerts affecting people are Tier 3."""
        tier = classify_alert_tier(confidence=0.90, affects_person=True)
        assert tier == AlertTier.ACTIONABLE_INTELLIGENCE

    def test_medium_confidence_person_is_tier_2(self):
        """Medium confidence alerts affecting people are Tier 2."""
        tier = classify_alert_tier(confidence=0.70, affects_person=True)
        assert tier == AlertTier.PATTERN_DETECTION

    def test_low_confidence_person_is_tier_1(self):
        """Low confidence alerts are Tier 1 (informational)."""
        tier = classify_alert_tier(confidence=0.30, affects_person=True)
        assert tier == AlertTier.ENRICHMENT

    def test_no_person_affected_max_tier_1(self):
        """Alerts not affecting persons max out at Tier 1."""
        tier = classify_alert_tier(confidence=0.95, affects_person=False)
        assert tier == AlertTier.ENRICHMENT

    def test_threshold_boundary_tier_3(self):
        """Test exact threshold for Tier 3."""
        tier = classify_alert_tier(confidence=0.85, affects_person=True)
        assert tier == AlertTier.ACTIONABLE_INTELLIGENCE

    def test_threshold_boundary_tier_2(self):
        """Test exact threshold for Tier 2."""
        tier = classify_alert_tier(confidence=0.50, affects_person=True)
        assert tier == AlertTier.PATTERN_DETECTION


class TestGetTierRequirements:
    """Tests for tier requirement lookup."""

    def test_tier_0_requirements(self):
        """Tier 0 has no review requirements."""
        req = get_tier_requirements(AlertTier.DATA_RETRIEVAL)
        assert req["review_required"] is False
        assert req["can_export_immediately"] is True

    def test_tier_2_requirements(self):
        """Tier 2 requires acknowledgment."""
        req = get_tier_requirements(AlertTier.PATTERN_DETECTION)
        assert req["review_required"] is True
        assert req["requires_acknowledgment"] is True
        assert req["requires_approval"] is False
        assert req["can_batch_review"] is True

    def test_tier_3_requirements(self):
        """Tier 3 requires approval with justification."""
        req = get_tier_requirements(AlertTier.ACTIONABLE_INTELLIGENCE)
        assert req["review_required"] is True
        assert req["requires_approval"] is True
        assert req["requires_justification"] is True
        assert req["can_batch_review"] is False


class TestCanExport:
    """Tests for export permission checking."""

    def test_tier_1_can_always_export(self):
        """Tier 1 alerts can always be exported."""
        assert can_export(tier=1) is True

    def test_tier_2_needs_acknowledgment(self):
        """Tier 2 alerts need acknowledgment before export."""
        assert can_export(tier=2) is False
        assert can_export(tier=2, acknowledged_by="user123") is True

    def test_tier_3_needs_approval(self):
        """Tier 3 alerts need approval before export."""
        assert can_export(tier=3) is False
        assert can_export(tier=3, acknowledged_by="user123") is False
        assert can_export(tier=3, approval_decision="rejected") is False
        assert can_export(tier=3, approval_decision="approved") is True


class TestGetReviewStatus:
    """Tests for review status calculation."""

    def test_tier_1_status(self):
        """Tier 1 alerts don't need review."""
        assert get_review_status(tier=1) == "no_review_needed"

    def test_tier_2_pending(self):
        """Tier 2 alerts pending acknowledgment."""
        assert get_review_status(tier=2) == "pending_acknowledgment"

    def test_tier_2_acknowledged(self):
        """Tier 2 alerts that are acknowledged."""
        assert get_review_status(tier=2, acknowledged_by="user123") == "acknowledged"

    def test_tier_3_pending(self):
        """Tier 3 alerts pending approval."""
        assert get_review_status(tier=3) == "pending_approval"

    def test_tier_3_approved(self):
        """Tier 3 alerts that are approved."""
        status = get_review_status(tier=3, approval_decision="approved")
        assert status == "decision_approved"


class TestValidateJustification:
    """Tests for justification validation."""

    def test_valid_justification(self):
        """Test valid justification."""
        is_valid, error = validate_justification(
            "This alert shows a clear pattern of structuring transactions."
        )
        assert is_valid is True
        assert error is None

    def test_too_short(self):
        """Test rejection of too short justification."""
        is_valid, error = validate_justification("ok")
        assert is_valid is False
        assert "kort" in error.lower() or "short" in error.lower()

    def test_garbage_input(self):
        """Test rejection of garbage input."""
        garbage_inputs = ["ok", "fine", "approved", "asdf", "123", "test"]
        for garbage in garbage_inputs:
            is_valid, error = validate_justification(garbage)
            assert is_valid is False

    def test_repetitive_text(self):
        """Test rejection of repetitive text."""
        is_valid, error = validate_justification("aaaaaaaaaa")
        assert is_valid is False

    def test_keyboard_pattern(self):
        """Test rejection of keyboard patterns."""
        is_valid, error = validate_justification("asdfasdfasdf")
        assert is_valid is False


class TestValidateReviewDuration:
    """Tests for review duration validation."""

    def test_valid_duration(self):
        """Test valid review duration."""
        is_valid, warning = validate_review_duration(5.0)
        assert is_valid is True
        assert warning is None

    def test_too_fast(self):
        """Test rejection of too fast review."""
        is_valid, warning = validate_review_duration(1.0)
        assert is_valid is False
        assert warning is not None


class TestIsRubberStamp:
    """Tests for rubber-stamp detection."""

    def test_fast_review_is_rubber_stamp(self):
        """Fast review is flagged as rubber-stamp."""
        assert is_rubber_stamp(duration_seconds=1.0) is True

    def test_slow_review_not_rubber_stamp(self):
        """Slow review is not flagged."""
        assert is_rubber_stamp(duration_seconds=10.0) is False

    def test_garbage_justification_is_rubber_stamp(self):
        """Garbage justification is flagged."""
        assert is_rubber_stamp(duration_seconds=5.0, justification="ok") is True


class TestReviewStats:
    """Tests for review statistics."""

    def test_approval_rate_calculation(self):
        """Test approval rate calculation."""
        stats = ReviewStats(
            user_id="user123",
            period_days=7,
            total_reviews=100,
            approvals=80,
            rejections=15,
            escalations=5,
            avg_review_seconds=10.0,
            min_review_seconds=3.0,
            max_review_seconds=60.0,
            rubber_stamp_count=5,
        )
        assert stats.approval_rate == 0.80
        assert stats.rejection_rate == 0.15

    def test_is_suspicious_high_approval(self):
        """Test suspicious flag for high approval rate."""
        stats = ReviewStats(
            user_id="user123",
            period_days=7,
            total_reviews=100,
            approvals=99,
            rejections=1,
            escalations=0,
            avg_review_seconds=10.0,
            min_review_seconds=3.0,
            max_review_seconds=60.0,
            rubber_stamp_count=0,
        )
        assert stats.is_suspicious is True

    def test_is_suspicious_fast_reviews(self):
        """Test suspicious flag for fast reviews."""
        stats = ReviewStats(
            user_id="user123",
            period_days=7,
            total_reviews=100,
            approvals=70,
            rejections=30,
            escalations=0,
            avg_review_seconds=2.0,  # Too fast
            min_review_seconds=1.0,
            max_review_seconds=5.0,
            rubber_stamp_count=0,
        )
        assert stats.is_suspicious is True

    def test_not_suspicious_with_few_reviews(self):
        """Test that few reviews don't trigger suspicious flag."""
        stats = ReviewStats(
            user_id="user123",
            period_days=7,
            total_reviews=5,  # Not enough data
            approvals=5,
            rejections=0,
            escalations=0,
            avg_review_seconds=2.0,
            min_review_seconds=1.0,
            max_review_seconds=5.0,
            rubber_stamp_count=0,
        )
        assert stats.is_suspicious is False


class TestGenerateComplianceReport:
    """Tests for compliance report generation."""

    def test_passing_report(self):
        """Test compliance report for good reviewer."""
        stats = ReviewStats(
            user_id="user123",
            period_days=7,
            total_reviews=50,
            approvals=35,
            rejections=10,
            escalations=5,
            avg_review_seconds=15.0,
            min_review_seconds=5.0,
            max_review_seconds=120.0,
            rubber_stamp_count=1,
        )
        report = generate_compliance_report(stats)
        assert report["compliance_status"] == "PASS"
        assert len(report["flags"]) == 0

    def test_failing_report(self):
        """Test compliance report for problematic reviewer."""
        stats = ReviewStats(
            user_id="user123",
            period_days=7,
            total_reviews=100,
            approvals=99,
            rejections=1,
            escalations=0,
            avg_review_seconds=2.0,
            min_review_seconds=0.5,
            max_review_seconds=5.0,
            rubber_stamp_count=50,
        )
        report = generate_compliance_report(stats)
        assert report["compliance_status"] == "REVIEW_NEEDED"
        assert len(report["flags"]) > 0
