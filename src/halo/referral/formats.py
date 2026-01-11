"""
Authority-specific referral formats.

Converts internal referral data into formats required by each Swedish authority.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class FormattedReferral:
    """A referral formatted for a specific authority."""

    authority: str
    format_version: str
    content: dict[str, Any]
    raw_xml: Optional[str] = None
    raw_json: Optional[str] = None


class ReferralFormatter(ABC):
    """Base class for authority-specific formatters."""

    @property
    @abstractmethod
    def authority_code(self) -> str:
        """Return the authority code this formatter handles."""
        pass

    @property
    @abstractmethod
    def format_version(self) -> str:
        """Return the format version identifier."""
        pass

    @abstractmethod
    def format(
        self,
        case_id: UUID,
        summary: str,
        evidence: list[dict],
        entities: list[dict],
        detections: list[dict],
        metadata: Optional[dict] = None,
    ) -> FormattedReferral:
        """Format a referral for this authority."""
        pass


class EBMFormat(ReferralFormatter):
    """
    Formatter for Ekobrottsmyndigheten (Economic Crime Authority).

    Uses EBM's digital referral format for economic crime cases.
    """

    @property
    def authority_code(self) -> str:
        return "EBM"

    @property
    def format_version(self) -> str:
        return "EBM_REFERRAL_2024_v1"

    def format(
        self,
        case_id: UUID,
        summary: str,
        evidence: list[dict],
        entities: list[dict],
        detections: list[dict],
        metadata: Optional[dict] = None,
    ) -> FormattedReferral:
        """
        Format referral for EBM.

        EBM requires:
        - Structured case summary
        - Entity list with identifiers (orgnr, personnummer)
        - Evidence chain with provenance
        - Financial impact estimation
        """
        metadata = metadata or {}

        # Extract companies (huvudmål - main targets)
        companies = [e for e in entities if e.get("entity_type") == "company"]

        # Extract persons (misstänkta - suspects)
        persons = [e for e in entities if e.get("entity_type") == "person"]

        # Calculate estimated value
        estimated_value = sum(
            d.get("estimated_value_sek", 0) for d in detections
        )

        content = {
            "header": {
                "format": self.format_version,
                "timestamp": datetime.utcnow().isoformat(),
                "source_system": "Halo Intelligence Platform",
                "case_reference": str(case_id),
            },
            "summary": {
                "title": f"Ekonomisk brottsmisstanke - {summary[:100]}",
                "description": summary,
                "brottstyp": metadata.get("crime_type", "Ekobrott"),
                "estimated_value_sek": estimated_value,
            },
            "targets": {
                "companies": [
                    {
                        "name": c.get("display_name", ""),
                        "organisationsnummer": c.get("organisationsnummer", ""),
                        "role": "huvudmål",
                    }
                    for c in companies[:10]  # Limit to 10
                ],
                "persons": [
                    {
                        "name": p.get("display_name", ""),
                        "personnummer": p.get("personnummer", ""),  # Masked
                        "role": p.get("role", "misstänkt"),
                    }
                    for p in persons[:20]  # Limit to 20
                ],
            },
            "evidence": {
                "count": len(evidence),
                "items": [
                    {
                        "type": e.get("type", "document"),
                        "description": e.get("description", ""),
                        "source": e.get("source", ""),
                        "hash": e.get("hash", ""),
                    }
                    for e in evidence[:50]
                ],
            },
            "detections": {
                "count": len(detections),
                "patterns": [
                    {
                        "type": d.get("pattern_type", ""),
                        "confidence": d.get("confidence", 0),
                        "description": d.get("description", ""),
                    }
                    for d in detections[:10]
                ],
            },
        }

        return FormattedReferral(
            authority=self.authority_code,
            format_version=self.format_version,
            content=content,
            raw_json=json.dumps(content, ensure_ascii=False, indent=2),
        )


class SkatteverketFormat(ReferralFormatter):
    """
    Formatter for Skatteverket (Swedish Tax Agency).

    Uses Skatteverket's kontrolluppgift format for tax fraud cases.
    """

    @property
    def authority_code(self) -> str:
        return "SKV"

    @property
    def format_version(self) -> str:
        return "SKV_KONTROLLUPPGIFT_2024_v1"

    def format(
        self,
        case_id: UUID,
        summary: str,
        evidence: list[dict],
        entities: list[dict],
        detections: list[dict],
        metadata: Optional[dict] = None,
    ) -> FormattedReferral:
        """
        Format referral for Skatteverket.

        Skatteverket requires:
        - Tax identification numbers
        - Period of suspected fraud
        - Estimated undeclared amounts
        """
        metadata = metadata or {}

        # Extract relevant entities
        companies = [e for e in entities if e.get("entity_type") == "company"]
        persons = [e for e in entities if e.get("entity_type") == "person"]

        # Calculate tax impact
        estimated_tax_loss = sum(
            d.get("estimated_tax_impact_sek", 0) for d in detections
        )

        content = {
            "header": {
                "format": self.format_version,
                "timestamp": datetime.utcnow().isoformat(),
                "source_system": "Halo Intelligence Platform",
                "case_reference": str(case_id),
            },
            "kontrolluppgift": {
                "typ": metadata.get("tax_type", "Skattebrott"),
                "period_start": metadata.get("period_start", ""),
                "period_end": metadata.get("period_end", ""),
                "estimated_undeclared_sek": estimated_tax_loss,
            },
            "skattskyldiga": [
                {
                    "typ": "juridisk_person" if e.get("entity_type") == "company" else "fysisk_person",
                    "namn": e.get("display_name", ""),
                    "organisationsnummer": e.get("organisationsnummer", ""),
                    "personnummer": e.get("personnummer", ""),
                }
                for e in (companies + persons)[:20]
            ],
            "underlag": {
                "description": summary,
                "evidence_count": len(evidence),
                "detection_count": len(detections),
            },
        }

        return FormattedReferral(
            authority=self.authority_code,
            format_version=self.format_version,
            content=content,
            raw_json=json.dumps(content, ensure_ascii=False, indent=2),
        )


class FIUFormat(ReferralFormatter):
    """
    Formatter for Financial Intelligence Unit (Finanspolisen).

    Uses goAML format for suspicious activity reports (SARs).
    """

    @property
    def authority_code(self) -> str:
        return "FIU"

    @property
    def format_version(self) -> str:
        return "GOAML_SE_2024_v1"

    def format(
        self,
        case_id: UUID,
        summary: str,
        evidence: list[dict],
        entities: list[dict],
        detections: list[dict],
        metadata: Optional[dict] = None,
    ) -> FormattedReferral:
        """
        Format referral for FIU as a SAR (Suspicious Activity Report).

        FIU requires goAML-compatible format with:
        - Transaction details
        - Account information
        - Suspicious indicators
        """
        metadata = metadata or {}

        content = {
            "report_header": {
                "format": self.format_version,
                "report_type": "SAR",
                "submission_date": datetime.utcnow().isoformat(),
                "reporting_entity": "Halo Intelligence Platform",
                "case_reference": str(case_id),
            },
            "report_info": {
                "reason": summary,
                "suspicion_indicators": [
                    d.get("indicator_type", "") for d in detections
                ],
                "priority": metadata.get("priority", "normal"),
            },
            "subjects": [
                {
                    "role": "subject",
                    "entity_type": e.get("entity_type", ""),
                    "name": e.get("display_name", ""),
                    "identifier": e.get("organisationsnummer") or e.get("personnummer", ""),
                }
                for e in entities[:20]
            ],
            "transactions": metadata.get("transactions", []),
            "narrative": summary,
        }

        return FormattedReferral(
            authority=self.authority_code,
            format_version=self.format_version,
            content=content,
            raw_json=json.dumps(content, ensure_ascii=False, indent=2),
        )


# Registry of available formatters
FORMATTERS: dict[str, type[ReferralFormatter]] = {
    "EBM": EBMFormat,
    "SKV": SkatteverketFormat,
    "FIU": FIUFormat,
}


def get_formatter(authority_code: str) -> ReferralFormatter:
    """Get the appropriate formatter for an authority."""
    formatter_class = FORMATTERS.get(authority_code)
    if not formatter_class:
        raise ValueError(f"No formatter available for authority: {authority_code}")
    return formatter_class()
