"""
Fraud Sequence Detection (Playbooks).

Fraud has a playbook. The ORDER of events is a signature.
Detect fraud playbooks from event sequences.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from halo.graph.client import GraphClient


# Event types in company lifecycle
EVENT_TYPES = [
    "formed",
    "director_added",
    "director_removed",
    "owner_changed",
    "foreign_owner_added",
    "signatory_changed",
    "f_skatt_registered",
    "vat_registered",
    "employer_registered",
    "address_changed",
    "address_to_virtual",
    "capital_increased",
    "capital_decreased",
    "sni_changed",
    "arsredovisning_filed",
    "arsredovisning_late",
    "arsredovisning_missing",
    "debt_registered",
    "status_changed",
    "dissolved",
    "konkurs",
]


@dataclass
class Playbook:
    """Definition of a fraud playbook (sequence pattern)."""
    id: str
    name: str
    description: str
    sequence: list  # List of event types or (event, expected) tuples
    time_window_days: int
    severity: str
    typology: str


@dataclass
class PlaybookMatch:
    """Result of playbook detection."""
    playbook_id: str
    playbook_name: str
    severity: str
    confidence: float
    current_stage: int
    total_stages: int
    next_expected: Optional[str]
    matched_events: list[dict]
    entity_id: str
    alert: str
    detected_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "playbook_id": self.playbook_id,
            "playbook_name": self.playbook_name,
            "severity": self.severity,
            "confidence": self.confidence,
            "current_stage": self.current_stage,
            "total_stages": self.total_stages,
            "next_expected": self.next_expected,
            "matched_events": self.matched_events,
            "entity_id": self.entity_id,
            "alert": self.alert,
            "detected_at": self.detected_at.isoformat(),
        }


# Known fraud playbooks
PLAYBOOKS: dict[str, Playbook] = {
    "invoice_factory": Playbook(
        id="invoice_factory",
        name="Invoice Factory Setup",
        description="Company being set up to generate fake invoices for tax fraud",
        sequence=[
            "formed",
            "f_skatt_registered",
            ("vat_registered", False),  # Expected NOT to happen
            "address_to_virtual",
        ],
        time_window_days=90,
        severity="high",
        typology="tax_fraud"
    ),

    "phoenix": Playbook(
        id="phoenix",
        name="Phoenix Company",
        description="Directors abandon failing company and immediately start new one",
        sequence=[
            ("company_a", "director_removed"),
            ("company_b", "formed"),  # Same director
            ("company_a", "konkurs"),
        ],
        time_window_days=180,
        severity="high",
        typology="corporate_fraud"
    ),

    "ownership_layering": Playbook(
        id="ownership_layering",
        name="Ownership Layering",
        description="Ownership being obscured through multiple transfers",
        sequence=[
            "formed",
            "foreign_owner_added",
            "owner_changed",
            "owner_changed",  # Multiple transfers
        ],
        time_window_days=365,
        severity="medium",
        typology="money_laundering"
    ),

    "shelf_company_activation": Playbook(
        id="shelf_company_activation",
        name="Shelf Company Activation",
        description="Dormant company being activated for potential misuse",
        sequence=[
            "director_removed",
            "director_added",
            "address_changed",
            "sni_changed",
        ],
        time_window_days=60,
        severity="medium",
        typology="shell_company"
    ),

    "rapid_asset_stripping": Playbook(
        id="rapid_asset_stripping",
        name="Rapid Asset Stripping",
        description="Company being stripped before bankruptcy",
        sequence=[
            "owner_changed",
            "capital_decreased",
            "debt_registered",
            "dissolved",
        ],
        time_window_days=180,
        severity="high",
        typology="corporate_fraud"
    ),

    "nominee_takeover": Playbook(
        id="nominee_takeover",
        name="Nominee Takeover",
        description="Company control transferred to nominee director",
        sequence=[
            "director_removed",
            "director_added",  # Nominee
            "signatory_changed",
            "address_changed",
        ],
        time_window_days=30,
        severity="high",
        typology="shell_company"
    ),

    "pre_bankruptcy_fraud": Playbook(
        id="pre_bankruptcy_fraud",
        name="Pre-Bankruptcy Fraud",
        description="Signs of fraud before planned bankruptcy",
        sequence=[
            "arsredovisning_late",
            "director_removed",
            "address_changed",
            "arsredovisning_missing",
            "debt_registered",
        ],
        time_window_days=365,
        severity="critical",
        typology="corporate_fraud"
    ),
}


@dataclass
class Event:
    """A company lifecycle event."""
    event_type: str
    timestamp: datetime
    entity_id: str
    details: dict = field(default_factory=dict)


class FraudSequenceDetector:
    """
    Detect fraud playbooks from event sequences.

    Analyzes company event history to identify known fraud patterns.
    """

    def __init__(self, graph_client: Optional[GraphClient] = None):
        self.graph = graph_client
        self.playbooks = PLAYBOOKS

    async def detect_playbook(self, entity_id: str) -> list[PlaybookMatch]:
        """
        Check if entity's event sequence matches any fraud playbooks.
        """
        events = await self._get_event_sequence(entity_id)
        if not events:
            return []

        matches = []

        for playbook_id, playbook in self.playbooks.items():
            match_result = self._match_playbook(events, playbook, entity_id)
            if match_result:
                matches.append(match_result)

        return matches

    async def detect_playbook_batch(
        self,
        entity_ids: list[str]
    ) -> dict[str, list[PlaybookMatch]]:
        """
        Detect playbooks for multiple entities.
        """
        results = {}
        for entity_id in entity_ids:
            matches = await self.detect_playbook(entity_id)
            if matches:
                results[entity_id] = matches
        return results

    def _match_playbook(
        self,
        events: list[Event],
        playbook: Playbook,
        entity_id: str
    ) -> Optional[PlaybookMatch]:
        """
        Match events against a playbook sequence.
        """
        sequence = playbook.sequence
        window_days = playbook.time_window_days

        # Track which sequence steps have been matched
        matched_steps = []
        matched_events = []

        # Sort events by timestamp
        events = sorted(events, key=lambda e: e.timestamp)

        if not events:
            return None

        # Check time window
        first_event = events[0].timestamp
        last_event = events[-1].timestamp

        for step_idx, step in enumerate(sequence):
            # Handle (event, expected) tuples
            if isinstance(step, tuple):
                event_type, expected = step
                # For negative matches (expected=False), check it didn't happen
                if not expected:
                    if not any(e.event_type == event_type for e in events):
                        matched_steps.append(step_idx)
                    continue
            else:
                event_type = step

            # Find matching event
            for event in events:
                if event.event_type == event_type:
                    # Check if within time window of first matched event
                    if matched_events:
                        days_diff = (event.timestamp - matched_events[0].timestamp).days
                        if days_diff > window_days:
                            continue

                    matched_steps.append(step_idx)
                    matched_events.append(event)
                    break

        # Calculate match score
        total_steps = len(sequence)
        matched_count = len(matched_steps)

        if matched_count == 0:
            return None

        confidence = matched_count / total_steps

        # Only report if significant match (> 50% of steps)
        if confidence < 0.5:
            return None

        # Determine current stage and next expected
        current_stage = max(matched_steps) + 1 if matched_steps else 0
        next_expected = None
        if current_stage < total_steps:
            next_step = sequence[current_stage]
            if isinstance(next_step, tuple):
                next_expected = next_step[0]
            else:
                next_expected = next_step

        alert = f"Company following {playbook.name} playbook (stage {current_stage}/{total_steps})"

        return PlaybookMatch(
            playbook_id=playbook.id,
            playbook_name=playbook.name,
            severity=playbook.severity,
            confidence=confidence,
            current_stage=current_stage,
            total_stages=total_steps,
            next_expected=next_expected,
            matched_events=[
                {"type": e.event_type, "timestamp": e.timestamp.isoformat(), "details": e.details}
                for e in matched_events
            ],
            entity_id=entity_id,
            alert=alert
        )

    async def predict_next_events(
        self,
        entity_id: str,
        playbook_match: PlaybookMatch
    ) -> list[str]:
        """
        Predict likely next events based on playbook match.
        """
        playbook = self.playbooks.get(playbook_match.playbook_id)
        if not playbook:
            return []

        predictions = []
        current = playbook_match.current_stage

        # Get remaining steps in playbook
        for step in playbook.sequence[current:]:
            if isinstance(step, tuple):
                event_type, expected = step
                if expected:
                    predictions.append(event_type)
            else:
                predictions.append(step)

        return predictions

    async def find_entities_matching_playbook(
        self,
        playbook_id: str,
        min_confidence: float = 0.5
    ) -> list[PlaybookMatch]:
        """
        Find all entities matching a specific playbook.
        """
        if playbook_id not in self.playbooks:
            return []

        matches = []

        # Get entities with recent events
        entity_ids = await self._get_active_entities()

        for entity_id in entity_ids:
            entity_matches = await self.detect_playbook(entity_id)
            for match in entity_matches:
                if match.playbook_id == playbook_id and match.confidence >= min_confidence:
                    matches.append(match)

        return matches

    async def _get_event_sequence(self, entity_id: str) -> list[Event]:
        """
        Get event sequence for an entity from the graph/database.
        """
        events = []

        if self.graph:
            # Query for company events/changes
            company = await self.graph.get_company(entity_id)
            if not company:
                return []

            # Formation event
            formation = company.get("formation", {})
            formation_date = formation.get("date")
            if formation_date:
                try:
                    if isinstance(formation_date, str):
                        from datetime import date
                        formation_date = date.fromisoformat(formation_date)
                    events.append(Event(
                        event_type="formed",
                        timestamp=datetime.combine(formation_date, datetime.min.time()),
                        entity_id=entity_id,
                        details=formation
                    ))
                except (ValueError, TypeError):
                    pass

            # F-skatt event
            f_skatt = company.get("f_skatt", {})
            if f_skatt.get("registered"):
                f_skatt_from = f_skatt.get("from")
                if f_skatt_from:
                    try:
                        if isinstance(f_skatt_from, str):
                            from datetime import date
                            f_skatt_from = date.fromisoformat(f_skatt_from)
                        events.append(Event(
                            event_type="f_skatt_registered",
                            timestamp=datetime.combine(f_skatt_from, datetime.min.time()),
                            entity_id=entity_id,
                            details=f_skatt
                        ))
                    except (ValueError, TypeError):
                        pass

            # VAT event
            vat = company.get("vat", {})
            if vat.get("registered"):
                vat_from = vat.get("from")
                if vat_from:
                    try:
                        if isinstance(vat_from, str):
                            from datetime import date
                            vat_from = date.fromisoformat(vat_from)
                        events.append(Event(
                            event_type="vat_registered",
                            timestamp=datetime.combine(vat_from, datetime.min.time()),
                            entity_id=entity_id,
                            details=vat
                        ))
                    except (ValueError, TypeError):
                        pass

            # Status changes from history
            for status_change in company.get("status_history", []):
                status_code = status_change.get("status", "")
                status_from = status_change.get("from")
                if status_from:
                    try:
                        if isinstance(status_from, str):
                            from datetime import date
                            status_from = date.fromisoformat(status_from)

                        event_type = "status_changed"
                        if status_code.lower() in ("konkurs", "bankrupt"):
                            event_type = "konkurs"
                        elif status_code.lower() in ("dissolved", "avregistrerad"):
                            event_type = "dissolved"

                        events.append(Event(
                            event_type=event_type,
                            timestamp=datetime.combine(status_from, datetime.min.time()),
                            entity_id=entity_id,
                            details=status_change
                        ))
                    except (ValueError, TypeError):
                        pass

            # Address changes
            addresses = company.get("addresses", [])
            for addr in addresses:
                addr_from = addr.get("from")
                if addr_from:
                    try:
                        if isinstance(addr_from, str):
                            from datetime import date
                            addr_from = date.fromisoformat(addr_from)

                        event_type = "address_changed"
                        if addr.get("type") == "virtual":
                            event_type = "address_to_virtual"

                        events.append(Event(
                            event_type=event_type,
                            timestamp=datetime.combine(addr_from, datetime.min.time()),
                            entity_id=entity_id,
                            details=addr
                        ))
                    except (ValueError, TypeError):
                        pass

        return sorted(events, key=lambda e: e.timestamp)

    async def _get_active_entities(self) -> list[str]:
        """Get list of active entity IDs to check."""
        if self.graph:
            try:
                query = """
                MATCH (c:Company)
                WHERE c.status.code IN ['active', 'aktiv']
                RETURN c.id as id
                LIMIT 1000
                """
                results = await self.graph.execute_cypher(query)
                return [r.get("id") for r in results if r.get("id")]
            except Exception:
                pass
        return []

    def add_playbook(self, playbook: Playbook) -> None:
        """Add a custom playbook."""
        self.playbooks[playbook.id] = playbook

    def get_playbook(self, playbook_id: str) -> Optional[Playbook]:
        """Get a playbook by ID."""
        return self.playbooks.get(playbook_id)
