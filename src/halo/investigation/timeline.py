"""
Timeline reconstruction for investigations.

Builds chronological views of events related to an investigation.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of timeline events."""

    TRANSACTION = "transaction"
    COMMUNICATION = "communication"
    DOCUMENT = "document"
    ENTITY_CHANGE = "entity_change"  # Company registration, address change, etc.
    RELATIONSHIP = "relationship"  # New connection between entities
    ALERT = "alert"
    INVESTIGATION = "investigation"  # Case actions
    REGULATORY = "regulatory"  # Filings, reports
    EXTERNAL = "external"  # News, public events
    CUSTOM = "custom"


class EventSeverity(str, Enum):
    """Importance/severity of event."""

    INFO = "info"
    MINOR = "minor"
    MODERATE = "moderate"
    SIGNIFICANT = "significant"
    CRITICAL = "critical"


@dataclass
class TimelineEvent:
    """An event on the timeline."""

    id: UUID = field(default_factory=uuid4)
    event_type: EventType = EventType.CUSTOM
    severity: EventSeverity = EventSeverity.INFO

    # Timing
    timestamp: datetime = field(default_factory=datetime.utcnow)
    end_timestamp: Optional[datetime] = None  # For events with duration

    # Description
    title: str = ""
    description: str = ""

    # Related items
    entity_ids: list[UUID] = field(default_factory=list)
    transaction_ids: list[UUID] = field(default_factory=list)
    evidence_ids: list[UUID] = field(default_factory=list)
    case_ids: list[UUID] = field(default_factory=list)

    # Source
    source: str = ""  # Where this event came from
    source_id: Optional[str] = None

    # Additional data
    metadata: dict[str, Any] = field(default_factory=dict)

    # Display
    icon: str = ""
    color: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "end_timestamp": self.end_timestamp.isoformat() if self.end_timestamp else None,
            "title": self.title,
            "description": self.description,
            "entity_ids": [str(e) for e in self.entity_ids],
            "transaction_ids": [str(t) for t in self.transaction_ids],
            "evidence_ids": [str(e) for e in self.evidence_ids],
            "case_ids": [str(c) for c in self.case_ids],
            "source": self.source,
            "source_id": self.source_id,
            "metadata": self.metadata,
            "icon": self.icon,
            "color": self.color,
        }


@dataclass
class Timeline:
    """A timeline of events."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""

    # Scope
    case_id: Optional[UUID] = None
    entity_ids: list[UUID] = field(default_factory=list)

    # Events
    events: list[TimelineEvent] = field(default_factory=list)

    # Time range
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[UUID] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "case_id": str(self.case_id) if self.case_id else None,
            "entity_ids": [str(e) for e in self.entity_ids],
            "events": [e.to_dict() for e in self.events],
            "event_count": len(self.events),
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "created_at": self.created_at.isoformat(),
            "created_by": str(self.created_by) if self.created_by else None,
            "updated_at": self.updated_at.isoformat(),
        }

    def add_event(self, event: TimelineEvent) -> None:
        """Add an event to the timeline."""
        self.events.append(event)
        self.events.sort(key=lambda e: e.timestamp)
        self._update_date_range()
        self.updated_at = datetime.utcnow()

    def remove_event(self, event_id: UUID) -> bool:
        """Remove an event from the timeline."""
        for i, event in enumerate(self.events):
            if event.id == event_id:
                self.events.pop(i)
                self._update_date_range()
                self.updated_at = datetime.utcnow()
                return True
        return False

    def get_events_in_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[TimelineEvent]:
        """Get events within a time range."""
        return [
            e for e in self.events
            if start <= e.timestamp <= end
        ]

    def get_events_by_type(self, event_type: EventType) -> list[TimelineEvent]:
        """Get events of a specific type."""
        return [e for e in self.events if e.event_type == event_type]

    def get_events_for_entity(self, entity_id: UUID) -> list[TimelineEvent]:
        """Get events related to a specific entity."""
        return [e for e in self.events if entity_id in e.entity_ids]

    def _update_date_range(self) -> None:
        """Update start/end dates based on events."""
        if self.events:
            self.start_date = min(e.timestamp for e in self.events)
            self.end_date = max(e.timestamp for e in self.events)
        else:
            self.start_date = None
            self.end_date = None


class TimelineBuilder:
    """
    Builds timelines from various data sources.

    Aggregates events from transactions, alerts, case actions, etc.
    """

    # Event icons by type
    ICONS = {
        EventType.TRANSACTION: "💰",
        EventType.COMMUNICATION: "💬",
        EventType.DOCUMENT: "📄",
        EventType.ENTITY_CHANGE: "🏢",
        EventType.RELATIONSHIP: "🔗",
        EventType.ALERT: "⚠️",
        EventType.INVESTIGATION: "🔍",
        EventType.REGULATORY: "📋",
        EventType.EXTERNAL: "🌐",
        EventType.CUSTOM: "📌",
    }

    # Colors by severity
    COLORS = {
        EventSeverity.INFO: "#6c757d",
        EventSeverity.MINOR: "#17a2b8",
        EventSeverity.MODERATE: "#ffc107",
        EventSeverity.SIGNIFICANT: "#fd7e14",
        EventSeverity.CRITICAL: "#dc3545",
    }

    def __init__(self, case_id: Optional[UUID] = None):
        """
        Initialize a timeline builder.

        Args:
            case_id: Optional case ID to associate with the timeline
        """
        self._timelines: dict[UUID, Timeline] = {}
        self._case_id = case_id
        self._pending_events: list[TimelineEvent] = []

    def add_event(
        self,
        timestamp: datetime,
        description: str,
        event_type: str,
        entity_id: Optional[UUID] = None,
        metadata: Optional[dict] = None,
    ) -> TimelineEvent:
        """
        Add an event to the timeline being built.

        Args:
            timestamp: When the event occurred
            description: Event description
            event_type: Type of event (string)
            entity_id: Optional related entity
            metadata: Additional metadata

        Returns:
            Created TimelineEvent
        """
        # Map string to EventType
        try:
            etype = EventType(event_type)
        except ValueError:
            etype = EventType.CUSTOM

        event = TimelineEvent(
            event_type=etype,
            timestamp=timestamp,
            title=description,
            description=description,
            entity_ids=[entity_id] if entity_id else [],
            metadata=metadata or {},
            icon=self.ICONS.get(etype, "📌"),
            color=self.COLORS[EventSeverity.INFO],
        )

        self._pending_events.append(event)
        return event

    def build(self) -> Timeline:
        """
        Build the timeline from added events.

        Returns:
            Timeline with all added events
        """
        timeline = Timeline(
            case_id=self._case_id,
            name=f"Timeline for case {self._case_id}" if self._case_id else "Timeline",
        )

        # Add all pending events (they'll be sorted automatically)
        for event in self._pending_events:
            timeline.add_event(event)

        # Store it
        self._timelines[timeline.id] = timeline

        return timeline

    def create_timeline(
        self,
        name: str,
        case_id: Optional[UUID] = None,
        entity_ids: Optional[list[UUID]] = None,
        description: str = "",
        created_by: Optional[UUID] = None,
    ) -> Timeline:
        """
        Create a new timeline.

        Args:
            name: Timeline name
            case_id: Optional case this timeline is for
            entity_ids: Entities to include
            description: Description
            created_by: User creating the timeline

        Returns:
            Created Timeline
        """
        timeline = Timeline(
            name=name,
            description=description,
            case_id=case_id,
            entity_ids=entity_ids or [],
            created_by=created_by,
        )

        self._timelines[timeline.id] = timeline

        logger.info(f"Created timeline: {name}")

        return timeline

    def build_from_transactions(
        self,
        timeline: Timeline,
        transactions: list[dict],
    ) -> Timeline:
        """
        Add transaction events to timeline.

        Args:
            timeline: Timeline to add events to
            transactions: List of transaction dicts

        Returns:
            Updated Timeline
        """
        for txn in transactions:
            amount = txn.get("amount", 0)
            currency = txn.get("currency", "SEK")
            txn_type = txn.get("transaction_type", "transfer")

            # Determine severity based on amount
            if amount >= 1000000:
                severity = EventSeverity.SIGNIFICANT
            elif amount >= 100000:
                severity = EventSeverity.MODERATE
            elif amount >= 10000:
                severity = EventSeverity.MINOR
            else:
                severity = EventSeverity.INFO

            event = TimelineEvent(
                event_type=EventType.TRANSACTION,
                severity=severity,
                timestamp=txn.get("timestamp", datetime.utcnow()),
                title=f"{txn_type.title()}: {amount:,.0f} {currency}",
                description=txn.get("description", ""),
                transaction_ids=[UUID(str(txn["id"]))] if txn.get("id") else [],
                source="transaction_data",
                source_id=str(txn.get("id", "")),
                metadata={
                    "amount": amount,
                    "currency": currency,
                    "type": txn_type,
                    "from": txn.get("from_entity_name"),
                    "to": txn.get("to_entity_name"),
                },
                icon=self.ICONS[EventType.TRANSACTION],
                color=self.COLORS[severity],
            )

            # Add entity references
            for key in ["from_entity_id", "to_entity_id"]:
                if txn.get(key):
                    try:
                        event.entity_ids.append(UUID(str(txn[key])))
                    except ValueError:
                        pass

            timeline.add_event(event)

        return timeline

    def build_from_alerts(
        self,
        timeline: Timeline,
        alerts: list[dict],
    ) -> Timeline:
        """
        Add alert events to timeline.

        Args:
            timeline: Timeline to add events to
            alerts: List of alert dicts

        Returns:
            Updated Timeline
        """
        for alert in alerts:
            # Map alert severity
            alert_severity = alert.get("severity", "low")
            severity_map = {
                "critical": EventSeverity.CRITICAL,
                "high": EventSeverity.SIGNIFICANT,
                "medium": EventSeverity.MODERATE,
                "low": EventSeverity.MINOR,
            }
            severity = severity_map.get(alert_severity, EventSeverity.INFO)

            event = TimelineEvent(
                event_type=EventType.ALERT,
                severity=severity,
                timestamp=alert.get("created_at", datetime.utcnow()),
                title=alert.get("title", "Alert"),
                description=alert.get("description", ""),
                source="alert_system",
                source_id=str(alert.get("id", "")),
                metadata={
                    "alert_type": alert.get("alert_type"),
                    "pattern_type": alert.get("pattern_type"),
                    "confidence": alert.get("confidence"),
                },
                icon=self.ICONS[EventType.ALERT],
                color=self.COLORS[severity],
            )

            # Add entity references
            for entity in alert.get("entities", []):
                if entity.get("id"):
                    try:
                        event.entity_ids.append(UUID(str(entity["id"])))
                    except ValueError:
                        pass

            timeline.add_event(event)

        return timeline

    def build_from_case_actions(
        self,
        timeline: Timeline,
        case_notes: list[dict],
    ) -> Timeline:
        """
        Add case action events to timeline.

        Args:
            timeline: Timeline to add events to
            case_notes: List of case note dicts

        Returns:
            Updated Timeline
        """
        for note in case_notes:
            event = TimelineEvent(
                event_type=EventType.INVESTIGATION,
                severity=EventSeverity.INFO,
                timestamp=note.get("created_at", datetime.utcnow()),
                title="Investigation Action",
                description=note.get("content", ""),
                source="case_management",
                source_id=str(note.get("id", "")),
                metadata={
                    "author_id": str(note.get("author_id", "")),
                },
                icon=self.ICONS[EventType.INVESTIGATION],
                color=self.COLORS[EventSeverity.INFO],
            )

            timeline.add_event(event)

        return timeline

    def build_from_entity_changes(
        self,
        timeline: Timeline,
        changes: list[dict],
    ) -> Timeline:
        """
        Add entity change events to timeline.

        Args:
            timeline: Timeline to add events to
            changes: List of entity change dicts

        Returns:
            Updated Timeline
        """
        for change in changes:
            change_type = change.get("change_type", "update")

            # Determine severity
            significant_changes = [
                "ownership_change", "board_change", "address_change",
                "beneficial_owner_change", "status_change",
            ]
            if change_type in significant_changes:
                severity = EventSeverity.MODERATE
            else:
                severity = EventSeverity.MINOR

            event = TimelineEvent(
                event_type=EventType.ENTITY_CHANGE,
                severity=severity,
                timestamp=change.get("timestamp", datetime.utcnow()),
                title=change.get("title", f"Entity Change: {change_type}"),
                description=change.get("description", ""),
                source=change.get("source", "entity_monitoring"),
                metadata={
                    "change_type": change_type,
                    "old_value": change.get("old_value"),
                    "new_value": change.get("new_value"),
                },
                icon=self.ICONS[EventType.ENTITY_CHANGE],
                color=self.COLORS[severity],
            )

            if change.get("entity_id"):
                try:
                    event.entity_ids.append(UUID(str(change["entity_id"])))
                except ValueError:
                    pass

            timeline.add_event(event)

        return timeline

    def add_custom_event(
        self,
        timeline: Timeline,
        title: str,
        timestamp: datetime,
        description: str = "",
        severity: EventSeverity = EventSeverity.INFO,
        entity_ids: Optional[list[UUID]] = None,
        metadata: Optional[dict] = None,
    ) -> TimelineEvent:
        """
        Add a custom event to timeline.

        Args:
            timeline: Timeline to add event to
            title: Event title
            timestamp: When the event occurred
            description: Event description
            severity: Event severity
            entity_ids: Related entity IDs
            metadata: Additional metadata

        Returns:
            Created TimelineEvent
        """
        event = TimelineEvent(
            event_type=EventType.CUSTOM,
            severity=severity,
            timestamp=timestamp,
            title=title,
            description=description,
            entity_ids=entity_ids or [],
            source="manual_entry",
            metadata=metadata or {},
            icon=self.ICONS[EventType.CUSTOM],
            color=self.COLORS[severity],
        )

        timeline.add_event(event)

        return event

    def get_timeline(self, timeline_id: UUID) -> Optional[Timeline]:
        """Get a timeline by ID."""
        return self._timelines.get(timeline_id)

    def get_for_case(self, case_id: UUID) -> list[Timeline]:
        """Get all timelines for a case."""
        return [t for t in self._timelines.values() if t.case_id == case_id]

    def generate_summary(self, timeline: Timeline) -> dict[str, Any]:
        """
        Generate a summary of timeline events.

        Returns statistics and key events.
        """
        if not timeline.events:
            return {
                "event_count": 0,
                "date_range": None,
                "by_type": {},
                "by_severity": {},
                "key_events": [],
            }

        # Count by type
        by_type = {}
        for event in timeline.events:
            by_type[event.event_type.value] = by_type.get(event.event_type.value, 0) + 1

        # Count by severity
        by_severity = {}
        for event in timeline.events:
            by_severity[event.severity.value] = by_severity.get(event.severity.value, 0) + 1

        # Key events (significant or critical)
        key_events = [
            e for e in timeline.events
            if e.severity in [EventSeverity.SIGNIFICANT, EventSeverity.CRITICAL]
        ]

        return {
            "event_count": len(timeline.events),
            "date_range": {
                "start": timeline.start_date.isoformat() if timeline.start_date else None,
                "end": timeline.end_date.isoformat() if timeline.end_date else None,
            },
            "by_type": by_type,
            "by_severity": by_severity,
            "key_events": [e.to_dict() for e in key_events[:10]],
        }

    def detect_patterns(self, timeline: Timeline) -> list[dict]:
        """
        Detect patterns in timeline events.

        Looks for:
        - Clusters of activity
        - Unusual timing
        - Correlated events
        """
        patterns = []

        if len(timeline.events) < 3:
            return patterns

        # Detect activity clusters
        clusters = self._find_clusters(timeline.events)
        for cluster in clusters:
            patterns.append({
                "type": "activity_cluster",
                "description": f"High activity: {len(cluster)} events in short period",
                "event_count": len(cluster),
                "start": cluster[0].timestamp.isoformat(),
                "end": cluster[-1].timestamp.isoformat(),
                "event_ids": [str(e.id) for e in cluster],
            })

        # Detect unusual timing (weekend/night activity)
        unusual = [
            e for e in timeline.events
            if e.timestamp.weekday() >= 5 or e.timestamp.hour < 6 or e.timestamp.hour >= 22
        ]
        if len(unusual) >= 3:
            patterns.append({
                "type": "unusual_timing",
                "description": f"{len(unusual)} events during unusual hours/days",
                "event_count": len(unusual),
                "event_ids": [str(e.id) for e in unusual],
            })

        return patterns

    def _find_clusters(
        self,
        events: list[TimelineEvent],
        window_hours: int = 24,
        min_events: int = 5,
    ) -> list[list[TimelineEvent]]:
        """Find clusters of events within a time window."""
        clusters = []
        if not events:
            return clusters

        sorted_events = sorted(events, key=lambda e: e.timestamp)

        i = 0
        while i < len(sorted_events):
            window_end = sorted_events[i].timestamp + timedelta(hours=window_hours)
            cluster = [sorted_events[i]]

            j = i + 1
            while j < len(sorted_events) and sorted_events[j].timestamp <= window_end:
                cluster.append(sorted_events[j])
                j += 1

            if len(cluster) >= min_events:
                clusters.append(cluster)
                i = j  # Skip past this cluster
            else:
                i += 1

        return clusters
