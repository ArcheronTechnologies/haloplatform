"""
Evidence package system for court-grade evidence compilation.

Handles:
- Evidence compilation from multiple sources
- Provenance chain tracking (hash-based)
- Authority-specific export formats
- Chain of custody documentation
"""

from halo.evidence.package import (
    EvidencePackage,
    EvidenceItem,
    PackageStatus,
    create_evidence_package,
)
from halo.evidence.provenance import (
    ProvenanceChain,
    ProvenanceEntry,
    verify_provenance,
)
from halo.evidence.export import (
    EvidenceExporter,
    ExportFormat,
)

__all__ = [
    "EvidencePackage",
    "EvidenceItem",
    "PackageStatus",
    "create_evidence_package",
    "ProvenanceChain",
    "ProvenanceEntry",
    "verify_provenance",
    "EvidenceExporter",
    "ExportFormat",
]
