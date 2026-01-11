"""
Real-time alerting for pattern matches.

Generates alerts when high-risk patterns are detected.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    """Types of alerts."""

    SHELL_NETWORK = "shell_network"
    REGISTRATION_MILL = "registration_mill"
    PHOENIX_COMPANY = "phoenix_company"
    HIGH_RISK_FORMATION = "high_risk_formation"
    DIRECTOR_VELOCITY = "director_velocity"
    NETWORK_CLUSTER = "network_cluster"
    SANCTIONS_MATCH = "sanctions_match"
    PATTERN_MATCH = "pattern_match"


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Alert:
    """An alert generated from pattern detection."""

    id: UUID
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    description: str
    entity_ids: list[UUID] = field(default_factory=list)
    pattern_data: dict[str, Any] = field(default_factory=dict)
    risk_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "entity_ids": [str(e) for e in self.entity_ids],
            "pattern_data": self.pattern_data,
            "risk_score": self.risk_score,
            "created_at": self.created_at.isoformat(),
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "notes": self.notes,
        }

    def acknowledge(self, user_id: str, notes: str = "") -> None:
        """Acknowledge the alert."""
        self.acknowledged = True
        self.acknowledged_by = user_id
        self.acknowledged_at = datetime.utcnow()
        self.notes = notes


@dataclass
class AlertRule:
    """A rule for generating alerts."""

    id: str
    name: str
    alert_type: AlertType
    severity: AlertSeverity
    condition: str  # Description of condition
    min_risk_score: float = 0.5
    enabled: bool = True


class AlertGenerator:
    """
    Generate alerts from pattern detection results.

    Applies rules to determine severity and deduplicates alerts.
    """

    # Default alert rules
    DEFAULT_RULES = [
        AlertRule(
            id="shell_network_high",
            name="High-Risk Shell Network",
            alert_type=AlertType.SHELL_NETWORK,
            severity=AlertSeverity.HIGH,
            condition="Person directs 5+ shell companies",
            min_risk_score=0.7,
        ),
        AlertRule(
            id="shell_network_critical",
            name="Critical Shell Network",
            alert_type=AlertType.SHELL_NETWORK,
            severity=AlertSeverity.CRITICAL,
            condition="Person directs 10+ shell companies with shared addresses",
            min_risk_score=0.85,
        ),
        AlertRule(
            id="registration_mill",
            name="Registration Mill Detected",
            alert_type=AlertType.REGISTRATION_MILL,
            severity=AlertSeverity.HIGH,
            condition="Address has 10+ companies with shared directors",
            min_risk_score=0.6,
        ),
        AlertRule(
            id="high_risk_formation",
            name="High-Risk New Company",
            alert_type=AlertType.HIGH_RISK_FORMATION,
            severity=AlertSeverity.MEDIUM,
            condition="New company formed with multiple risk indicators",
            min_risk_score=0.5,
        ),
        AlertRule(
            id="director_velocity",
            name="Rapid Director Changes",
            alert_type=AlertType.DIRECTOR_VELOCITY,
            severity=AlertSeverity.MEDIUM,
            condition="Company changed directors 3+ times in 12 months",
            min_risk_score=0.5,
        ),
    ]

    def __init__(self, rules: Optional[list[AlertRule]] = None):
        self.rules = rules or self.DEFAULT_RULES
        self._alerts: dict[UUID, Alert] = {}
        self._dedup_keys: set[str] = set()

    def generate_shell_network_alert(
        self,
        person_id: UUID,
        person_name: str,
        company_count: int,
        risk_score: float,
        indicators: list[str],
        company_ids: list[UUID],
    ) -> Optional[Alert]:
        """Generate alert for shell network detection."""
        # Determine severity based on risk score and company count
        if risk_score >= 0.85 or company_count >= 10:
            severity = AlertSeverity.CRITICAL
        elif risk_score >= 0.7 or company_count >= 5:
            severity = AlertSeverity.HIGH
        elif risk_score >= 0.5:
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW

        # Deduplication key
        dedup_key = f"shell_network:{person_id}"
        if dedup_key in self._dedup_keys:
            logger.debug(f"Duplicate alert for {person_id}, skipping")
            return None

        alert = Alert(
            id=uuid4(),
            alert_type=AlertType.SHELL_NETWORK,
            severity=severity,
            title=f"Shell Network: {person_name}",
            description=(
                f"{person_name} directs {company_count} potential shell companies. "
                f"Risk score: {risk_score:.2f}. "
                f"Indicators: {', '.join(indicators)}"
            ),
            entity_ids=[person_id] + company_ids,
            pattern_data={
                "person_id": str(person_id),
                "person_name": person_name,
                "company_count": company_count,
                "indicators": indicators,
            },
            risk_score=risk_score,
        )

        self._alerts[alert.id] = alert
        self._dedup_keys.add(dedup_key)

        logger.info(
            f"Generated {severity.value} alert for shell network: {person_name}"
        )

        return alert

    def generate_registration_mill_alert(
        self,
        address_id: UUID,
        address: str,
        company_count: int,
        shared_director_count: int,
        risk_score: float,
    ) -> Optional[Alert]:
        """Generate alert for registration mill detection."""
        if risk_score >= 0.8 or company_count >= 20:
            severity = AlertSeverity.CRITICAL
        elif risk_score >= 0.6 or company_count >= 10:
            severity = AlertSeverity.HIGH
        else:
            severity = AlertSeverity.MEDIUM

        dedup_key = f"registration_mill:{address_id}"
        if dedup_key in self._dedup_keys:
            return None

        alert = Alert(
            id=uuid4(),
            alert_type=AlertType.REGISTRATION_MILL,
            severity=severity,
            title=f"Registration Mill: {address}",
            description=(
                f"Address has {company_count} registered companies with "
                f"{shared_director_count} shared directors. "
                f"Risk score: {risk_score:.2f}"
            ),
            entity_ids=[address_id],
            pattern_data={
                "address_id": str(address_id),
                "address": address,
                "company_count": company_count,
                "shared_director_count": shared_director_count,
            },
            risk_score=risk_score,
        )

        self._alerts[alert.id] = alert
        self._dedup_keys.add(dedup_key)

        logger.info(
            f"Generated {severity.value} alert for registration mill: {address}"
        )

        return alert

    def generate_high_risk_formation_alert(
        self,
        company_id: UUID,
        company_name: str,
        orgnummer: str,
        risk_score: float,
        indicators: list[str],
        director_id: Optional[UUID] = None,
    ) -> Optional[Alert]:
        """Generate alert for high-risk new company formation."""
        if risk_score < 0.5:
            return None

        if risk_score >= 0.8:
            severity = AlertSeverity.HIGH
        elif risk_score >= 0.6:
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW

        dedup_key = f"formation:{company_id}"
        if dedup_key in self._dedup_keys:
            return None

        entity_ids = [company_id]
        if director_id:
            entity_ids.append(director_id)

        alert = Alert(
            id=uuid4(),
            alert_type=AlertType.HIGH_RISK_FORMATION,
            severity=severity,
            title=f"High-Risk Formation: {company_name}",
            description=(
                f"New company {company_name} ({orgnummer}) formed with risk indicators: "
                f"{', '.join(indicators)}. Risk score: {risk_score:.2f}"
            ),
            entity_ids=entity_ids,
            pattern_data={
                "company_id": str(company_id),
                "company_name": company_name,
                "orgnummer": orgnummer,
                "indicators": indicators,
            },
            risk_score=risk_score,
        )

        self._alerts[alert.id] = alert
        self._dedup_keys.add(dedup_key)

        return alert

    def get_alert(self, alert_id: UUID) -> Optional[Alert]:
        """Get an alert by ID."""
        return self._alerts.get(alert_id)

    def get_alerts(
        self,
        alert_type: Optional[AlertType] = None,
        severity: Optional[AlertSeverity] = None,
        acknowledged: Optional[bool] = None,
        limit: int = 50,
    ) -> list[Alert]:
        """Get alerts with optional filtering."""
        alerts = list(self._alerts.values())

        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]

        # Sort by created_at descending
        alerts.sort(key=lambda a: a.created_at, reverse=True)

        return alerts[:limit]

    def acknowledge_alert(
        self,
        alert_id: UUID,
        user_id: str,
        notes: str = "",
    ) -> Optional[Alert]:
        """Acknowledge an alert."""
        alert = self._alerts.get(alert_id)
        if alert:
            alert.acknowledge(user_id, notes)
            logger.info(f"Alert {alert_id} acknowledged by {user_id}")
        return alert

    def get_stats(self) -> dict[str, Any]:
        """Get alert statistics."""
        alerts = list(self._alerts.values())

        by_type = {}
        by_severity = {}
        acknowledged_count = 0

        for alert in alerts:
            by_type[alert.alert_type.value] = by_type.get(alert.alert_type.value, 0) + 1
            by_severity[alert.severity.value] = by_severity.get(alert.severity.value, 0) + 1
            if alert.acknowledged:
                acknowledged_count += 1

        return {
            "total": len(alerts),
            "acknowledged": acknowledged_count,
            "unacknowledged": len(alerts) - acknowledged_count,
            "by_type": by_type,
            "by_severity": by_severity,
        }

    def clear(self) -> None:
        """Clear all alerts."""
        self._alerts.clear()
        self._dedup_keys.clear()
