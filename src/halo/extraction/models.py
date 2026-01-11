"""Data models for director extraction."""

from dataclasses import dataclass, field
from typing import Optional
from datetime import date


@dataclass
class ExtractedDirector:
    """A director/board member extracted from an annual report."""

    first_name: str
    last_name: str
    role: str  # Original Swedish text
    role_normalized: str  # VD, STYRELSEORDFORANDE, STYRELSELEDAMOT, etc.
    confidence: float  # 0.0 - 1.0
    source_field: str  # XBRL field name that contained this data

    @property
    def full_name(self) -> str:
        """Get the full name."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def name_normalized(self) -> str:
        """Normalize name for deduplication/matching."""
        name = self.full_name.lower()
        name = name.replace("-", " ")
        name = name.replace("å", "a").replace("ä", "a").replace("ö", "o")
        name = name.replace("é", "e").replace("è", "e").replace("ü", "u")
        return " ".join(name.split())


@dataclass
class ExtractedAuditor:
    """An auditor extracted from an annual report."""

    name: str
    firm: Optional[str]
    auditor_type: str  # auktoriserad, godkänd, unknown
    confidence: float


@dataclass
class ExtractionResult:
    """Complete extraction result for one annual report."""

    orgnr: str
    document_id: str
    company_name: Optional[str] = None
    directors: list[ExtractedDirector] = field(default_factory=list)
    auditors: list[ExtractedAuditor] = field(default_factory=list)
    signature_date: Optional[date] = None
    reporting_period_end: Optional[date] = None
    extraction_confidence: float = 0.0
    extraction_method: str = "xbrl"  # "xbrl" or "pdf"
    warnings: list[str] = field(default_factory=list)
    processing_time_ms: int = 0

    @property
    def has_directors(self) -> bool:
        return len(self.directors) > 0

    @property
    def has_vd(self) -> bool:
        return any(d.role_normalized == "VD" for d in self.directors)

    @property
    def has_ordforande(self) -> bool:
        return any(d.role_normalized == "STYRELSEORDFORANDE" for d in self.directors)
