"""
Case management for investigations.

Handles the lifecycle of investigation cases from creation to closure.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class CaseStatus(str, Enum):
    """Status of an investigation case."""

    DRAFT = "draft"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    ESCALATED = "escalated"
    ON_HOLD = "on_hold"
    CLOSED = "closed"  # Generic closed status
    CLOSED_CONFIRMED = "closed_confirmed"  # Suspicion confirmed
    CLOSED_CLEARED = "closed_cleared"  # Entity cleared
    CLOSED_INCONCLUSIVE = "closed_inconclusive"
    ARCHIVED = "archived"


class CasePriority(str, Enum):
    """Priority levels for cases."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CaseType(str, Enum):
    """Types of investigation cases."""

    AML = "aml"  # Anti-money laundering
    FRAUD = "fraud"
    SANCTIONS = "sanctions"
    PEP = "pep"  # Politically exposed persons
    CTF = "ctf"  # Counter-terrorist financing
    TAX_EVASION = "tax_evasion"
    INSIDER = "insider"
    MARKET_ABUSE = "market_abuse"
    OTHER = "other"


@dataclass
class CaseNote:
    """A note or comment on a case."""

    id: UUID = field(default_factory=uuid4)
    content: str = ""
    author_id: UUID = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_internal: bool = True  # vs. shareable with regulators

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "content": self.content,
            "author_id": str(self.author_id) if self.author_id else None,
            "created_at": self.created_at.isoformat(),
            "is_internal": self.is_internal,
        }


@dataclass
class CaseSubject:
    """Subject (person or company) of an investigation."""

    entity_id: UUID
    entity_type: str  # "person" or "company"
    name: str
    identifier: str  # personnummer or organisationsnummer
    role: str = "primary"  # primary, secondary, witness, counterparty

    # Risk assessment at time of case creation
    risk_level: Optional[str] = None
    risk_score: Optional[float] = None

    # Additional context
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": str(self.entity_id),
            "entity_type": self.entity_type,
            "name": self.name,
            "identifier": self.identifier,
            "role": self.role,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "notes": self.notes,
        }


@dataclass
class Case:
    """An investigation case."""

    id: UUID = field(default_factory=uuid4)
    case_number: str = ""  # Human-readable case number
    title: str = ""
    description: str = ""

    case_type: CaseType = CaseType.OTHER
    status: CaseStatus = CaseStatus.OPEN  # Default to OPEN
    priority: CasePriority = CasePriority.MEDIUM

    # Subjects
    subjects: list[CaseSubject] = field(default_factory=list)

    # Linked entity IDs (convenience accessor)
    entity_ids: list[UUID] = field(default_factory=list)

    # Related items
    alert_ids: list[UUID] = field(default_factory=list)
    sar_ids: list[UUID] = field(default_factory=list)
    evidence_ids: list[UUID] = field(default_factory=list)
    related_case_ids: list[UUID] = field(default_factory=list)

    # Assignment
    assigned_to: Optional[UUID] = None
    team_id: Optional[UUID] = None

    # Notes and findings
    notes: list[CaseNote] = field(default_factory=list)
    findings: str = ""
    recommendations: str = ""
    outcome: Optional[str] = None  # Outcome when closed

    # Regulatory
    sar_required: bool = False
    sar_filed: bool = False
    regulator_notified: bool = False

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[UUID] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None

    # Audit
    last_activity_at: datetime = field(default_factory=datetime.utcnow)
    activity_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "case_number": self.case_number,
            "title": self.title,
            "description": self.description,
            "case_type": self.case_type.value,
            "status": self.status.value,
            "priority": self.priority.value,
            "subjects": [s.to_dict() for s in self.subjects],
            "entity_ids": [str(e) for e in self.entity_ids],
            "alert_ids": [str(a) for a in self.alert_ids],
            "sar_ids": [str(s) for s in self.sar_ids],
            "evidence_ids": [str(e) for e in self.evidence_ids],
            "related_case_ids": [str(c) for c in self.related_case_ids],
            "assigned_to": str(self.assigned_to) if self.assigned_to else None,
            "team_id": str(self.team_id) if self.team_id else None,
            "notes": [n.to_dict() for n in self.notes],
            "findings": self.findings,
            "recommendations": self.recommendations,
            "outcome": self.outcome,
            "sar_required": self.sar_required,
            "sar_filed": self.sar_filed,
            "regulator_notified": self.regulator_notified,
            "created_at": self.created_at.isoformat(),
            "created_by": str(self.created_by) if self.created_by else None,
            "updated_at": self.updated_at.isoformat(),
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "last_activity_at": self.last_activity_at.isoformat(),
            "activity_count": self.activity_count,
        }


class CaseManager:
    """
    Manages investigation cases.

    In production, this would integrate with a database.
    This implementation provides the interface.
    """

    # Case number prefix by type
    CASE_PREFIXES = {
        CaseType.AML: "AML",
        CaseType.FRAUD: "FRD",
        CaseType.SANCTIONS: "SAN",
        CaseType.PEP: "PEP",
        CaseType.CTF: "CTF",
        CaseType.TAX_EVASION: "TAX",
        CaseType.INSIDER: "INS",
        CaseType.MARKET_ABUSE: "MKT",
        CaseType.OTHER: "OTH",
    }

    def __init__(self):
        # In-memory storage for demo
        self._cases: dict[UUID, Case] = {}
        self._case_counter: dict[str, int] = {p: 0 for p in self.CASE_PREFIXES.values()}

    def create_case(
        self,
        title: str,
        case_type: CaseType,
        subjects: Optional[list[CaseSubject]] = None,
        description: str = "",
        priority: CasePriority = CasePriority.MEDIUM,
        alert_ids: Optional[list[UUID]] = None,
        created_by: Optional[UUID] = None,
    ) -> Case:
        """
        Create a new investigation case.

        Args:
            title: Case title
            case_type: Type of case
            subjects: List of case subjects (optional)
            description: Detailed description
            priority: Case priority
            alert_ids: Related alert IDs that triggered the case
            created_by: User who created the case

        Returns:
            Created Case object
        """
        case = Case(
            title=title,
            case_type=case_type,
            description=description,
            priority=priority,
            subjects=subjects or [],
            alert_ids=alert_ids or [],
            created_by=created_by,
        )

        # Generate case number
        case.case_number = self._generate_case_number(case_type)

        self._cases[case.id] = case

        logger.info(f"Created case {case.case_number}: {title}")

        return case

    def link_entity(
        self,
        case_id: UUID,
        entity_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Case:
        """Link an entity to a case."""
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case not found: {case_id}")

        if entity_id not in case.entity_ids:
            case.entity_ids.append(entity_id)
            case.updated_at = datetime.utcnow()
            case.last_activity_at = datetime.utcnow()
            case.activity_count += 1

            case.notes.append(CaseNote(
                content=f"Entity {entity_id} linked to case",
                author_id=user_id,
            ))

        return case

    def link_alert(
        self,
        case_id: UUID,
        alert_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Case:
        """Link an alert to a case."""
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case not found: {case_id}")

        if alert_id not in case.alert_ids:
            case.alert_ids.append(alert_id)
            case.updated_at = datetime.utcnow()
            case.last_activity_at = datetime.utcnow()
            case.activity_count += 1

            case.notes.append(CaseNote(
                content=f"Alert {alert_id} linked to case",
                author_id=user_id,
            ))

        return case

    def create_from_alerts(
        self,
        alert_ids: list[UUID],
        alerts_data: list[dict],
        created_by: Optional[UUID] = None,
    ) -> Case:
        """
        Create a case from one or more alerts.

        Args:
            alert_ids: Alert IDs to include
            alerts_data: Alert data dicts
            created_by: User creating the case

        Returns:
            Created Case
        """
        if not alerts_data:
            raise ValueError("At least one alert required")

        # Determine case type from alerts
        case_type = self._infer_case_type(alerts_data)

        # Extract subjects from alerts
        subjects = []
        seen_entities = set()
        for alert in alerts_data:
            for entity in alert.get("entities", []):
                entity_id = entity.get("id")
                if entity_id and entity_id not in seen_entities:
                    subjects.append(CaseSubject(
                        entity_id=UUID(str(entity_id)),
                        entity_type=entity.get("entity_type", "unknown"),
                        name=entity.get("name", "Unknown"),
                        identifier=entity.get("identifier", ""),
                        risk_level=entity.get("risk_level"),
                        risk_score=entity.get("risk_score"),
                    ))
                    seen_entities.add(entity_id)

        # Determine priority
        severities = [a.get("severity", "low") for a in alerts_data]
        if "critical" in severities:
            priority = CasePriority.CRITICAL
        elif "high" in severities:
            priority = CasePriority.HIGH
        elif "medium" in severities:
            priority = CasePriority.MEDIUM
        else:
            priority = CasePriority.LOW

        # Generate title
        title = self._generate_title(case_type, subjects, alerts_data)

        # Generate description
        description = self._generate_description(alerts_data)

        return self.create_case(
            title=title,
            case_type=case_type,
            subjects=subjects,
            description=description,
            priority=priority,
            alert_ids=alert_ids,
            created_by=created_by,
        )

    def get_case(self, case_id: UUID) -> Optional[Case]:
        """Get a case by ID."""
        return self._cases.get(case_id)

    def get_by_number(self, case_number: str) -> Optional[Case]:
        """Get a case by case number."""
        for case in self._cases.values():
            if case.case_number == case_number:
                return case
        return None

    def update_status(
        self,
        case_id: UUID,
        new_status: CaseStatus,
        user_id: Optional[UUID] = None,
        note: Optional[str] = None,
    ) -> Case:
        """
        Update case status.

        Args:
            case_id: Case to update
            new_status: New status
            user_id: User making the change
            note: Optional note about the change

        Returns:
            Updated Case
        """
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case not found: {case_id}")

        old_status = case.status
        case.status = new_status
        case.updated_at = datetime.utcnow()
        case.last_activity_at = datetime.utcnow()
        case.activity_count += 1

        # Set timestamps based on status
        if new_status == CaseStatus.OPEN and not case.opened_at:
            case.opened_at = datetime.utcnow()
        elif new_status in [
            CaseStatus.CLOSED_CONFIRMED,
            CaseStatus.CLOSED_CLEARED,
            CaseStatus.CLOSED_INCONCLUSIVE,
        ]:
            case.closed_at = datetime.utcnow()

        # Add note
        if note:
            case.notes.append(CaseNote(
                content=f"Status changed from {old_status.value} to {new_status.value}: {note}",
                author_id=user_id,
            ))

        logger.info(f"Case {case.case_number} status: {old_status.value} -> {new_status.value}")

        return case

    def assign_case(
        self,
        case_id: UUID,
        assigned_to: UUID,
        assigned_by: Optional[UUID] = None,
    ) -> Case:
        """Assign a case to a user."""
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case not found: {case_id}")

        case.assigned_to = assigned_to
        case.updated_at = datetime.utcnow()
        case.last_activity_at = datetime.utcnow()
        case.activity_count += 1

        case.notes.append(CaseNote(
            content=f"Case assigned to {assigned_to}",
            author_id=assigned_by,
        ))

        # Auto-open if still in draft
        if case.status == CaseStatus.DRAFT:
            case.status = CaseStatus.OPEN
            case.opened_at = datetime.utcnow()

        logger.info(f"Case {case.case_number} assigned to {assigned_to}")

        return case

    def add_note(
        self,
        case_id: UUID,
        content: str,
        author_id: Optional[UUID] = None,
        is_internal: bool = True,
    ) -> CaseNote:
        """Add a note to a case."""
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case not found: {case_id}")

        note = CaseNote(
            content=content,
            author_id=author_id,
            is_internal=is_internal,
        )
        case.notes.append(note)
        case.updated_at = datetime.utcnow()
        case.last_activity_at = datetime.utcnow()
        case.activity_count += 1

        return note

    def add_evidence(
        self,
        case_id: UUID,
        evidence_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Case:
        """Link evidence to a case."""
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case not found: {case_id}")

        if evidence_id not in case.evidence_ids:
            case.evidence_ids.append(evidence_id)
            case.updated_at = datetime.utcnow()
            case.last_activity_at = datetime.utcnow()
            case.activity_count += 1

            case.notes.append(CaseNote(
                content=f"Evidence {evidence_id} linked to case",
                author_id=user_id,
            ))

        return case

    def link_sar(
        self,
        case_id: UUID,
        sar_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Case:
        """Link a SAR to a case."""
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case not found: {case_id}")

        if sar_id not in case.sar_ids:
            case.sar_ids.append(sar_id)
            case.sar_required = True
            case.updated_at = datetime.utcnow()
            case.last_activity_at = datetime.utcnow()
            case.activity_count += 1

            case.notes.append(CaseNote(
                content=f"SAR {sar_id} linked to case",
                author_id=user_id,
            ))

        return case

    def close_case(
        self,
        case_id: UUID,
        outcome: str,
        findings: str,
        recommendations: str = "",
        user_id: Optional[UUID] = None,
    ) -> Case:
        """
        Close a case with findings.

        Args:
            case_id: Case to close
            outcome: Outcome string (e.g., 'confirmed', 'cleared', 'inconclusive')
            findings: Summary of findings
            recommendations: Recommendations for future action
            user_id: User closing the case

        Returns:
            Closed Case
        """
        case = self._cases.get(case_id)
        if not case:
            raise ValueError(f"Case not found: {case_id}")

        case.status = CaseStatus.CLOSED
        case.outcome = outcome
        case.findings = findings
        case.recommendations = recommendations
        case.closed_at = datetime.utcnow()
        case.updated_at = datetime.utcnow()
        case.last_activity_at = datetime.utcnow()
        case.activity_count += 1

        case.notes.append(CaseNote(
            content=f"Case closed with outcome: {outcome}",
            author_id=user_id,
        ))

        logger.info(f"Case {case.case_number} closed: {outcome}")

        return case

    def search_cases(
        self,
        status: Optional[CaseStatus] = None,
        case_type: Optional[CaseType] = None,
        priority: Optional[CasePriority] = None,
        assigned_to: Optional[UUID] = None,
        subject_id: Optional[UUID] = None,
    ) -> list[Case]:
        """Search cases with filters."""
        results = []

        for case in self._cases.values():
            if status and case.status != status:
                continue
            if case_type and case.case_type != case_type:
                continue
            if priority and case.priority != priority:
                continue
            if assigned_to and case.assigned_to != assigned_to:
                continue
            if subject_id:
                subject_ids = [s.entity_id for s in case.subjects]
                if subject_id not in subject_ids:
                    continue

            results.append(case)

        # Sort by priority and created date
        priority_order = {
            CasePriority.CRITICAL: 0,
            CasePriority.HIGH: 1,
            CasePriority.MEDIUM: 2,
            CasePriority.LOW: 3,
        }
        results.sort(key=lambda c: (priority_order[c.priority], c.created_at))

        return results

    def get_statistics(self) -> dict[str, Any]:
        """Get case statistics."""
        total = len(self._cases)

        by_status = {}
        by_type = {}
        by_priority = {}

        for case in self._cases.values():
            by_status[case.status.value] = by_status.get(case.status.value, 0) + 1
            by_type[case.case_type.value] = by_type.get(case.case_type.value, 0) + 1
            by_priority[case.priority.value] = by_priority.get(case.priority.value, 0) + 1

        open_cases = [
            c for c in self._cases.values()
            if c.status not in [
                CaseStatus.CLOSED_CONFIRMED,
                CaseStatus.CLOSED_CLEARED,
                CaseStatus.CLOSED_INCONCLUSIVE,
                CaseStatus.ARCHIVED,
            ]
        ]

        return {
            "total": total,
            "open": len(open_cases),
            "by_status": by_status,
            "by_type": by_type,
            "by_priority": by_priority,
        }

    def _generate_case_number(self, case_type: CaseType) -> str:
        """Generate a unique case number."""
        # Use the case type name for the prefix (e.g., AML, SANCTIONS, FRAUD)
        prefix = case_type.name.upper()
        if prefix not in self._case_counter:
            self._case_counter[prefix] = 0
        self._case_counter[prefix] += 1
        year = datetime.utcnow().year
        seq = self._case_counter[prefix]
        return f"{prefix}-{year}-{seq:05d}"

    def _infer_case_type(self, alerts_data: list[dict]) -> CaseType:
        """Infer case type from alerts."""
        patterns = set()
        for alert in alerts_data:
            patterns.add(alert.get("pattern_type", ""))
            patterns.add(alert.get("alert_type", ""))

        # Map patterns to case types
        if "sanctions" in patterns or "sanctioned" in patterns:
            return CaseType.SANCTIONS
        if "pep" in patterns:
            return CaseType.PEP
        if "terrorism" in patterns or "ctf" in patterns:
            return CaseType.CTF
        if any(p in patterns for p in ["structuring", "layering", "smurfing", "round_trip"]):
            return CaseType.AML
        if "fraud" in patterns:
            return CaseType.FRAUD

        return CaseType.AML  # Default

    def _generate_title(
        self,
        case_type: CaseType,
        subjects: list[CaseSubject],
        alerts_data: list[dict],
    ) -> str:
        """Generate case title."""
        type_name = case_type.name.replace("_", " ").title()

        if subjects:
            primary = next((s for s in subjects if s.role == "primary"), subjects[0])
            return f"{type_name} Investigation - {primary.name}"

        return f"{type_name} Investigation - {len(alerts_data)} Alert(s)"

    def _generate_description(self, alerts_data: list[dict]) -> str:
        """Generate case description from alerts."""
        lines = [
            "Case created from the following alerts:",
            "",
        ]

        for alert in alerts_data:
            lines.append(f"• {alert.get('title', 'Alert')}")
            if alert.get("description"):
                lines.append(f"  {alert.get('description')}")

        return "\n".join(lines)
