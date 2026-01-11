"""
Evidence package export functionality.

Exports evidence packages in various formats for different authorities and purposes.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from halo.evidence.package import EvidencePackage

logger = logging.getLogger(__name__)


class ExportFormat(str, Enum):
    """Supported export formats."""

    JSON = "json"
    PDF = "pdf"
    XML = "xml"
    CSV = "csv"


@dataclass
class ExportResult:
    """Result of an evidence package export."""

    format: ExportFormat
    filename: str
    content: bytes
    content_type: str
    exported_at: datetime
    package_hash: str


class EvidenceExporter:
    """
    Exports evidence packages in various formats.

    Supports multiple output formats for different use cases:
    - JSON: Machine-readable, API responses
    - PDF: Human-readable court documents
    - XML: Authority-specific formats
    - CSV: Spreadsheet analysis
    """

    def export(
        self,
        package: EvidencePackage,
        format: ExportFormat,
        options: Optional[dict] = None,
    ) -> ExportResult:
        """
        Export an evidence package in the specified format.

        Args:
            package: The evidence package to export
            format: Target export format
            options: Format-specific options

        Returns:
            ExportResult with the exported content
        """
        options = options or {}

        if format == ExportFormat.JSON:
            return self._export_json(package, options)
        elif format == ExportFormat.CSV:
            return self._export_csv(package, options)
        elif format == ExportFormat.XML:
            return self._export_xml(package, options)
        elif format == ExportFormat.PDF:
            return self._export_pdf(package, options)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _export_json(
        self,
        package: EvidencePackage,
        options: dict,
    ) -> ExportResult:
        """Export as JSON."""
        indent = options.get("indent", 2)
        data = package.to_dict()

        content = json.dumps(
            data,
            ensure_ascii=False,
            indent=indent,
            default=str,
        ).encode("utf-8")

        return ExportResult(
            format=ExportFormat.JSON,
            filename=f"evidence_package_{package.id}.json",
            content=content,
            content_type="application/json",
            exported_at=datetime.utcnow(),
            package_hash=package.package_hash or package.calculate_hash(),
        )

    def _export_csv(
        self,
        package: EvidencePackage,
        options: dict,
    ) -> ExportResult:
        """Export evidence items as CSV."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "Item ID",
            "Type",
            "Title",
            "Description",
            "Source",
            "Source Timestamp",
            "Content Hash",
        ])

        # Data rows
        for item in package.items:
            writer.writerow([
                str(item.id),
                item.item_type,
                item.title,
                item.description,
                item.source,
                item.source_timestamp.isoformat(),
                item.content_hash,
            ])

        content = output.getvalue().encode("utf-8")

        return ExportResult(
            format=ExportFormat.CSV,
            filename=f"evidence_package_{package.id}.csv",
            content=content,
            content_type="text/csv",
            exported_at=datetime.utcnow(),
            package_hash=package.package_hash or package.calculate_hash(),
        )

    def _export_xml(
        self,
        package: EvidencePackage,
        options: dict,
    ) -> ExportResult:
        """Export as XML."""
        # Simple XML generation (would use proper XML library in production)
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<evidence_package id="{package.id}">',
            f'  <case_id>{package.case_id}</case_id>',
            f'  <title>{self._xml_escape(package.title)}</title>',
            f'  <status>{package.status.value}</status>',
            f'  <created_at>{package.created_at.isoformat()}</created_at>',
            f'  <created_by>{self._xml_escape(package.created_by)}</created_by>',
            f'  <summary>{self._xml_escape(package.summary)}</summary>',
            '  <items>',
        ]

        for item in package.items:
            lines.extend([
                f'    <item id="{item.id}">',
                f'      <type>{item.item_type}</type>',
                f'      <title>{self._xml_escape(item.title)}</title>',
                f'      <description>{self._xml_escape(item.description)}</description>',
                f'      <source>{self._xml_escape(item.source)}</source>',
                f'      <source_timestamp>{item.source_timestamp.isoformat()}</source_timestamp>',
                f'      <content_hash>{item.content_hash}</content_hash>',
                '    </item>',
            ])

        lines.extend([
            '  </items>',
            f'  <package_hash>{package.package_hash or ""}</package_hash>',
            '</evidence_package>',
        ])

        content = '\n'.join(lines).encode("utf-8")

        return ExportResult(
            format=ExportFormat.XML,
            filename=f"evidence_package_{package.id}.xml",
            content=content,
            content_type="application/xml",
            exported_at=datetime.utcnow(),
            package_hash=package.package_hash or package.calculate_hash(),
        )

    def _export_pdf(
        self,
        package: EvidencePackage,
        options: dict,
    ) -> ExportResult:
        """
        Export as PDF.

        Note: This is a placeholder. In production, use a proper PDF library
        like reportlab or weasyprint.
        """
        # Placeholder - return a text file with PDF extension
        lines = [
            "EVIDENCE PACKAGE",
            "=" * 50,
            "",
            f"Package ID: {package.id}",
            f"Case ID: {package.case_id}",
            f"Title: {package.title}",
            f"Status: {package.status.value}",
            f"Created: {package.created_at.isoformat()}",
            f"Created By: {package.created_by}",
            "",
            "SUMMARY",
            "-" * 50,
            package.summary,
            "",
            "EVIDENCE ITEMS",
            "-" * 50,
        ]

        for i, item in enumerate(package.items, 1):
            lines.extend([
                f"\n{i}. {item.title}",
                f"   Type: {item.item_type}",
                f"   Source: {item.source}",
                f"   Hash: {item.content_hash[:16]}...",
            ])

        lines.extend([
            "",
            "=" * 50,
            f"Package Hash: {package.package_hash or 'Not sealed'}",
            f"Sealed At: {package.sealed_at.isoformat() if package.sealed_at else 'Not sealed'}",
        ])

        content = '\n'.join(lines).encode("utf-8")

        return ExportResult(
            format=ExportFormat.PDF,
            filename=f"evidence_package_{package.id}.pdf",
            content=content,
            content_type="application/pdf",
            exported_at=datetime.utcnow(),
            package_hash=package.package_hash or package.calculate_hash(),
        )

    @staticmethod
    def _xml_escape(text: str) -> str:
        """Escape special XML characters."""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
