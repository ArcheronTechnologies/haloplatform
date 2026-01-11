"""
SAR (Suspicious Activity Report) generator.

Generates reports for Swedish Finanspolisen (Financial Police)
in compliance with Swedish AML regulations (Penningtvättslagen).

SAR types:
- STR: Suspicious Transaction Report
- CTR: Currency Transaction Report (cash over threshold)
- SAR: General Suspicious Activity Report
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class SARType(str, Enum):
    """Types of suspicious activity reports."""

    STR = "str"  # Suspicious Transaction Report
    CTR = "ctr"  # Currency Transaction Report
    SAR = "sar"  # General Suspicious Activity Report
    TFAR = "tfar"  # Terrorist Financing Activity Report


class SARStatus(str, Enum):
    """Status of a SAR in the workflow."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"


class SARPriority(str, Enum):
    """Priority levels for SAR submission."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class SARSubject:
    """Subject of a SAR (person or company)."""

    entity_id: UUID
    entity_type: str  # "person" or "company"
    name: str
    identifier: str  # personnummer or organisationsnummer

    # Additional details
    address: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[str] = None
    occupation: Optional[str] = None

    # Relationship to activity
    role: str = "subject"  # subject, counterparty, beneficiary

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": str(self.entity_id),
            "entity_type": self.entity_type,
            "name": self.name,
            "identifier": self.identifier,
            "address": self.address,
            "nationality": self.nationality,
            "date_of_birth": self.date_of_birth,
            "occupation": self.occupation,
            "role": self.role,
        }


@dataclass
class SARTransaction:
    """Transaction included in a SAR."""

    transaction_id: UUID
    amount: Decimal
    currency: str
    timestamp: datetime
    transaction_type: str

    from_entity: Optional[str] = None
    to_entity: Optional[str] = None
    description: Optional[str] = None

    # Why this transaction is suspicious
    suspicion_indicators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": str(self.transaction_id),
            "amount": str(self.amount),
            "currency": self.currency,
            "timestamp": self.timestamp.isoformat(),
            "transaction_type": self.transaction_type,
            "from_entity": self.from_entity,
            "to_entity": self.to_entity,
            "description": self.description,
            "suspicion_indicators": self.suspicion_indicators,
        }


@dataclass
class SARReport:
    """
    Suspicious Activity Report.

    Swedish format aligned with Finanspolisen requirements.
    """

    id: UUID = field(default_factory=uuid4)
    sar_type: SARType = SARType.SAR
    status: SARStatus = SARStatus.DRAFT
    priority: SARPriority = SARPriority.MEDIUM

    # Subjects
    subjects: list[SARSubject] = field(default_factory=list)

    # Transactions
    transactions: list[SARTransaction] = field(default_factory=list)

    # Narrative
    summary: str = ""
    detailed_narrative: str = ""
    suspicion_grounds: list[str] = field(default_factory=list)

    # Pattern matches that triggered this SAR
    pattern_matches: list[dict] = field(default_factory=list)

    # Amounts
    total_amount: Optional[Decimal] = None
    currency: str = "SEK"

    # Timeframe
    activity_start: Optional[datetime] = None
    activity_end: Optional[datetime] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[UUID] = None
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None

    # External reference (from Finanspolisen)
    external_reference: Optional[str] = None

    # Related case
    case_id: Optional[UUID] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "sar_type": self.sar_type.value,
            "status": self.status.value,
            "priority": self.priority.value,
            "subjects": [s.to_dict() for s in self.subjects],
            "transactions": [t.to_dict() for t in self.transactions],
            "summary": self.summary,
            "detailed_narrative": self.detailed_narrative,
            "suspicion_grounds": self.suspicion_grounds,
            "pattern_matches": self.pattern_matches,
            "total_amount": str(self.total_amount) if self.total_amount else None,
            "currency": self.currency,
            "activity_start": self.activity_start.isoformat() if self.activity_start else None,
            "activity_end": self.activity_end.isoformat() if self.activity_end else None,
            "created_at": self.created_at.isoformat(),
            "created_by": str(self.created_by) if self.created_by else None,
            "reviewed_by": str(self.reviewed_by) if self.reviewed_by else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "external_reference": self.external_reference,
            "case_id": str(self.case_id) if self.case_id else None,
        }

    def to_finanspolisen_xml(self) -> str:
        """
        Generate XML format for Finanspolisen submission.

        Note: This is a simplified template. Actual format
        should be validated against Finanspolisen specifications.
        """
        subjects_xml = "\n".join(
            f"""    <Subject>
      <EntityType>{s.entity_type}</EntityType>
      <Name>{s.name}</Name>
      <Identifier>{s.identifier}</Identifier>
      <Role>{s.role}</Role>
    </Subject>"""
            for s in self.subjects
        )

        transactions_xml = "\n".join(
            f"""    <Transaction>
      <TransactionId>{t.transaction_id}</TransactionId>
      <Amount currency="{t.currency}">{t.amount}</Amount>
      <Timestamp>{t.timestamp.isoformat()}</Timestamp>
      <Type>{t.transaction_type}</Type>
    </Transaction>"""
            for t in self.transactions
        )

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<SuspiciousActivityReport xmlns="urn:finanspolisen:sar:v1">
  <Header>
    <ReportId>{self.id}</ReportId>
    <ReportType>{self.sar_type.value.upper()}</ReportType>
    <Priority>{self.priority.value}</Priority>
    <CreatedAt>{self.created_at.isoformat()}</CreatedAt>
  </Header>

  <Subjects>
{subjects_xml}
  </Subjects>

  <Transactions>
{transactions_xml}
  </Transactions>

  <Narrative>
    <Summary>{self.summary}</Summary>
    <DetailedNarrative><![CDATA[{self.detailed_narrative}]]></DetailedNarrative>
  </Narrative>

  <SuspicionGrounds>
    {"".join(f"<Ground>{g}</Ground>" for g in self.suspicion_grounds)}
  </SuspicionGrounds>

  <TotalAmount currency="{self.currency}">{self.total_amount or 0}</TotalAmount>
  <ActivityPeriod>
    <Start>{self.activity_start.isoformat() if self.activity_start else ""}</Start>
    <End>{self.activity_end.isoformat() if self.activity_end else ""}</End>
  </ActivityPeriod>
</SuspiciousActivityReport>"""


class SARGenerator:
    """
    Generates SAR reports from pattern matches and entity data.

    Usage:
        generator = SARGenerator()
        sar = generator.create_from_patterns(pattern_matches, entity_data)
    """

    # Suspicion ground templates
    SUSPICION_TEMPLATES = {
        "structuring": "Transactions appear structured to avoid reporting thresholds",
        "layering": "Complex transaction chain designed to obscure fund origin",
        "rapid_movement": "Funds moved unusually quickly with no apparent business purpose",
        "round_trip": "Funds returned to origin through intermediaries",
        "smurfing": "Multiple depositors aggregating funds to single recipient",
        "high_risk_country": "Transactions involving high-risk jurisdiction",
        "pep_involvement": "Politically exposed person involvement",
        "unusual_pattern": "Transaction pattern inconsistent with stated business",
        "cash_intensive": "Unusual cash transaction volume",
        "shell_company": "Entity exhibits shell company characteristics",
    }

    def __init__(self):
        pass

    def create_from_patterns(
        self,
        pattern_matches: list[dict],
        entities: dict[UUID, dict],
        transactions: Optional[list[dict]] = None,
        case_id: Optional[UUID] = None,
        created_by: Optional[UUID] = None,
    ) -> SARReport:
        """
        Create SAR from pattern match results.

        Args:
            pattern_matches: List of PatternMatch.to_dict() results
            entities: Dict mapping entity_id to entity data
            transactions: Optional list of transaction dicts
            case_id: Optional related case ID
            created_by: Optional user ID who triggered creation

        Returns:
            SARReport ready for review
        """
        sar = SARReport(
            case_id=case_id,
            created_by=created_by,
        )

        # Collect all entity IDs and transaction IDs from patterns
        entity_ids: set[UUID] = set()
        transaction_ids: set[UUID] = set()
        total_amount = Decimal("0")

        for match in pattern_matches:
            for eid in match.get("entity_ids", []):
                try:
                    entity_ids.add(UUID(eid) if isinstance(eid, str) else eid)
                except ValueError:
                    pass

            for tid in match.get("transaction_ids", []):
                try:
                    transaction_ids.add(UUID(tid) if isinstance(tid, str) else tid)
                except ValueError:
                    pass

            if match.get("total_amount"):
                try:
                    total_amount += Decimal(str(match["total_amount"]))
                except Exception:
                    pass

            # Add suspicion grounds
            pattern_type = match.get("pattern_type", "")
            if pattern_type in self.SUSPICION_TEMPLATES:
                ground = self.SUSPICION_TEMPLATES[pattern_type]
                if ground not in sar.suspicion_grounds:
                    sar.suspicion_grounds.append(ground)

            # Store pattern match
            sar.pattern_matches.append(match)

        # Add subjects
        for eid in entity_ids:
            entity_data = entities.get(eid, {})
            if entity_data:
                sar.subjects.append(SARSubject(
                    entity_id=eid,
                    entity_type=entity_data.get("entity_type", "unknown"),
                    name=entity_data.get("name", "Unknown"),
                    identifier=entity_data.get("identifier", ""),
                    address=entity_data.get("address"),
                    nationality=entity_data.get("nationality"),
                ))

        # Add transactions if provided
        if transactions:
            for txn in transactions:
                txn_id = txn.get("id")
                if txn_id and (UUID(str(txn_id)) if isinstance(txn_id, str) else txn_id) in transaction_ids:
                    sar.transactions.append(SARTransaction(
                        transaction_id=UUID(str(txn_id)) if isinstance(txn_id, str) else txn_id,
                        amount=Decimal(str(txn.get("amount", 0))),
                        currency=txn.get("currency", "SEK"),
                        timestamp=txn.get("timestamp", datetime.utcnow()),
                        transaction_type=txn.get("transaction_type", "unknown"),
                        from_entity=txn.get("from_entity_name"),
                        to_entity=txn.get("to_entity_name"),
                    ))

        # Set amounts and timeframe
        sar.total_amount = total_amount

        if sar.transactions:
            timestamps = [t.timestamp for t in sar.transactions]
            sar.activity_start = min(timestamps)
            sar.activity_end = max(timestamps)

        # Determine SAR type
        sar.sar_type = self._determine_sar_type(pattern_matches)

        # Determine priority
        sar.priority = self._determine_priority(pattern_matches, total_amount)

        # Generate summary
        sar.summary = self._generate_summary(pattern_matches, len(sar.subjects), total_amount)

        # Generate detailed narrative
        sar.detailed_narrative = self._generate_narrative(
            pattern_matches, sar.subjects, sar.transactions
        )

        return sar

    def create_ctr(
        self,
        transaction: dict,
        entity: dict,
        created_by: Optional[UUID] = None,
    ) -> SARReport:
        """
        Create Currency Transaction Report for large cash transaction.

        Args:
            transaction: Transaction dict
            entity: Entity data dict
            created_by: Optional user ID

        Returns:
            SARReport of type CTR
        """
        sar = SARReport(
            sar_type=SARType.CTR,
            priority=SARPriority.MEDIUM,
            created_by=created_by,
        )

        entity_id = entity.get("id")
        if entity_id:
            sar.subjects.append(SARSubject(
                entity_id=UUID(str(entity_id)) if isinstance(entity_id, str) else entity_id,
                entity_type=entity.get("entity_type", "unknown"),
                name=entity.get("name", "Unknown"),
                identifier=entity.get("identifier", ""),
            ))

        txn_id = transaction.get("id")
        amount = Decimal(str(transaction.get("amount", 0)))

        sar.transactions.append(SARTransaction(
            transaction_id=UUID(str(txn_id)) if isinstance(txn_id, str) else txn_id,
            amount=amount,
            currency=transaction.get("currency", "SEK"),
            timestamp=transaction.get("timestamp", datetime.utcnow()),
            transaction_type=transaction.get("transaction_type", "cash"),
        ))

        sar.total_amount = amount
        sar.activity_start = transaction.get("timestamp")
        sar.activity_end = transaction.get("timestamp")

        sar.suspicion_grounds = ["Cash transaction exceeding reporting threshold (150,000 SEK)"]
        sar.summary = f"Currency Transaction Report: {amount} SEK cash transaction"
        sar.detailed_narrative = f"""Currency Transaction Report

Transaction Details:
- Amount: {amount} SEK
- Type: {transaction.get('transaction_type', 'cash')}
- Date: {transaction.get('timestamp', datetime.utcnow()).isoformat()}

Subject:
- Name: {entity.get('name', 'Unknown')}
- Identifier: {entity.get('identifier', '')}

This report is filed in compliance with Swedish AML regulations
requiring reporting of cash transactions exceeding 150,000 SEK."""

        return sar

    def _determine_sar_type(self, pattern_matches: list[dict]) -> SARType:
        """Determine SAR type based on patterns detected."""
        pattern_types = {m.get("pattern_type") for m in pattern_matches}

        # Check for terrorist financing indicators
        if "terrorist_financing" in pattern_types:
            return SARType.TFAR

        # Default to general SAR
        return SARType.SAR

    def _determine_priority(
        self,
        pattern_matches: list[dict],
        total_amount: Decimal,
    ) -> SARPriority:
        """Determine SAR priority based on severity and amount."""
        severities = [m.get("severity", "low") for m in pattern_matches]

        if "critical" in severities or total_amount >= Decimal("5000000"):
            return SARPriority.URGENT
        elif "high" in severities or total_amount >= Decimal("1000000"):
            return SARPriority.HIGH
        elif "medium" in severities or total_amount >= Decimal("500000"):
            return SARPriority.MEDIUM
        return SARPriority.LOW

    def _generate_summary(
        self,
        pattern_matches: list[dict],
        subject_count: int,
        total_amount: Decimal,
    ) -> str:
        """Generate summary line for SAR."""
        pattern_types = list({m.get("pattern_type", "suspicious activity") for m in pattern_matches})

        if len(pattern_types) == 1:
            pattern_desc = pattern_types[0].replace("_", " ").title()
        else:
            pattern_desc = f"{len(pattern_types)} suspicious patterns"

        return (
            f"{pattern_desc} detected involving {subject_count} subject(s) "
            f"and {total_amount:,.0f} SEK in total transactions"
        )

    def _generate_narrative(
        self,
        pattern_matches: list[dict],
        subjects: list[SARSubject],
        transactions: list[SARTransaction],
    ) -> str:
        """Generate detailed narrative for SAR."""
        lines = ["SUSPICIOUS ACTIVITY REPORT", "=" * 40, ""]

        # Subjects section
        lines.append("SUBJECTS:")
        lines.append("-" * 20)
        for i, subject in enumerate(subjects, 1):
            lines.append(f"{i}. {subject.name}")
            lines.append(f"   Type: {subject.entity_type}")
            lines.append(f"   Identifier: {subject.identifier}")
            if subject.address:
                lines.append(f"   Address: {subject.address}")
            lines.append("")

        # Patterns section
        lines.append("DETECTED PATTERNS:")
        lines.append("-" * 20)
        for match in pattern_matches:
            lines.append(f"• {match.get('pattern_type', 'Unknown').replace('_', ' ').title()}")
            lines.append(f"  Severity: {match.get('severity', 'unknown').upper()}")
            lines.append(f"  Confidence: {match.get('confidence', 0) * 100:.0f}%")
            lines.append(f"  Description: {match.get('description', '')}")
            if match.get("total_amount"):
                lines.append(f"  Amount: {match.get('total_amount')} {match.get('currency', 'SEK')}")
            lines.append("")

        # Transactions section
        if transactions:
            lines.append("KEY TRANSACTIONS:")
            lines.append("-" * 20)
            for txn in transactions[:10]:  # Limit to 10 for readability
                lines.append(
                    f"• {txn.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                    f"{txn.amount:,.2f} {txn.currency} | {txn.transaction_type}"
                )
            if len(transactions) > 10:
                lines.append(f"  ... and {len(transactions) - 10} more transactions")
            lines.append("")

        # Conclusion
        lines.append("CONCLUSION:")
        lines.append("-" * 20)
        lines.append(
            "Based on the patterns detected and the nature of the transactions, "
            "this activity warrants further investigation by Finanspolisen."
        )

        return "\n".join(lines)

    def validate_sar(self, sar: SARReport) -> tuple[bool, list[str]]:
        """
        Validate SAR before submission.

        Returns:
            Tuple of (is_valid, list of validation errors)
        """
        errors = []

        if not sar.subjects:
            errors.append("SAR must have at least one subject")

        if not sar.summary:
            errors.append("SAR must have a summary")

        if not sar.suspicion_grounds:
            errors.append("SAR must have at least one suspicion ground")

        if not sar.detailed_narrative:
            errors.append("SAR must have a detailed narrative")

        for subject in sar.subjects:
            if not subject.name:
                errors.append(f"Subject {subject.entity_id} missing name")
            if not subject.identifier:
                errors.append(f"Subject {subject.entity_id} missing identifier")

        return len(errors) == 0, errors

    def approve_sar(
        self,
        sar: SARReport,
        reviewer_id: UUID,
    ) -> SARReport:
        """Mark SAR as approved for submission."""
        sar.status = SARStatus.APPROVED
        sar.reviewed_by = reviewer_id
        sar.reviewed_at = datetime.utcnow()
        return sar

    def submit_sar(self, sar: SARReport) -> SARReport:
        """
        Submit SAR to Finanspolisen.

        Note: Actual submission would integrate with Finanspolisen's
        goAML or similar system. This is a placeholder.
        """
        if sar.status != SARStatus.APPROVED:
            raise ValueError("SAR must be approved before submission")

        # In production, this would:
        # 1. Convert to goAML XML format
        # 2. Submit via Finanspolisen API or secure file transfer
        # 3. Receive acknowledgment reference

        sar.status = SARStatus.SUBMITTED
        sar.submitted_at = datetime.utcnow()
        sar.external_reference = f"FP-{datetime.utcnow().strftime('%Y%m%d')}-{sar.id.hex[:8].upper()}"

        logger.info(f"SAR {sar.id} submitted with reference {sar.external_reference}")

        return sar
