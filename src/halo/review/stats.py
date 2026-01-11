"""
Review statistics for rubber-stamp detection.

Monitors user review patterns to detect potential compliance issues.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class ReviewStats:
    """Statistics for a user's review activity."""

    user_id: str
    period_days: int
    total_reviews: int
    approvals: int
    rejections: int
    escalations: int
    avg_review_seconds: float
    min_review_seconds: float
    max_review_seconds: float
    rubber_stamp_count: int

    @property
    def approval_rate(self) -> float:
        """Calculate approval rate."""
        if self.total_reviews == 0:
            return 0.0
        return self.approvals / self.total_reviews

    @property
    def rejection_rate(self) -> float:
        """Calculate rejection rate."""
        if self.total_reviews == 0:
            return 0.0
        return self.rejections / self.total_reviews

    @property
    def rubber_stamp_rate(self) -> float:
        """Calculate rubber-stamp rate."""
        if self.total_reviews == 0:
            return 0.0
        return self.rubber_stamp_count / self.total_reviews

    @property
    def is_suspicious(self) -> bool:
        """
        Check if review patterns are suspicious.

        Suspicious indicators:
        - Approval rate > 98% (almost never rejects)
        - Average review time < 3 seconds (too fast)
        - Rubber-stamp rate > 10%
        """
        if self.total_reviews < 10:
            # Not enough data to judge
            return False

        if self.approval_rate > 0.98:
            return True

        if self.avg_review_seconds < 3.0:
            return True

        if self.rubber_stamp_rate > 0.10:
            return True

        return False


async def check_rubber_stamping(
    user_id: str,
    reviews: list[dict],
    days: int = 7,
) -> ReviewStats:
    """
    Analyze a user's review history for rubber-stamping.

    This function takes a list of review records and calculates
    statistics to detect potential compliance issues.

    Args:
        user_id: User to analyze
        reviews: List of review records with:
            - decision: 'approved', 'rejected', 'escalated'
            - review_duration_seconds: How long review took
            - is_rubber_stamp: Whether flagged as rubber-stamp
        days: Period to analyze

    Returns:
        ReviewStats with analysis results
    """
    if not reviews:
        return ReviewStats(
            user_id=user_id,
            period_days=days,
            total_reviews=0,
            approvals=0,
            rejections=0,
            escalations=0,
            avg_review_seconds=0.0,
            min_review_seconds=0.0,
            max_review_seconds=0.0,
            rubber_stamp_count=0,
        )

    approvals = sum(1 for r in reviews if r.get("decision") == "approved")
    rejections = sum(1 for r in reviews if r.get("decision") == "rejected")
    escalations = sum(1 for r in reviews if r.get("decision") == "escalated")

    durations = [r.get("review_duration_seconds", 0) for r in reviews if r.get("review_duration_seconds")]
    rubber_stamps = sum(1 for r in reviews if r.get("is_rubber_stamp", False))

    avg_duration = sum(durations) / len(durations) if durations else 0.0
    min_duration = min(durations) if durations else 0.0
    max_duration = max(durations) if durations else 0.0

    return ReviewStats(
        user_id=user_id,
        period_days=days,
        total_reviews=len(reviews),
        approvals=approvals,
        rejections=rejections,
        escalations=escalations,
        avg_review_seconds=avg_duration,
        min_review_seconds=min_duration,
        max_review_seconds=max_duration,
        rubber_stamp_count=rubber_stamps,
    )


def generate_compliance_report(stats: ReviewStats) -> dict:
    """
    Generate a compliance report for IMY audit purposes.

    Returns a structured report that can be presented during
    regulatory audits to demonstrate meaningful human review.

    Args:
        stats: Review statistics for a user

    Returns:
        Compliance report dict
    """
    report = {
        "user_id": stats.user_id,
        "period_days": stats.period_days,
        "summary": {
            "total_reviews": stats.total_reviews,
            "approval_rate": f"{stats.approval_rate:.1%}",
            "rejection_rate": f"{stats.rejection_rate:.1%}",
            "avg_review_time": f"{stats.avg_review_seconds:.1f}s",
        },
        "compliance_status": "PASS" if not stats.is_suspicious else "REVIEW_NEEDED",
        "flags": [],
        "recommendations": [],
    }

    # Add flags for suspicious patterns
    if stats.approval_rate > 0.98 and stats.total_reviews >= 10:
        report["flags"].append({
            "type": "HIGH_APPROVAL_RATE",
            "severity": "WARNING",
            "message": f"Approval rate of {stats.approval_rate:.1%} exceeds 98% threshold",
        })
        report["recommendations"].append(
            "Review training on when to reject alerts"
        )

    if stats.avg_review_seconds < 3.0 and stats.total_reviews >= 10:
        report["flags"].append({
            "type": "FAST_REVIEWS",
            "severity": "WARNING",
            "message": f"Average review time of {stats.avg_review_seconds:.1f}s below 3s minimum",
        })
        report["recommendations"].append(
            "Ensure adequate time is taken to review each alert"
        )

    if stats.rubber_stamp_rate > 0.10:
        report["flags"].append({
            "type": "RUBBER_STAMPING",
            "severity": "CRITICAL",
            "message": f"Rubber-stamp rate of {stats.rubber_stamp_rate:.1%} exceeds 10% threshold",
        })
        report["recommendations"].append(
            "Immediate review of user's review practices required"
        )

    return report
