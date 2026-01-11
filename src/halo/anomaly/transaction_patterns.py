"""
Transaction pattern detection for AML compliance.

Detects common money laundering patterns:
- Structuring (smurfing): Breaking large amounts into smaller ones
- Velocity spikes: Unusual increase in transaction frequency
- Round amounts: Transactions in suspiciously round numbers
- Rapid in-out: Money moving through accounts quickly
- Geographic anomalies: Unusual cross-border patterns
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Types of suspicious patterns."""

    STRUCTURING = "structuring"
    VELOCITY_SPIKE = "velocity_spike"
    ROUND_AMOUNTS = "round_amounts"
    RAPID_IN_OUT = "rapid_in_out"
    UNUSUAL_TIME = "unusual_time"
    NEW_COUNTERPARTY = "new_counterparty"
    DORMANT_REACTIVATION = "dormant_reactivation"


@dataclass
class PatternMatch:
    """A detected suspicious pattern."""

    pattern_type: PatternType
    confidence: float  # 0.0 to 1.0
    description: str
    transaction_ids: list[UUID] = field(default_factory=list)
    entity_ids: list[UUID] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def severity(self) -> str:
        """Calculate severity based on confidence."""
        if self.confidence >= 0.85:
            return "high"
        elif self.confidence >= 0.50:
            return "medium"
        else:
            return "low"


@dataclass
class Transaction:
    """Transaction for analysis."""

    id: UUID
    timestamp: datetime
    amount: float
    currency: str = "SEK"
    from_entity_id: Optional[UUID] = None
    to_entity_id: Optional[UUID] = None
    from_account: str = ""
    to_account: str = ""
    transaction_type: str = ""
    description: str = ""


class TransactionPatternDetector:
    """
    Detects suspicious transaction patterns.

    Implements common AML detection rules for Swedish financial institutions.
    """

    # Swedish reporting threshold (transactions over this must be reported)
    REPORTING_THRESHOLD_SEK = 150_000

    # Structuring threshold (just under reporting limit is suspicious)
    STRUCTURING_THRESHOLD_SEK = 140_000

    def __init__(
        self,
        structuring_threshold: float = None,
        velocity_window_hours: int = 24,
        velocity_multiplier: float = 3.0,
        round_amount_threshold: int = 10_000,
    ):
        """
        Initialize the pattern detector.

        Args:
            structuring_threshold: Threshold for structuring detection
            velocity_window_hours: Window for velocity calculations
            velocity_multiplier: Multiplier for velocity spike detection
            round_amount_threshold: Minimum round amount to flag
        """
        self.structuring_threshold = (
            structuring_threshold or self.STRUCTURING_THRESHOLD_SEK
        )
        self.velocity_window = timedelta(hours=velocity_window_hours)
        self.velocity_multiplier = velocity_multiplier
        self.round_amount_threshold = round_amount_threshold

    def detect_patterns(
        self,
        transactions: list[Transaction],
        historical_transactions: Optional[list[Transaction]] = None,
    ) -> list[PatternMatch]:
        """
        Detect all suspicious patterns in transactions.

        Args:
            transactions: Current transactions to analyze
            historical_transactions: Historical context (optional)

        Returns:
            List of detected patterns
        """
        patterns = []

        # Structuring detection
        patterns.extend(self.detect_structuring(transactions))

        # Velocity spike detection
        if historical_transactions:
            patterns.extend(
                self.detect_velocity_spikes(transactions, historical_transactions)
            )

        # Round amount detection
        patterns.extend(self.detect_round_amounts(transactions))

        # Rapid in-out detection
        patterns.extend(self.detect_rapid_in_out(transactions))

        # Unusual time detection
        patterns.extend(self.detect_unusual_times(transactions))

        return patterns

    def detect_structuring(
        self,
        transactions: list[Transaction],
        window_days: int = 3,
    ) -> list[PatternMatch]:
        """
        Detect structuring (smurfing) patterns.

        Structuring is breaking large amounts into smaller transactions
        to avoid reporting thresholds.

        Args:
            transactions: Transactions to analyze
            window_days: Window to group transactions

        Returns:
            Detected structuring patterns
        """
        patterns = []

        # Group transactions by entity
        by_entity: dict[UUID, list[Transaction]] = {}
        for txn in transactions:
            entity_id = txn.from_entity_id or txn.to_entity_id
            if entity_id:
                by_entity.setdefault(entity_id, []).append(txn)

        for entity_id, entity_txns in by_entity.items():
            # Sort by timestamp
            entity_txns.sort(key=lambda t: t.timestamp)

            # Sliding window analysis
            for i, txn in enumerate(entity_txns):
                window_txns = [
                    t
                    for t in entity_txns[i:]
                    if t.timestamp <= txn.timestamp + timedelta(days=window_days)
                ]

                if len(window_txns) < 3:
                    continue

                # Check for structuring indicators
                amounts = [t.amount for t in window_txns]
                total = sum(amounts)

                # Pattern 1: Multiple transactions just under threshold
                under_threshold = [
                    a
                    for a in amounts
                    if self.structuring_threshold <= a < self.REPORTING_THRESHOLD_SEK
                ]

                if len(under_threshold) >= 3:
                    confidence = min(1.0, len(under_threshold) / 5 * 0.9)
                    patterns.append(
                        PatternMatch(
                            pattern_type=PatternType.STRUCTURING,
                            confidence=confidence,
                            description=f"{len(under_threshold)} transactions between {self.structuring_threshold:,.0f} and {self.REPORTING_THRESHOLD_SEK:,.0f} SEK within {window_days} days",
                            transaction_ids=[t.id for t in window_txns],
                            entity_ids=[entity_id],
                            metadata={
                                "total_amount": total,
                                "transaction_count": len(window_txns),
                                "under_threshold_count": len(under_threshold),
                            },
                        )
                    )

                # Pattern 2: Total exceeds threshold via small transactions
                if total >= self.REPORTING_THRESHOLD_SEK and all(
                    a < self.REPORTING_THRESHOLD_SEK for a in amounts
                ):
                    avg_amount = total / len(amounts)
                    if avg_amount > self.round_amount_threshold:
                        confidence = min(1.0, (total / self.REPORTING_THRESHOLD_SEK - 1) * 0.5 + 0.5)
                        patterns.append(
                            PatternMatch(
                                pattern_type=PatternType.STRUCTURING,
                                confidence=confidence,
                                description=f"Total of {total:,.0f} SEK across {len(amounts)} transactions (avg {avg_amount:,.0f} SEK)",
                                transaction_ids=[t.id for t in window_txns],
                                entity_ids=[entity_id],
                                metadata={
                                    "total_amount": total,
                                    "average_amount": avg_amount,
                                    "transaction_count": len(amounts),
                                },
                            )
                        )

        return patterns

    def detect_velocity_spikes(
        self,
        current: list[Transaction],
        historical: list[Transaction],
    ) -> list[PatternMatch]:
        """
        Detect unusual spikes in transaction velocity.

        Args:
            current: Current period transactions
            historical: Historical transactions for baseline

        Returns:
            Detected velocity spikes
        """
        patterns = []

        # Calculate historical baseline per entity
        baseline: dict[UUID, float] = {}
        for txn in historical:
            entity_id = txn.from_entity_id or txn.to_entity_id
            if entity_id:
                baseline[entity_id] = baseline.get(entity_id, 0) + 1

        # Normalize to daily rate
        if historical:
            days = max(
                1,
                (historical[-1].timestamp - historical[0].timestamp).days,
            )
            baseline = {k: v / days for k, v in baseline.items()}

        # Count current transactions per entity
        current_counts: dict[UUID, int] = {}
        for txn in current:
            entity_id = txn.from_entity_id or txn.to_entity_id
            if entity_id:
                current_counts[entity_id] = current_counts.get(entity_id, 0) + 1

        # Compare to baseline
        for entity_id, count in current_counts.items():
            base_rate = baseline.get(entity_id, 1)

            if count > base_rate * self.velocity_multiplier:
                ratio = count / max(1, base_rate)
                confidence = min(1.0, (ratio - self.velocity_multiplier) / 5 + 0.6)

                entity_txns = [
                    t
                    for t in current
                    if t.from_entity_id == entity_id or t.to_entity_id == entity_id
                ]

                patterns.append(
                    PatternMatch(
                        pattern_type=PatternType.VELOCITY_SPIKE,
                        confidence=confidence,
                        description=f"Transaction velocity {ratio:.1f}x higher than baseline ({count} vs {base_rate:.1f} per day)",
                        transaction_ids=[t.id for t in entity_txns],
                        entity_ids=[entity_id],
                        metadata={
                            "current_count": count,
                            "baseline_rate": base_rate,
                            "multiplier": ratio,
                        },
                    )
                )

        return patterns

    def detect_round_amounts(
        self,
        transactions: list[Transaction],
    ) -> list[PatternMatch]:
        """
        Detect suspiciously round transaction amounts.

        Round amounts (especially large ones) can indicate
        informal value transfer or structuring.
        """
        patterns = []

        for txn in transactions:
            if txn.amount < self.round_amount_threshold:
                continue

            # Check if amount is suspiciously round
            is_round = False
            roundness_level = ""

            if txn.amount % 100_000 == 0 and txn.amount >= 100_000:
                is_round = True
                roundness_level = "100,000"
            elif txn.amount % 50_000 == 0 and txn.amount >= 50_000:
                is_round = True
                roundness_level = "50,000"
            elif txn.amount % 10_000 == 0 and txn.amount >= 10_000:
                is_round = True
                roundness_level = "10,000"

            if is_round:
                confidence = 0.4 + min(0.4, txn.amount / 1_000_000)
                patterns.append(
                    PatternMatch(
                        pattern_type=PatternType.ROUND_AMOUNTS,
                        confidence=confidence,
                        description=f"Round amount of {txn.amount:,.0f} SEK (multiple of {roundness_level})",
                        transaction_ids=[txn.id],
                        entity_ids=[
                            e
                            for e in [txn.from_entity_id, txn.to_entity_id]
                            if e is not None
                        ],
                        metadata={
                            "amount": txn.amount,
                            "roundness": roundness_level,
                        },
                    )
                )

        return patterns

    def detect_rapid_in_out(
        self,
        transactions: list[Transaction],
        window_hours: int = 48,
    ) -> list[PatternMatch]:
        """
        Detect rapid movement of funds through accounts.

        Money that comes in and goes out quickly (pass-through)
        is a common money laundering indicator.
        """
        patterns = []

        # Group by account
        by_account: dict[str, list[Transaction]] = {}
        for txn in transactions:
            for account in [txn.from_account, txn.to_account]:
                if account:
                    by_account.setdefault(account, []).append(txn)

        window = timedelta(hours=window_hours)

        for account, account_txns in by_account.items():
            if len(account_txns) < 2:
                continue

            account_txns.sort(key=lambda t: t.timestamp)

            # Look for in-out pairs
            for i, txn_in in enumerate(account_txns):
                if txn_in.to_account != account:
                    continue

                for txn_out in account_txns[i + 1 :]:
                    if txn_out.from_account != account:
                        continue

                    if txn_out.timestamp - txn_in.timestamp > window:
                        break

                    # Check if amounts are similar
                    amount_diff = abs(txn_in.amount - txn_out.amount)
                    amount_ratio = amount_diff / max(txn_in.amount, txn_out.amount)

                    if amount_ratio < 0.1:  # Within 10%
                        hours = (txn_out.timestamp - txn_in.timestamp).total_seconds() / 3600
                        confidence = min(1.0, 0.5 + (48 - hours) / 48 * 0.4)

                        patterns.append(
                            PatternMatch(
                                pattern_type=PatternType.RAPID_IN_OUT,
                                confidence=confidence,
                                description=f"Rapid in-out: {txn_in.amount:,.0f} SEK in, {txn_out.amount:,.0f} SEK out within {hours:.1f} hours",
                                transaction_ids=[txn_in.id, txn_out.id],
                                metadata={
                                    "account": account,
                                    "amount_in": txn_in.amount,
                                    "amount_out": txn_out.amount,
                                    "hours_between": hours,
                                },
                            )
                        )

        return patterns

    def detect_unusual_times(
        self,
        transactions: list[Transaction],
    ) -> list[PatternMatch]:
        """
        Detect transactions at unusual times.

        Business transactions late at night or on weekends
        can be suspicious.
        """
        patterns = []

        for txn in transactions:
            hour = txn.timestamp.hour
            weekday = txn.timestamp.weekday()

            is_unusual = False
            reason = ""

            # Late night (midnight to 5am)
            if 0 <= hour < 5:
                is_unusual = True
                reason = f"late night ({hour:02d}:00)"

            # Weekend for business transactions
            if weekday >= 5 and txn.amount > 50_000:
                is_unusual = True
                reason = "weekend (large amount)"

            if is_unusual:
                confidence = 0.4 + min(0.3, txn.amount / 500_000)
                patterns.append(
                    PatternMatch(
                        pattern_type=PatternType.UNUSUAL_TIME,
                        confidence=confidence,
                        description=f"Transaction at unusual time: {reason}",
                        transaction_ids=[txn.id],
                        entity_ids=[
                            e
                            for e in [txn.from_entity_id, txn.to_entity_id]
                            if e is not None
                        ],
                        metadata={
                            "hour": hour,
                            "weekday": weekday,
                            "amount": txn.amount,
                        },
                    )
                )

        return patterns
