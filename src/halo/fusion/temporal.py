"""
Temporal analysis for event sequencing and pattern detection.

Analyzes timing patterns across entities and events to identify:
- Coordinated activities
- Suspicious timing patterns
- Event sequences indicating organized crime
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of events for temporal analysis."""

    COMPANY_REGISTRATION = "company_registration"
    COMPANY_DISSOLUTION = "company_dissolution"
    DIRECTOR_APPOINTMENT = "director_appointment"
    DIRECTOR_RESIGNATION = "director_resignation"
    ADDRESS_CHANGE = "address_change"
    OWNERSHIP_TRANSFER = "ownership_transfer"
    TRANSACTION = "transaction"
    BENEFIT_CLAIM = "benefit_claim"
    PROPERTY_TRANSFER = "property_transfer"
    LEGAL_ACTION = "legal_action"


class PatternType(str, Enum):
    """Types of temporal patterns."""

    BURST = "burst"  # Many events in short period
    SEQUENCE = "sequence"  # Ordered series of events
    PERIODIC = "periodic"  # Repeating at intervals
    COORDINATED = "coordinated"  # Multiple entities acting together
    SUSPICIOUS_TIMING = "suspicious_timing"  # Events timed to avoid detection


@dataclass
class TimelineEvent:
    """An event on a timeline."""

    id: UUID
    entity_id: UUID
    event_type: EventType
    occurred_at: datetime
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id),
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at.isoformat(),
            "description": self.description,
            "metadata": self.metadata,
        }


@dataclass
class TemporalPattern:
    """A detected temporal pattern."""

    pattern_type: PatternType
    events: list[TimelineEvent]
    entity_ids: list[UUID]
    start_time: datetime
    end_time: datetime
    confidence: float  # 0.0 to 1.0
    description: str
    risk_score: float = 0.0

    def duration(self) -> timedelta:
        """Get pattern duration."""
        return self.end_time - self.start_time

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pattern_type": self.pattern_type.value,
            "events": [e.to_dict() for e in self.events],
            "entity_ids": [str(eid) for eid in self.entity_ids],
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": self.duration().total_seconds(),
            "confidence": self.confidence,
            "description": self.description,
            "risk_score": self.risk_score,
        }


class TemporalAnalyzer:
    """
    Analyzes temporal patterns in event data.

    Detects suspicious timing patterns that may indicate
    coordinated criminal activity.
    """

    def __init__(
        self,
        burst_threshold: timedelta = timedelta(hours=24),
        burst_min_events: int = 3,
        coordination_window: timedelta = timedelta(hours=1),
    ):
        self.burst_threshold = burst_threshold
        self.burst_min_events = burst_min_events
        self.coordination_window = coordination_window
        self._events: list[TimelineEvent] = []

    def add_event(self, event: TimelineEvent) -> None:
        """Add an event to the timeline."""
        self._events.append(event)
        self._events.sort(key=lambda e: e.occurred_at)

    def add_events(self, events: list[TimelineEvent]) -> None:
        """Add multiple events to the timeline."""
        self._events.extend(events)
        self._events.sort(key=lambda e: e.occurred_at)

    def get_timeline(
        self,
        entity_id: Optional[UUID] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        event_types: Optional[list[EventType]] = None,
    ) -> list[TimelineEvent]:
        """
        Get filtered timeline of events.

        Args:
            entity_id: Filter by entity
            start: Start time filter
            end: End time filter
            event_types: Filter by event types

        Returns:
            Filtered list of events
        """
        events = self._events

        if entity_id:
            events = [e for e in events if e.entity_id == entity_id]
        if start:
            events = [e for e in events if e.occurred_at >= start]
        if end:
            events = [e for e in events if e.occurred_at <= end]
        if event_types:
            events = [e for e in events if e.event_type in event_types]

        return events

    def detect_bursts(
        self,
        entity_id: Optional[UUID] = None,
    ) -> list[TemporalPattern]:
        """
        Detect burst patterns (many events in short time).

        Args:
            entity_id: Filter by entity

        Returns:
            List of detected burst patterns
        """
        events = self.get_timeline(entity_id=entity_id)
        patterns = []

        if len(events) < self.burst_min_events:
            return patterns

        # Sliding window to find bursts
        for i, event in enumerate(events):
            window_end = event.occurred_at + self.burst_threshold
            window_events = [
                e for e in events[i:]
                if e.occurred_at <= window_end
            ]

            if len(window_events) >= self.burst_min_events:
                # Found a burst
                entity_ids = list(set(e.entity_id for e in window_events))
                pattern = TemporalPattern(
                    pattern_type=PatternType.BURST,
                    events=window_events,
                    entity_ids=entity_ids,
                    start_time=window_events[0].occurred_at,
                    end_time=window_events[-1].occurred_at,
                    confidence=min(1.0, len(window_events) / 10),
                    description=f"Burst of {len(window_events)} events in {self.burst_threshold}",
                    risk_score=self._calculate_burst_risk(window_events),
                )
                patterns.append(pattern)

        return self._deduplicate_patterns(patterns)

    def detect_coordinated_activity(
        self,
        entity_ids: list[UUID],
    ) -> list[TemporalPattern]:
        """
        Detect coordinated activity across multiple entities.

        Args:
            entity_ids: Entities to check for coordination

        Returns:
            List of detected coordination patterns
        """
        patterns = []

        # Get events for all entities
        entity_events = {
            eid: self.get_timeline(entity_id=eid)
            for eid in entity_ids
        }

        # Find overlapping windows
        all_events = []
        for events in entity_events.values():
            all_events.extend(events)
        all_events.sort(key=lambda e: e.occurred_at)

        for event in all_events:
            window_start = event.occurred_at
            window_end = window_start + self.coordination_window

            # Find events from different entities in this window
            window_events = [
                e for e in all_events
                if window_start <= e.occurred_at <= window_end
            ]

            participating_entities = set(e.entity_id for e in window_events)

            if len(participating_entities) >= 2:
                pattern = TemporalPattern(
                    pattern_type=PatternType.COORDINATED,
                    events=window_events,
                    entity_ids=list(participating_entities),
                    start_time=window_start,
                    end_time=window_end,
                    confidence=len(participating_entities) / len(entity_ids),
                    description=(
                        f"Coordinated activity: {len(participating_entities)} entities "
                        f"within {self.coordination_window}"
                    ),
                    risk_score=self._calculate_coordination_risk(
                        window_events, participating_entities
                    ),
                )
                patterns.append(pattern)

        return self._deduplicate_patterns(patterns)

    def detect_sequences(
        self,
        entity_id: UUID,
        sequence_types: list[EventType],
    ) -> list[TemporalPattern]:
        """
        Detect specific event sequences.

        Args:
            entity_id: Entity to analyze
            sequence_types: Expected sequence of event types

        Returns:
            List of detected sequences
        """
        events = self.get_timeline(entity_id=entity_id)
        patterns = []

        if len(events) < len(sequence_types):
            return patterns

        # Look for matching sequences
        for i in range(len(events) - len(sequence_types) + 1):
            window = events[i:i + len(sequence_types)]
            types = [e.event_type for e in window]

            if types == sequence_types:
                pattern = TemporalPattern(
                    pattern_type=PatternType.SEQUENCE,
                    events=window,
                    entity_ids=[entity_id],
                    start_time=window[0].occurred_at,
                    end_time=window[-1].occurred_at,
                    confidence=1.0,
                    description=(
                        f"Detected sequence: {' -> '.join(t.value for t in sequence_types)}"
                    ),
                    risk_score=0.5,  # Base risk for matching sequence
                )
                patterns.append(pattern)

        return patterns

    def _calculate_burst_risk(self, events: list[TimelineEvent]) -> float:
        """Calculate risk score for a burst pattern."""
        # More events = higher risk
        event_risk = min(1.0, len(events) / 20)

        # Multiple event types = higher risk
        unique_types = len(set(e.event_type for e in events))
        type_risk = min(1.0, unique_types / 5)

        # Shorter duration = higher risk
        if len(events) >= 2:
            duration = (events[-1].occurred_at - events[0].occurred_at).total_seconds()
            duration_risk = 1.0 / (1.0 + duration / 3600)  # Inverse of hours
        else:
            duration_risk = 1.0

        return (event_risk + type_risk + duration_risk) / 3

    def _calculate_coordination_risk(
        self,
        events: list[TimelineEvent],
        entities: set[UUID],
    ) -> float:
        """Calculate risk score for coordinated activity."""
        # More entities = higher risk
        entity_risk = min(1.0, len(entities) / 5)

        # Similar event types = higher risk (suggests coordination)
        types = [e.event_type for e in events]
        type_similarity = types.count(types[0]) / len(types) if types else 0

        return (entity_risk + type_similarity) / 2

    def _deduplicate_patterns(
        self,
        patterns: list[TemporalPattern],
    ) -> list[TemporalPattern]:
        """Remove overlapping patterns, keeping highest confidence."""
        if not patterns:
            return []

        # Sort by confidence descending
        patterns.sort(key=lambda p: p.confidence, reverse=True)

        unique = []
        for pattern in patterns:
            # Check if overlaps with existing pattern
            overlaps = False
            for existing in unique:
                if (
                    pattern.start_time <= existing.end_time and
                    pattern.end_time >= existing.start_time
                ):
                    # Check for significant event overlap
                    pattern_event_ids = {e.id for e in pattern.events}
                    existing_event_ids = {e.id for e in existing.events}
                    overlap = len(pattern_event_ids & existing_event_ids)
                    if overlap >= len(pattern.events) / 2:
                        overlaps = True
                        break

            if not overlaps:
                unique.append(pattern)

        return unique
