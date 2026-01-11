"""
Suspicious Activity Report (SAR) Generator.

Automatically generates SAR documentation for regulatory filings.
Swedish terminology: Suspicious Transaction Report (STR) / Misstänkt transaktion
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from halo.graph.client import GraphClient


@dataclass
class SARSection:
    """A section of the SAR document."""
    title: str
    content: Any
    section_type: str = "text"  # text, table, diagram, timeline


@dataclass
class SAR:
    """Suspicious Activity Report document."""
    id: str = field(default_factory=lambda: str(uuid4()))
    sar_type: str = "str"  # str, ctr, sar, tfar (terrorism financing)
    status: str = "draft"  # draft, pending_review, approved, submitted
    priority: str = "medium"  # low, medium, high, urgent

    # Subject information
    subject_entity_id: str = ""
    subject_entity_type: str = ""
    subject_name: str = ""
    subject_identifier: str = ""  # orgnr or personnummer

    # Report details
    summary: str = ""
    trigger_reason: str = ""
    sections: list[SARSection] = field(default_factory=list)

    # Financial summary
    total_amount: Optional[float] = None
    currency: str = "SEK"
    transaction_count: int = 0

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = ""
    submitted_at: Optional[datetime] = None
    external_reference: Optional[str] = None

    # Related entities and cases
    related_entity_ids: list[str] = field(default_factory=list)
    alert_ids: list[str] = field(default_factory=list)
    case_id: Optional[str] = None

    def add_section(self, title: str, content: Any, section_type: str = "text") -> None:
        """Add a section to the SAR."""
        self.sections.append(SARSection(
            title=title,
            content=content,
            section_type=section_type
        ))

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "sar_type": self.sar_type,
            "status": self.status,
            "priority": self.priority,
            "subject_entity_id": self.subject_entity_id,
            "subject_entity_type": self.subject_entity_type,
            "subject_name": self.subject_name,
            "subject_identifier": self.subject_identifier,
            "summary": self.summary,
            "trigger_reason": self.trigger_reason,
            "sections": [
                {"title": s.title, "content": s.content, "type": s.section_type}
                for s in self.sections
            ],
            "total_amount": self.total_amount,
            "currency": self.currency,
            "transaction_count": self.transaction_count,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "external_reference": self.external_reference,
            "related_entity_ids": self.related_entity_ids,
            "alert_ids": self.alert_ids,
            "case_id": self.case_id,
        }


class SARGenerator:
    """
    Generate Suspicious Activity Report documentation automatically.

    Creates comprehensive reports for regulatory filing based on
    detected patterns, network analysis, and evidence.
    """

    def __init__(self, graph_client: Optional[GraphClient] = None):
        self.graph = graph_client

    async def generate_sar(
        self,
        entity_id: str,
        trigger_reason: str,
        alert_ids: Optional[list[str]] = None,
        case_id: Optional[str] = None,
        created_by: str = "system"
    ) -> SAR:
        """
        Generate a SAR for the given entity.

        Args:
            entity_id: The primary subject entity
            trigger_reason: Why this SAR is being generated
            alert_ids: Related alert IDs
            case_id: Related case ID
            created_by: User or system generating the SAR
        """
        # Get entity details
        entity = await self._get_entity(entity_id)
        entity_type = entity.get("_type", "Company")

        # Initialize SAR
        sar = SAR(
            subject_entity_id=entity_id,
            subject_entity_type=entity_type,
            subject_name=entity.get("display_name", "Unknown"),
            subject_identifier=entity.get("orgnr") or entity.get("personnummer", ""),
            trigger_reason=trigger_reason,
            alert_ids=alert_ids or [],
            case_id=case_id,
            created_by=created_by
        )

        # Expand network for context
        network = await self._expand_network(entity_id, hops=2)

        # Get pattern matches
        patterns = await self._get_pattern_matches(entity_id)

        # Get timeline of events
        timeline = await self._get_event_timeline(entity_id)

        # Calculate risk score
        risk_assessment = await self._calculate_risk(entity_id)

        # Build sections

        # 1. Subject Identification
        sar.add_section(
            "Subject Identification",
            self._format_entity_details(entity),
            "table"
        )

        # 2. Executive Summary
        summary = self._generate_summary(entity, patterns, risk_assessment, trigger_reason)
        sar.summary = summary
        sar.add_section("Executive Summary", summary, "text")

        # 3. Relationship Map
        sar.add_section(
            "Relationship Map",
            self._format_network_for_report(network),
            "diagram"
        )

        # 4. Timeline of Suspicious Activity
        sar.add_section(
            "Timeline of Suspicious Activity",
            self._format_timeline(timeline),
            "timeline"
        )

        # 5. Pattern Analysis
        sar.add_section(
            "Pattern Analysis",
            self._format_pattern_matches(patterns),
            "table"
        )

        # 6. Evidence Chain
        evidence = await self._gather_evidence(entity_id, network)
        sar.add_section(
            "Evidence Chain",
            self._format_evidence(evidence),
            "table"
        )

        # 7. Risk Assessment
        sar.add_section(
            "Risk Assessment",
            {
                "overall_score": risk_assessment.get("score", 0),
                "risk_level": risk_assessment.get("level", "unknown"),
                "risk_factors": risk_assessment.get("factors", []),
                "rationale": risk_assessment.get("rationale", "")
            },
            "table"
        )

        # 8. Recommended Actions
        recommendations = self._generate_recommendations(risk_assessment, patterns)
        sar.add_section(
            "Recommended Actions",
            recommendations,
            "text"
        )

        # 9. Related Entities
        related = list(network.get("nodes", {}).keys())
        related = [r for r in related if r != entity_id]
        sar.related_entity_ids = related[:50]  # Limit to 50
        sar.add_section(
            "Related Entities",
            self._format_related_entities(network),
            "table"
        )

        # Calculate financial totals if available
        financial = await self._get_financial_summary(entity_id)
        sar.total_amount = financial.get("total_amount")
        sar.transaction_count = financial.get("transaction_count", 0)

        # Set priority based on risk
        sar.priority = self._determine_priority(risk_assessment, patterns)

        return sar

    def _format_entity_details(self, entity: dict) -> dict:
        """Format entity details for the report."""
        entity_type = entity.get("_type", "Unknown")

        if entity_type == "Company":
            return {
                "Type": "Company (Företag)",
                "Name": entity.get("display_name", "Unknown"),
                "Organisation Number": entity.get("orgnr", ""),
                "Legal Form": entity.get("legal_form", ""),
                "Status": entity.get("status", {}).get("text", "Unknown"),
                "Formation Date": entity.get("formation", {}).get("date", ""),
                "Address": self._format_address(entity.get("addresses", [])),
                "Industry (SNI)": self._format_sni(entity.get("sni_codes", [])),
                "Employees": (entity.get("employees") or {}).get("count", "Unknown"),
                "F-skatt": "Yes" if (entity.get("f_skatt") or {}).get("registered") else "No",
                "VAT Registered": "Yes" if (entity.get("vat") or {}).get("registered") else "No",
            }
        elif entity_type == "Person":
            return {
                "Type": "Person",
                "Name": entity.get("display_name", "Unknown"),
                "Personal Number": entity.get("personnummer", "Protected/Unknown"),
                "Nationality": entity.get("nationality", "Unknown"),
                "PEP Status": "Yes" if entity.get("pep_status", {}).get("is_pep") else "No",
                "Address": self._format_address(entity.get("addresses", [])),
            }
        else:
            return {"Type": entity_type, "ID": entity.get("id", "")}

    def _format_address(self, addresses: list[dict]) -> str:
        """Format address list."""
        if not addresses:
            return "Unknown"

        # Get current address
        current = [a for a in addresses if not a.get("to_date")]
        if current:
            addr = current[0]
        else:
            addr = addresses[0]

        normalized = addr.get("normalized", {})
        parts = []
        if normalized.get("street"):
            street = normalized["street"]
            if normalized.get("number"):
                street += f" {normalized['number']}"
            parts.append(street)
        if normalized.get("postal_code"):
            parts.append(normalized["postal_code"])
        if normalized.get("city"):
            parts.append(normalized["city"])

        return ", ".join(parts) if parts else "Unknown"

    def _format_sni(self, sni_codes: list[dict]) -> str:
        """Format SNI codes."""
        if not sni_codes:
            return "Unknown"
        return ", ".join([s.get("code", "") for s in sni_codes[:3]])

    def _generate_summary(
        self,
        entity: dict,
        patterns: list[dict],
        risk: dict,
        trigger: str
    ) -> str:
        """Generate executive summary."""
        name = entity.get("display_name", "Unknown")
        entity_type = entity.get("_type", "entity")
        risk_level = risk.get("level", "unknown")

        pattern_count = len(patterns)
        pattern_types = list(set(p.get("typology", "") for p in patterns))

        summary_parts = [
            f"This Suspicious Activity Report concerns {name}, a {entity_type} "
            f"that has been flagged for review due to: {trigger}.",
            "",
            f"Risk Assessment: {risk_level.upper()}",
            f"Risk Score: {risk.get('score', 0):.2f}",
            "",
        ]

        if pattern_count > 0:
            summary_parts.append(
                f"The entity matches {pattern_count} fraud pattern(s) including: "
                f"{', '.join(pattern_types)}."
            )

        factors = risk.get("factors", [])
        if factors:
            summary_parts.append("")
            summary_parts.append("Key Risk Factors:")
            for factor in factors[:5]:
                summary_parts.append(f"  - {factor}")

        return "\n".join(summary_parts)

    def _format_network_for_report(self, network: dict) -> dict:
        """Format network data for visualization."""
        nodes = network.get("nodes", {})
        edges = network.get("edges", [])

        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": [
                {
                    "id": node_id,
                    "type": data.get("_type", "Unknown"),
                    "name": data.get("display_name", data.get("orgnr", node_id[:8])),
                    "risk_score": data.get("risk_score", 0),
                }
                for node_id, data in list(nodes.items())[:20]
            ],
            "edges": [
                {
                    "from": e.get("from"),
                    "to": e.get("to"),
                    "type": e.get("type", ""),
                }
                for e in edges[:50]
            ]
        }

    def _format_timeline(self, events: list[dict]) -> list[dict]:
        """Format timeline for report."""
        formatted = []
        for event in events:
            formatted.append({
                "date": event.get("date", ""),
                "event_type": event.get("type", ""),
                "description": event.get("description", ""),
                "significance": event.get("significance", "normal"),  # normal, suspicious, critical
            })
        return formatted

    def _format_pattern_matches(self, patterns: list[dict]) -> list[dict]:
        """Format pattern matches for report."""
        return [
            {
                "pattern_name": p.get("name", ""),
                "pattern_id": p.get("id", ""),
                "severity": p.get("severity", ""),
                "typology": p.get("typology", ""),
                "description": p.get("description", ""),
            }
            for p in patterns
        ]

    def _format_evidence(self, evidence: list[dict]) -> list[dict]:
        """Format evidence chain for report."""
        return [
            {
                "evidence_type": e.get("type", ""),
                "source": e.get("source", ""),
                "date": e.get("date", ""),
                "description": e.get("description", ""),
                "document_ref": e.get("document_ref"),
            }
            for e in evidence
        ]

    def _format_related_entities(self, network: dict) -> list[dict]:
        """Format related entities for report."""
        nodes = network.get("nodes", {})
        formatted = []

        for node_id, data in list(nodes.items())[:20]:
            formatted.append({
                "id": node_id,
                "type": data.get("_type", "Unknown"),
                "name": data.get("display_name", "Unknown"),
                "identifier": data.get("orgnr") or data.get("personnummer", ""),
                "relationship": "Direct" if data.get("depth", 1) == 1 else "Indirect",
                "risk_score": data.get("risk_score", 0),
            })

        return formatted

    def _generate_recommendations(
        self,
        risk: dict,
        patterns: list[dict]
    ) -> list[str]:
        """Generate recommended actions."""
        recommendations = []
        risk_level = risk.get("level", "low")

        # Base recommendations on risk level
        if risk_level == "critical":
            recommendations.extend([
                "IMMEDIATE: Escalate to senior compliance officer",
                "IMMEDIATE: Consider filing STR with Finanspolisen",
                "Freeze or restrict account activity pending investigation",
                "Document all findings for potential law enforcement referral",
            ])
        elif risk_level == "high":
            recommendations.extend([
                "Assign to compliance team for detailed investigation",
                "Prepare preliminary STR documentation",
                "Expand network analysis to identify all related parties",
                "Schedule management review within 48 hours",
            ])
        elif risk_level == "medium":
            recommendations.extend([
                "Assign to analyst for further review",
                "Document findings in case management system",
                "Monitor entity for changes",
                "Review in 30 days if no new information",
            ])
        else:
            recommendations.extend([
                "Add to watchlist for periodic review",
                "No immediate action required",
                "Review annually or if new alerts triggered",
            ])

        # Pattern-specific recommendations
        pattern_types = set(p.get("typology", "") for p in patterns)

        if "money_laundering" in pattern_types:
            recommendations.append("Review all transaction history for layering patterns")

        if "tax_fraud" in pattern_types:
            recommendations.append("Consider referral to Skatteverket if tax fraud suspected")

        if "shell_company_network" in pattern_types:
            recommendations.append("Map full corporate structure and beneficial ownership")

        return recommendations

    def _determine_priority(self, risk: dict, patterns: list[dict]) -> str:
        """Determine SAR priority."""
        risk_level = risk.get("level", "low")

        # Check for critical patterns
        critical_patterns = any(p.get("severity") == "critical" for p in patterns)

        if risk_level == "critical" or critical_patterns:
            return "urgent"
        elif risk_level == "high":
            return "high"
        elif risk_level == "medium":
            return "medium"
        else:
            return "low"

    # Data retrieval methods

    async def _get_entity(self, entity_id: str) -> dict:
        """Get entity data."""
        if self.graph:
            company = await self.graph.get_company(entity_id)
            if company:
                return company
            person = await self.graph.get_person(entity_id)
            if person:
                return person
        return {"id": entity_id}

    async def _expand_network(self, entity_id: str, hops: int) -> dict:
        """Expand network from entity."""
        if self.graph:
            return await self.graph.expand_network([entity_id], hops=hops)
        return {"nodes": {}, "edges": []}

    async def _get_pattern_matches(self, entity_id: str) -> list[dict]:
        """Get pattern matches for entity."""
        # Would integrate with PatternMatcher
        return []

    async def _get_event_timeline(self, entity_id: str) -> list[dict]:
        """Get timeline of events."""
        # Would get from sequence detector
        return []

    async def _calculate_risk(self, entity_id: str) -> dict:
        """Calculate risk assessment."""
        # Would integrate with RiskPredictor
        return {
            "score": 0.0,
            "level": "unknown",
            "factors": [],
            "rationale": ""
        }

    async def _gather_evidence(self, entity_id: str, network: dict) -> list[dict]:
        """Gather evidence from various sources."""
        evidence = []

        # Add entity data as evidence
        evidence.append({
            "type": "entity_data",
            "source": "Halo Intelligence Graph",
            "date": datetime.utcnow().isoformat(),
            "description": "Entity profile and attributes",
        })

        # Add network analysis as evidence
        if network.get("nodes"):
            evidence.append({
                "type": "network_analysis",
                "source": "Halo Graph Analysis",
                "date": datetime.utcnow().isoformat(),
                "description": f"Network of {len(network.get('nodes', {}))} related entities",
            })

        return evidence

    async def _get_financial_summary(self, entity_id: str) -> dict:
        """Get financial summary."""
        return {
            "total_amount": None,
            "transaction_count": 0
        }
