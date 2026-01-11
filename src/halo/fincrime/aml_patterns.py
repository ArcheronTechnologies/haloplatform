"""
AML (Anti-Money Laundering) pattern detection.

Implements detection for common money laundering typologies:
- Structuring (smurfing) - breaking large amounts into smaller ones
- Layering - complex transaction chains to obscure origin
- Rapid movement - quick in-and-out of funds
- Round-tripping - funds returning to origin through intermediaries
- Trade-based laundering - over/under invoicing
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


def _normalize_transaction(txn) -> dict:
    """
    Normalize a transaction to dict format.

    Handles both dict transactions and TransactionForAnalysis dataclass objects.
    """
    if isinstance(txn, dict):
        return txn
    # Handle TransactionForAnalysis dataclass
    return {
        "id": getattr(txn, "id", None),
        "entity_id": getattr(txn, "entity_id", None),
        "from_entity_id": getattr(txn, "entity_id", None),  # Use entity_id as sender
        "to_entity_id": getattr(txn, "counterparty_id", None),
        "amount": getattr(txn, "amount", 0),
        "currency": getattr(txn, "currency", "SEK"),
        "timestamp": getattr(txn, "timestamp", datetime.utcnow()),
        "transaction_type": getattr(txn, "transaction_type", ""),
        "counterparty_id": getattr(txn, "counterparty_id", None),
        "counterparty_name": getattr(txn, "counterparty_name", None),
        "metadata": getattr(txn, "metadata", {}),
    }


class PatternSeverity(str, Enum):
    """Severity levels for pattern matches."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TransactionForAnalysis:
    """Transaction data structure for AML analysis."""

    id: UUID
    entity_id: UUID
    amount: Decimal
    currency: str
    timestamp: datetime
    transaction_type: str
    counterparty_id: Optional[UUID] = None
    counterparty_name: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PatternMatch:
    """A detected AML pattern match."""

    pattern_type: str
    severity: PatternSeverity
    confidence: float  # 0.0 to 1.0
    description: str

    # Entities involved
    entity_ids: list[UUID] = field(default_factory=list)

    # Transactions involved
    transaction_ids: list[UUID] = field(default_factory=list)

    # Pattern-specific details
    details: dict[str, Any] = field(default_factory=dict)

    # Temporal info
    detected_at: datetime = field(default_factory=datetime.utcnow)
    pattern_start: Optional[datetime] = None
    pattern_end: Optional[datetime] = None

    # Total amount involved
    total_amount: Optional[Decimal] = None
    currency: str = "SEK"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/API."""
        return {
            "pattern_type": self.pattern_type,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "description": self.description,
            "entity_ids": [str(e) for e in self.entity_ids],
            "transaction_ids": [str(t) for t in self.transaction_ids],
            "details": self.details,
            "detected_at": self.detected_at.isoformat(),
            "pattern_start": self.pattern_start.isoformat() if self.pattern_start else None,
            "pattern_end": self.pattern_end.isoformat() if self.pattern_end else None,
            "total_amount": str(self.total_amount) if self.total_amount else None,
            "currency": self.currency,
        }


class AMLPattern(ABC):
    """Base class for AML pattern detectors."""

    @property
    @abstractmethod
    def pattern_type(self) -> str:
        """Unique identifier for this pattern type."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the pattern."""
        pass

    @abstractmethod
    def detect(
        self,
        transactions: list[dict],
        entity_id: Optional[UUID] = None,
    ) -> list[PatternMatch]:
        """
        Detect pattern in transactions.

        Args:
            transactions: List of transaction dicts with keys:
                - id: UUID
                - amount: Decimal
                - currency: str
                - timestamp: datetime
                - from_entity_id: UUID
                - to_entity_id: UUID
                - transaction_type: str
            entity_id: Optional entity to focus analysis on

        Returns:
            List of detected pattern matches
        """
        pass


class StructuringDetector(AMLPattern):
    """
    Detect structuring (smurfing) patterns.

    Structuring = breaking large transactions into smaller ones
    to avoid reporting thresholds.

    Swedish threshold: 150,000 SEK for cash transactions
    EU threshold: 10,000 EUR for cross-border
    """

    # Swedish reporting threshold for cash
    SWEDISH_CASH_THRESHOLD = Decimal("150000")

    # Common structuring patterns
    JUST_UNDER_THRESHOLD = Decimal("0.95")  # 95% of threshold
    LOOKBACK_DAYS = 7

    @property
    def pattern_type(self) -> str:
        return "structuring"

    @property
    def description(self) -> str:
        return "Multiple transactions just below reporting threshold"

    def __init__(
        self,
        threshold: Decimal = SWEDISH_CASH_THRESHOLD,
        lookback_days: int = LOOKBACK_DAYS,
        min_transactions: int = 3,
    ):
        self.threshold = threshold
        self.lookback_days = lookback_days
        self.min_transactions = min_transactions

    def detect(
        self,
        transactions: list,
        entity_id: Optional[UUID] = None,
    ) -> list[PatternMatch]:
        matches = []

        # Normalize all transactions to dicts
        normalized = [_normalize_transaction(t) for t in transactions]

        # Filter to relevant entity if specified
        if entity_id:
            normalized = [
                t for t in normalized
                if t.get("from_entity_id") == entity_id or t.get("to_entity_id") == entity_id
                   or t.get("entity_id") == entity_id
            ]

        # Group by sender (use entity_id if from_entity_id not present)
        by_sender: dict[UUID, list[dict]] = {}
        for txn in normalized:
            sender = txn.get("from_entity_id") or txn.get("entity_id")
            if sender:
                by_sender.setdefault(sender, []).append(txn)

        # Check each sender for structuring
        for sender_id, sender_txns in by_sender.items():
            # Sort by timestamp
            sender_txns.sort(key=lambda t: t.get("timestamp", datetime.min))

            # Sliding window analysis
            window_txns = []
            for txn in sender_txns:
                txn_time = txn.get("timestamp", datetime.utcnow())
                window_start = txn_time - timedelta(days=self.lookback_days)

                # Remove old transactions from window
                window_txns = [
                    t for t in window_txns
                    if t.get("timestamp", datetime.min) >= window_start
                ]
                window_txns.append(txn)

                # Check for structuring pattern
                just_under = [
                    t for t in window_txns
                    if self._is_just_under_threshold(Decimal(str(t.get("amount", 0))))
                ]

                if len(just_under) >= self.min_transactions:
                    total = sum(Decimal(str(t.get("amount", 0))) for t in just_under)

                    # Only flag if total would have exceeded threshold
                    if total >= self.threshold:
                        confidence = min(0.95, 0.5 + (len(just_under) - self.min_transactions) * 0.1)

                        matches.append(PatternMatch(
                            pattern_type=self.pattern_type,
                            severity=self._calculate_severity(total, len(just_under)),
                            confidence=confidence,
                            description=f"{len(just_under)} transactions just below {self.threshold} SEK threshold in {self.lookback_days} days",
                            entity_ids=[sender_id],
                            transaction_ids=[t.get("id") for t in just_under if t.get("id")],
                            total_amount=total,
                            pattern_start=just_under[0].get("timestamp"),
                            pattern_end=just_under[-1].get("timestamp"),
                            details={
                                "threshold": str(self.threshold),
                                "transaction_count": len(just_under),
                                "average_amount": str(total / len(just_under)),
                            },
                        ))

        return matches

    def _is_just_under_threshold(self, amount: Decimal) -> bool:
        """Check if amount is suspiciously close to threshold."""
        lower_bound = self.threshold * self.JUST_UNDER_THRESHOLD
        return lower_bound <= amount < self.threshold

    def _calculate_severity(self, total: Decimal, count: int) -> PatternSeverity:
        """Calculate severity based on total amount and transaction count."""
        if total >= self.threshold * 5 or count >= 10:
            return PatternSeverity.CRITICAL
        elif total >= self.threshold * 3 or count >= 7:
            return PatternSeverity.HIGH
        elif total >= self.threshold * 2 or count >= 5:
            return PatternSeverity.MEDIUM
        return PatternSeverity.LOW


class LayeringDetector(AMLPattern):
    """
    Detect layering patterns.

    Layering = moving money through multiple accounts/entities
    to obscure the origin.

    Indicators:
    - Funds move through 3+ entities quickly
    - No apparent business purpose
    - Circular patterns
    """

    @property
    def pattern_type(self) -> str:
        return "layering"

    @property
    def description(self) -> str:
        return "Complex transaction chains obscuring fund origin"

    def __init__(
        self,
        min_hops: int = 3,
        max_hours: int = 72,
        min_amount: Decimal = Decimal("50000"),
    ):
        self.min_hops = min_hops
        self.max_hours = max_hours
        self.min_amount = min_amount

    def detect(
        self,
        transactions: list,
        entity_id: Optional[UUID] = None,
    ) -> list[PatternMatch]:
        matches = []

        # Normalize all transactions to dicts
        normalized = [_normalize_transaction(t) for t in transactions]

        # Build transaction graph
        # Node = entity, Edge = transaction
        graph: dict[UUID, list[dict]] = {}
        for txn in normalized:
            sender = txn.get("from_entity_id") or txn.get("entity_id")
            if sender:
                graph.setdefault(sender, []).append(txn)

        # Find chains starting from each entity
        checked_chains: set[tuple] = set()

        for start_entity in graph:
            if entity_id and start_entity != entity_id:
                continue

            chains = self._find_chains(graph, start_entity, [], set())

            for chain in chains:
                if len(chain) >= self.min_hops:
                    chain_key = tuple(t.get("id") for t in chain)
                    if chain_key in checked_chains:
                        continue
                    checked_chains.add(chain_key)

                    # Check timing
                    first_time = chain[0].get("timestamp", datetime.utcnow())
                    last_time = chain[-1].get("timestamp", datetime.utcnow())
                    hours = (last_time - first_time).total_seconds() / 3600

                    if hours <= self.max_hours:
                        # Check amounts (should be similar, minus fees)
                        amounts = [Decimal(str(t.get("amount", 0))) for t in chain]
                        if min(amounts) >= self.min_amount:
                            entities = self._extract_entities(chain)

                            matches.append(PatternMatch(
                                pattern_type=self.pattern_type,
                                severity=self._calculate_severity(len(chain), min(amounts)),
                                confidence=0.7 + min(0.25, len(chain) * 0.05),
                                description=f"Funds moved through {len(entities)} entities in {hours:.1f} hours",
                                entity_ids=entities,
                                transaction_ids=[t.get("id") for t in chain if t.get("id")],
                                total_amount=amounts[0],
                                pattern_start=first_time,
                                pattern_end=last_time,
                                details={
                                    "hop_count": len(chain),
                                    "hours_elapsed": hours,
                                    "entity_count": len(entities),
                                },
                            ))

        return matches

    def _find_chains(
        self,
        graph: dict[UUID, list[dict]],
        current: UUID,
        path: list[dict],
        visited: set[UUID],
        max_depth: int = 10,
    ) -> list[list[dict]]:
        """Find transaction chains using DFS."""
        if len(path) >= max_depth or current in visited:
            return [path] if len(path) >= self.min_hops else []

        visited = visited | {current}
        chains = []

        for txn in graph.get(current, []):
            next_entity = txn.get("to_entity_id")
            if next_entity and next_entity not in visited:
                # Check timing continuity
                if path:
                    last_time = path[-1].get("timestamp", datetime.min)
                    this_time = txn.get("timestamp", datetime.max)
                    if this_time < last_time:
                        continue

                new_chains = self._find_chains(
                    graph, next_entity, path + [txn], visited, max_depth
                )
                chains.extend(new_chains)

        if not chains and len(path) >= self.min_hops:
            chains = [path]

        return chains

    def _extract_entities(self, chain: list[dict]) -> list[UUID]:
        """Extract unique entities from transaction chain."""
        entities = []
        seen = set()
        for txn in chain:
            for key in ["from_entity_id", "to_entity_id"]:
                eid = txn.get(key)
                if eid and eid not in seen:
                    entities.append(eid)
                    seen.add(eid)
        return entities

    def _calculate_severity(self, hops: int, amount: Decimal) -> PatternSeverity:
        """Calculate severity based on complexity and amount."""
        if hops >= 7 or amount >= Decimal("1000000"):
            return PatternSeverity.CRITICAL
        elif hops >= 5 or amount >= Decimal("500000"):
            return PatternSeverity.HIGH
        elif hops >= 4 or amount >= Decimal("200000"):
            return PatternSeverity.MEDIUM
        return PatternSeverity.LOW


class RapidMovementDetector(AMLPattern):
    """
    Detect rapid movement of funds.

    Pattern: Funds deposited and withdrawn quickly
    with no apparent business purpose.
    """

    @property
    def pattern_type(self) -> str:
        return "rapid_movement"

    @property
    def description(self) -> str:
        return "Funds deposited and withdrawn within short timeframe"

    def __init__(
        self,
        max_hours: int = 24,
        min_amount: Decimal = Decimal("100000"),
        min_percentage: float = 0.8,
    ):
        self.max_hours = max_hours
        self.min_amount = min_amount
        self.min_percentage = min_percentage

    def detect(
        self,
        transactions: list,
        entity_id: Optional[UUID] = None,
    ) -> list[PatternMatch]:
        matches = []

        # Normalize all transactions to dicts
        normalized = [_normalize_transaction(t) for t in transactions]

        # Group by entity
        by_entity: dict[UUID, list[dict]] = {}
        for txn in normalized:
            eid = txn.get("entity_id") or txn.get("from_entity_id")
            if eid:
                if not entity_id or eid == entity_id:
                    by_entity.setdefault(eid, []).append(txn)

        for eid, txns in by_entity.items():
            # Classify as inbound/outbound based on transaction type
            inbound = [t for t in txns if t.get("transaction_type") in ("deposit", "credit") or t.get("to_entity_id") == eid]
            outbound = [t for t in txns if t.get("transaction_type") in ("withdrawal", "debit", "transfer") or t.get("from_entity_id") == eid]

            # Sort by time
            inbound.sort(key=lambda t: t.get("timestamp", datetime.min))
            outbound.sort(key=lambda t: t.get("timestamp", datetime.min))

            # Check for rapid in-out patterns
            for in_txn in inbound:
                in_amount = Decimal(str(in_txn.get("amount", 0)))
                in_time = in_txn.get("timestamp", datetime.utcnow())

                if in_amount < self.min_amount:
                    continue

                # Find outbound within window
                window_end = in_time + timedelta(hours=self.max_hours)
                out_in_window = [
                    t for t in outbound
                    if in_time <= t.get("timestamp", datetime.min) <= window_end
                ]

                out_total = sum(Decimal(str(t.get("amount", 0))) for t in out_in_window)

                if out_total >= in_amount * Decimal(str(self.min_percentage)):
                    hours = max(
                        (t.get("timestamp", in_time) - in_time).total_seconds() / 3600
                        for t in out_in_window
                    ) if out_in_window else 0

                    matches.append(PatternMatch(
                        pattern_type=self.pattern_type,
                        severity=self._calculate_severity(in_amount, hours),
                        confidence=0.75,
                        description=f"{in_amount} SEK deposited and {out_total} SEK withdrawn within {hours:.1f} hours",
                        entity_ids=[eid],
                        transaction_ids=[in_txn.get("id")] + [t.get("id") for t in out_in_window],
                        total_amount=in_amount,
                        pattern_start=in_time,
                        pattern_end=out_in_window[-1].get("timestamp") if out_in_window else in_time,
                        details={
                            "inbound_amount": str(in_amount),
                            "outbound_amount": str(out_total),
                            "hours_elapsed": hours,
                            "outbound_count": len(out_in_window),
                        },
                    ))

        return matches

    def _calculate_severity(self, amount: Decimal, hours: float) -> PatternSeverity:
        """Calculate severity based on amount and speed."""
        if amount >= Decimal("1000000") or hours <= 2:
            return PatternSeverity.CRITICAL
        elif amount >= Decimal("500000") or hours <= 6:
            return PatternSeverity.HIGH
        elif amount >= Decimal("200000") or hours <= 12:
            return PatternSeverity.MEDIUM
        return PatternSeverity.LOW


class RoundTripDetector(AMLPattern):
    """
    Detect round-trip transactions.

    Pattern: Funds return to original entity through
    intermediaries, potentially with small "fees" removed.
    """

    @property
    def pattern_type(self) -> str:
        return "round_trip"

    @property
    def description(self) -> str:
        return "Funds returning to origin through intermediaries"

    def __init__(
        self,
        min_amount: Decimal = Decimal("50000"),
        max_days: int = 30,
        max_loss_percentage: float = 0.15,
    ):
        self.min_amount = min_amount
        self.max_days = max_days
        self.max_loss_percentage = max_loss_percentage

    def detect(
        self,
        transactions: list,
        entity_id: Optional[UUID] = None,
    ) -> list[PatternMatch]:
        matches = []

        # Normalize all transactions to dicts
        normalized = [_normalize_transaction(t) for t in transactions]

        # Build graph with amounts
        graph: dict[UUID, list[dict]] = {}
        for txn in normalized:
            sender = txn.get("from_entity_id") or txn.get("entity_id")
            if sender:
                graph.setdefault(sender, []).append(txn)

        # For each entity, check if funds return
        checked_patterns: set[tuple] = set()

        for start_entity in graph:
            if entity_id and start_entity != entity_id:
                continue

            # Find paths that return to start
            round_trips = self._find_round_trips(graph, start_entity)

            for trip in round_trips:
                if len(trip) < 2:
                    continue

                trip_key = tuple(sorted(str(t.get("id")) for t in trip))
                if trip_key in checked_patterns:
                    continue
                checked_patterns.add(trip_key)

                # Check amounts (should be similar minus fees)
                start_amount = Decimal(str(trip[0].get("amount", 0)))
                end_amount = Decimal(str(trip[-1].get("amount", 0)))

                if start_amount >= self.min_amount:
                    loss = (start_amount - end_amount) / start_amount
                    if loss <= self.max_loss_percentage:
                        entities = self._extract_entities(trip)
                        first_time = trip[0].get("timestamp", datetime.utcnow())
                        last_time = trip[-1].get("timestamp", datetime.utcnow())
                        days = (last_time - first_time).days

                        if days <= self.max_days:
                            matches.append(PatternMatch(
                                pattern_type=self.pattern_type,
                                severity=self._calculate_severity(start_amount, len(entities)),
                                confidence=0.8,
                                description=f"Funds returned to origin via {len(entities) - 1} intermediaries",
                                entity_ids=entities,
                                transaction_ids=[t.get("id") for t in trip if t.get("id")],
                                total_amount=start_amount,
                                pattern_start=first_time,
                                pattern_end=last_time,
                                details={
                                    "start_amount": str(start_amount),
                                    "end_amount": str(end_amount),
                                    "loss_percentage": float(loss * 100),
                                    "intermediary_count": len(entities) - 1,
                                    "days_elapsed": days,
                                },
                            ))

        return matches

    def _find_round_trips(
        self,
        graph: dict[UUID, list[dict]],
        start: UUID,
        max_depth: int = 8,
    ) -> list[list[dict]]:
        """Find transaction paths that return to start."""
        round_trips = []

        def dfs(current: UUID, path: list[dict], visited: set[UUID]):
            if len(path) >= max_depth:
                return

            for txn in graph.get(current, []):
                next_entity = txn.get("to_entity_id")
                if next_entity == start and len(path) >= 1:
                    # Found round trip
                    round_trips.append(path + [txn])
                elif next_entity and next_entity not in visited:
                    dfs(next_entity, path + [txn], visited | {next_entity})

        dfs(start, [], {start})
        return round_trips

    def _extract_entities(self, chain: list[dict]) -> list[UUID]:
        """Extract unique entities from transaction chain."""
        entities = []
        seen = set()
        for txn in chain:
            for key in ["from_entity_id", "to_entity_id"]:
                eid = txn.get(key)
                if eid and eid not in seen:
                    entities.append(eid)
                    seen.add(eid)
        return entities

    def _calculate_severity(self, amount: Decimal, entities: int) -> PatternSeverity:
        """Calculate severity based on amount and complexity."""
        if amount >= Decimal("1000000") or entities >= 6:
            return PatternSeverity.CRITICAL
        elif amount >= Decimal("500000") or entities >= 4:
            return PatternSeverity.HIGH
        elif amount >= Decimal("200000") or entities >= 3:
            return PatternSeverity.MEDIUM
        return PatternSeverity.LOW


class SmurfingDetector(AMLPattern):
    """
    Detect smurfing patterns.

    Smurfing = using multiple people to make small deposits
    that aggregate to a large amount.
    """

    @property
    def pattern_type(self) -> str:
        return "smurfing"

    @property
    def description(self) -> str:
        return "Multiple depositors aggregating to single recipient"

    def __init__(
        self,
        min_depositors: int = 3,
        min_aggregate: Decimal = Decimal("150000"),
        max_days: int = 7,
    ):
        self.min_depositors = min_depositors
        self.min_aggregate = min_aggregate
        self.max_days = max_days

    def detect(
        self,
        transactions: list,
        entity_id: Optional[UUID] = None,
    ) -> list[PatternMatch]:
        matches = []

        # Normalize all transactions to dicts
        normalized = [_normalize_transaction(t) for t in transactions]

        # Group by recipient (for smurfing, recipient is entity_id for deposits)
        by_recipient: dict[UUID, list[dict]] = {}
        for txn in normalized:
            # For deposits to an entity, the entity is the recipient
            if txn.get("transaction_type") == "deposit":
                recipient = txn.get("entity_id")
            else:
                recipient = txn.get("to_entity_id") or txn.get("entity_id")
            if recipient:
                if not entity_id or recipient == entity_id:
                    by_recipient.setdefault(recipient, []).append(txn)

        for recipient_id, txns in by_recipient.items():
            # Sort by time
            txns.sort(key=lambda t: t.get("timestamp", datetime.min))

            # Sliding window
            window_txns = []
            for txn in txns:
                txn_time = txn.get("timestamp", datetime.utcnow())
                window_start = txn_time - timedelta(days=self.max_days)

                # Remove old
                window_txns = [
                    t for t in window_txns
                    if t.get("timestamp", datetime.min) >= window_start
                ]
                window_txns.append(txn)

                # Count unique depositors (from counterparty_id for deposits)
                depositors = set()
                for t in window_txns:
                    depositor = t.get("counterparty_id") or t.get("from_entity_id")
                    if depositor:
                        depositors.add(depositor)

                if len(depositors) >= self.min_depositors:
                    total = sum(Decimal(str(t.get("amount", 0))) for t in window_txns)

                    if total >= self.min_aggregate:
                        first_time = window_txns[0].get("timestamp")
                        last_time = window_txns[-1].get("timestamp")

                        matches.append(PatternMatch(
                            pattern_type=self.pattern_type,
                            severity=self._calculate_severity(total, len(depositors)),
                            confidence=0.7 + min(0.25, (len(depositors) - self.min_depositors) * 0.05),
                            description=f"{len(depositors)} depositors sent {total} SEK to single recipient",
                            entity_ids=[recipient_id] + list(depositors),
                            transaction_ids=[t.get("id") for t in window_txns if t.get("id")],
                            total_amount=total,
                            pattern_start=first_time,
                            pattern_end=last_time,
                            details={
                                "depositor_count": len(depositors),
                                "transaction_count": len(window_txns),
                                "average_deposit": str(total / len(window_txns)),
                            },
                        ))

        return matches

    def _calculate_severity(self, amount: Decimal, depositors: int) -> PatternSeverity:
        """Calculate severity based on amount and depositor count."""
        if amount >= Decimal("1000000") or depositors >= 10:
            return PatternSeverity.CRITICAL
        elif amount >= Decimal("500000") or depositors >= 7:
            return PatternSeverity.HIGH
        elif amount >= Decimal("200000") or depositors >= 5:
            return PatternSeverity.MEDIUM
        return PatternSeverity.LOW


class AMLPatternDetector:
    """
    Orchestrates multiple AML pattern detectors.

    Usage:
        detector = AMLPatternDetector()
        matches = detector.detect_all(transactions)
    """

    def __init__(self, detectors: Optional[list[AMLPattern]] = None):
        """
        Initialize with pattern detectors.

        Args:
            detectors: List of pattern detectors (uses defaults if None)
        """
        self.detectors = detectors or [
            StructuringDetector(),
            LayeringDetector(),
            RapidMovementDetector(),
            RoundTripDetector(),
            SmurfingDetector(),
        ]

    def detect_all(
        self,
        transactions: list,
        entity_id: Optional[UUID] = None,
    ) -> list[PatternMatch]:
        """
        Run all pattern detectors on transactions.

        Args:
            transactions: List of transaction dicts or TransactionForAnalysis objects
            entity_id: Optional entity to focus analysis on

        Returns:
            All pattern matches from all detectors
        """
        all_matches = []

        for detector in self.detectors:
            try:
                matches = detector.detect(transactions, entity_id)
                all_matches.extend(matches)
                logger.debug(f"{detector.pattern_type}: found {len(matches)} matches")
            except Exception as e:
                logger.error(f"Error in {detector.pattern_type} detector: {e}")

        # Sort by severity and confidence
        severity_order = {
            PatternSeverity.CRITICAL: 0,
            PatternSeverity.HIGH: 1,
            PatternSeverity.MEDIUM: 2,
            PatternSeverity.LOW: 3,
        }
        all_matches.sort(key=lambda m: (severity_order[m.severity], -m.confidence))

        return all_matches

    def detect_pattern(
        self,
        pattern_type: str,
        transactions: list[dict],
        entity_id: Optional[UUID] = None,
    ) -> list[PatternMatch]:
        """
        Run a specific pattern detector.

        Args:
            pattern_type: Type of pattern to detect
            transactions: List of transaction dicts
            entity_id: Optional entity to focus analysis on

        Returns:
            Pattern matches from the specified detector
        """
        for detector in self.detectors:
            if detector.pattern_type == pattern_type:
                return detector.detect(transactions, entity_id)

        raise ValueError(f"Unknown pattern type: {pattern_type}")

    def add_detector(self, detector: AMLPattern) -> None:
        """Add a custom pattern detector."""
        self.detectors.append(detector)
