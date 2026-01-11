"""
XBRL extractor for Swedish annual reports (årsredovisningar).

Swedish annual reports filed digitally use iXBRL (inline XBRL) format,
which embeds structured data in XHTML. This extractor parses the XBRL
tags to extract director and board member information.

Key XBRL namespaces used:
- se-comp-base: Bolagsverket company base taxonomy
- se-gen-base: General base taxonomy

Key fields for directors:
- UnderskriftFaststallelseintygForetradareTilltalsnamn: First name
- UnderskriftFaststallelseintygForetradareEfternamn: Last name
- UnderskriftFaststallelseintygForetradareForetradarroll: Role
- UnderskriftHandlingTilltalsnamn: First name (alternate)
- UnderskriftHandlingEfternamn: Last name (alternate)
"""

import logging
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Optional
from xml.etree import ElementTree as ET

from .models import ExtractedDirector, ExtractedAuditor, ExtractionResult

logger = logging.getLogger(__name__)


# Role normalization mapping
ROLE_MAPPINGS = {
    # VD variants
    "verkställande direktör": "VD",
    "vd": "VD",
    "vice verkställande direktör": "VICE_VD",
    "vice vd": "VICE_VD",
    # Board chair
    "styrelseordförande": "STYRELSEORDFORANDE",
    "styrelsens ordförande": "STYRELSEORDFORANDE",
    "ordförande": "STYRELSEORDFORANDE",
    # Board members
    "styrelseledamot": "STYRELSELEDAMOT",
    "ledamot": "STYRELSELEDAMOT",
    # Alternates
    "styrelsesuppleant": "STYRELSESUPPLEANT",
    "suppleant": "STYRELSESUPPLEANT",
    # Other
    "arbetstagarrepresentant": "ARBETSTAGARREPRESENTANT",
    "extern ledamot": "EXTERN_LEDAMOT",
    # Auditors (handled separately but good to normalize)
    "auktoriserad revisor": "AUKTORISERAD_REVISOR",
    "godkänd revisor": "GODKAND_REVISOR",
    "huvudansvarig revisor": "HUVUDANSVARIG_REVISOR",
    "revisor": "REVISOR",
}


@dataclass
class XBRLField:
    """Represents an extracted XBRL field."""

    name: str  # Full XBRL field name
    value: str  # Field value
    context_ref: Optional[str] = None  # Context reference for grouping


class XBRLExtractor:
    """
    Extract directors from iXBRL annual reports.

    The extractor parses the XBRL tags embedded in the XHTML document
    and extracts structured director information.
    """

    # XBRL namespaces we care about
    NAMESPACES = {
        "ix": "http://www.xbrl.org/2013/inlineXBRL",
        "se-comp-base": "http://www.bolagsverket.se/se/fr/comp-base/2020-12-01",
        "se-gen-base": "http://www.taxonomier.se/se/fr/gen-base/2021-10-31",
        "xbrli": "http://www.xbrl.org/2003/instance",
    }

    # Field patterns for director extraction
    FIRST_NAME_PATTERNS = [
        "UnderskriftFaststallelseintygForetradareTilltalsnamn",
        "UnderskriftHandlingTilltalsnamn",
        "ForetradareTilltalsnamn",
        "Tilltalsnamn",
    ]

    LAST_NAME_PATTERNS = [
        "UnderskriftFaststallelseintygForetradareEfternamn",
        "UnderskriftHandlingEfternamn",
        "ForetradareEfternamn",
        "Efternamn",
    ]

    ROLE_PATTERNS = [
        "UnderskriftFaststallelseintygForetradareForetradarroll",
        "UnderskriftHandlingForetradarroll",
        "ForetradareForetradarroll",
        "Foretradarroll",
    ]

    DATE_PATTERNS = [
        "UnderskriftFastallelseintygDatum",
        "UnderskriftDatum",
        "UndertecknandeDatum",
    ]

    def __init__(self, min_confidence: float = 0.5):
        """
        Initialize the extractor.

        Args:
            min_confidence: Minimum confidence score to include a director
        """
        self.min_confidence = min_confidence

    def extract_from_zip(
        self, zip_bytes: bytes, orgnr: str, document_id: str
    ) -> ExtractionResult:
        """
        Extract directors from a ZIP file containing an annual report.

        Args:
            zip_bytes: ZIP file bytes from Bolagsverket API
            orgnr: Organization number
            document_id: Document ID from Bolagsverket

        Returns:
            ExtractionResult with extracted directors
        """
        start_time = time.time()
        result = ExtractionResult(orgnr=orgnr, document_id=document_id)

        try:
            with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
                # Find the XHTML file
                xhtml_files = [
                    n for n in zf.namelist() if n.endswith((".xhtml", ".html", ".xml"))
                ]

                if not xhtml_files:
                    result.warnings.append("No XHTML/XML file found in ZIP")
                    return result

                # Read the first XHTML file
                xhtml_content = zf.read(xhtml_files[0]).decode("utf-8")

        except zipfile.BadZipFile as e:
            result.warnings.append(f"Invalid ZIP file: {e}")
            return result
        except Exception as e:
            result.warnings.append(f"Failed to read ZIP: {e}")
            return result

        # Extract from XHTML content
        return self.extract_from_xhtml(xhtml_content, orgnr, document_id, start_time)

    def extract_from_xhtml(
        self,
        xhtml_content: str,
        orgnr: str,
        document_id: str,
        start_time: Optional[float] = None,
    ) -> ExtractionResult:
        """
        Extract directors from XHTML content.

        Args:
            xhtml_content: XHTML content string
            orgnr: Organization number
            document_id: Document ID

        Returns:
            ExtractionResult with extracted directors
        """
        if start_time is None:
            start_time = time.time()

        result = ExtractionResult(orgnr=orgnr, document_id=document_id)

        # Extract all XBRL fields
        fields = self._extract_xbrl_fields(xhtml_content)

        if not fields:
            result.warnings.append("No XBRL fields found in document")
            # Try regex fallback
            directors = self._extract_directors_regex(xhtml_content)
            result.directors = directors
        else:
            # Extract directors from XBRL fields
            result.directors = self._extract_directors_from_fields(fields)

            # Extract signature date
            result.signature_date = self._extract_date(fields)

        # Calculate confidence
        result.extraction_confidence = self._calculate_confidence(result)

        # Filter by confidence
        result.directors = [
            d for d in result.directors if d.confidence >= self.min_confidence
        ]

        # Deduplicate
        result.directors = self._deduplicate_directors(result.directors)

        result.processing_time_ms = int((time.time() - start_time) * 1000)

        return result

    def _extract_xbrl_fields(self, xhtml_content: str) -> list[XBRLField]:
        """Extract all relevant XBRL fields from the document."""
        fields = []

        try:
            root = ET.fromstring(xhtml_content.encode("utf-8"))

            # Iterate through all elements
            for elem in root.iter():
                # Check for ix:nonNumeric elements (text fields)
                if "nonNumeric" in elem.tag:
                    name = elem.get("name", "")
                    text = "".join(elem.itertext()).strip()
                    context_ref = elem.get("contextRef")

                    if name and text:
                        fields.append(
                            XBRLField(name=name, value=text, context_ref=context_ref)
                        )

        except ET.ParseError as e:
            logger.warning(f"XML parse error, falling back to regex: {e}")
            # Fall back to regex extraction
            fields = self._extract_fields_regex(xhtml_content)

        return fields

    def _extract_fields_regex(self, xhtml_content: str) -> list[XBRLField]:
        """Fallback: extract XBRL fields using regex."""
        fields = []

        # Pattern to match ix:nonNumeric elements
        pattern = r'<ix:nonNumeric[^>]*name="([^"]+)"[^>]*>([^<]+)</ix:nonNumeric>'

        for match in re.finditer(pattern, xhtml_content, re.IGNORECASE):
            name = match.group(1)
            value = match.group(2).strip()
            if name and value:
                fields.append(XBRLField(name=name, value=value))

        return fields

    def _extract_directors_from_fields(
        self, fields: list[XBRLField]
    ) -> list[ExtractedDirector]:
        """Extract director information from XBRL fields."""
        directors = []

        # Group fields that might be related
        first_names = []
        last_names = []
        roles = []

        for field in fields:
            field_name = field.name.split(":")[-1]  # Remove namespace prefix

            if any(p in field_name for p in self.FIRST_NAME_PATTERNS):
                first_names.append(field)
            elif any(p in field_name for p in self.LAST_NAME_PATTERNS):
                last_names.append(field)
            elif any(p in field_name for p in self.ROLE_PATTERNS):
                roles.append(field)

        # Match first names with last names and roles
        # Assume they appear in order
        for i, first_name_field in enumerate(first_names):
            first_name = first_name_field.value

            # Find corresponding last name
            last_name = ""
            if i < len(last_names):
                last_name = last_names[i].value

            # Find corresponding role
            role = "unknown"
            role_normalized = "UNKNOWN"
            if i < len(roles):
                role = roles[i].value
                role_normalized = self._normalize_role(role)

            # Skip if no meaningful data
            if not first_name or (not last_name and not role):
                continue

            # Skip auditors (handle separately)
            if "REVISOR" in role_normalized:
                continue

            confidence = self._calculate_director_confidence(
                first_name, last_name, role
            )

            directors.append(
                ExtractedDirector(
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                    role_normalized=role_normalized,
                    confidence=confidence,
                    source_field=first_name_field.name,
                )
            )

        return directors

    def _extract_directors_regex(self, xhtml_content: str) -> list[ExtractedDirector]:
        """Fallback: extract directors using regex patterns."""
        directors = []

        # Pattern: Name, Role (Swedish format)
        pattern = r">([A-ZÅÄÖ][a-zåäöéè]+(?:\s+[A-ZÅÄÖ][a-zåäöéè]+){1,3})\s*,?\s*(Styrelse(?:ledamot|ns ordförande|suppleant)?|VD|Verkställande direktör)[^<]*<"

        for match in re.finditer(pattern, xhtml_content, re.IGNORECASE):
            full_name = match.group(1).strip()
            role = match.group(2).strip()

            # Split name
            parts = full_name.split()
            first_name = parts[0] if parts else ""
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

            role_normalized = self._normalize_role(role)

            directors.append(
                ExtractedDirector(
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                    role_normalized=role_normalized,
                    confidence=0.6,  # Lower confidence for regex extraction
                    source_field="regex",
                )
            )

        return directors

    def _extract_date(self, fields: list[XBRLField]) -> Optional[date]:
        """Extract signature date from fields."""
        for field in fields:
            field_name = field.name.split(":")[-1]

            if any(p in field_name for p in self.DATE_PATTERNS):
                try:
                    # Try ISO format first
                    return date.fromisoformat(field.value)
                except ValueError:
                    # Try Swedish format
                    try:
                        # Format: "4 oktober 2024"
                        months = {
                            "januari": 1,
                            "februari": 2,
                            "mars": 3,
                            "april": 4,
                            "maj": 5,
                            "juni": 6,
                            "juli": 7,
                            "augusti": 8,
                            "september": 9,
                            "oktober": 10,
                            "november": 11,
                            "december": 12,
                        }
                        match = re.search(
                            r"(\d{1,2})\s+(\w+)\s+(\d{4})",
                            field.value,
                            re.IGNORECASE,
                        )
                        if match:
                            day = int(match.group(1))
                            month = months.get(match.group(2).lower(), 1)
                            year = int(match.group(3))
                            return date(year, month, day)
                    except (ValueError, KeyError):
                        pass

        return None

    def _normalize_role(self, role: str) -> str:
        """Normalize a Swedish role to a standard code."""
        role_lower = role.lower().strip()

        # Check exact matches first
        if role_lower in ROLE_MAPPINGS:
            return ROLE_MAPPINGS[role_lower]

        # Check partial matches
        for pattern, normalized in ROLE_MAPPINGS.items():
            if pattern in role_lower:
                return normalized

        return "UNKNOWN"

    def _calculate_director_confidence(
        self, first_name: str, last_name: str, role: str
    ) -> float:
        """Calculate confidence score for an extracted director."""
        confidence = 0.5  # Base confidence

        # Has both first and last name
        if first_name and last_name:
            confidence += 0.25

        # Has a recognized role
        if self._normalize_role(role) != "UNKNOWN":
            confidence += 0.2

        # Name looks valid (starts with uppercase, reasonable length)
        if first_name and first_name[0].isupper() and len(first_name) >= 2:
            confidence += 0.05

        return min(confidence, 1.0)

    def _calculate_confidence(self, result: ExtractionResult) -> float:
        """Calculate overall extraction confidence."""
        if not result.directors:
            return 0.0

        # Average director confidence
        avg = sum(d.confidence for d in result.directors) / len(result.directors)

        # Bonus for expected roles
        roles = {d.role_normalized for d in result.directors}
        if "VD" in roles:
            avg += 0.1
        if "STYRELSEORDFORANDE" in roles:
            avg += 0.1
        if "STYRELSELEDAMOT" in roles:
            avg += 0.05

        # Penalty for too few directors
        if len(result.directors) < 2:
            avg *= 0.8

        # Penalty for too many (likely errors)
        if len(result.directors) > 15:
            avg *= 0.7

        return min(avg, 1.0)

    def _deduplicate_directors(
        self, directors: list[ExtractedDirector]
    ) -> list[ExtractedDirector]:
        """Remove duplicate directors, keeping highest confidence."""
        seen = {}
        for d in directors:
            key = d.name_normalized
            if key not in seen or d.confidence > seen[key].confidence:
                seen[key] = d
        return list(seen.values())
