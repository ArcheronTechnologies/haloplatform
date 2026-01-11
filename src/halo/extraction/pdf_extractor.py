"""
PDF fallback extractor for Swedish annual reports.

When iXBRL is not available, extract directors from PDF by:
1. Finding signature pages using Swedish legal markers
2. Extracting names near role keywords
3. Parsing name/role associations

Lower confidence than XBRL but provides coverage for older filings.
"""

import logging
import re
import time
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import pymupdf  # PyMuPDF

from .models import ExtractedDirector, ExtractionResult

logger = logging.getLogger(__name__)


# Role normalization mapping (same as xbrl_extractor)
ROLE_MAPPINGS = {
    "verkställande direktör": "VD",
    "vd": "VD",
    "vice verkställande direktör": "VICE_VD",
    "vice vd": "VICE_VD",
    "styrelseordförande": "STYRELSEORDFORANDE",
    "styrelsens ordförande": "STYRELSEORDFORANDE",
    "ordförande": "STYRELSEORDFORANDE",
    "styrelseledamot": "STYRELSELEDAMOT",
    "ledamot": "STYRELSELEDAMOT",
    "styrelsesuppleant": "STYRELSESUPPLEANT",
    "suppleant": "STYRELSESUPPLEANT",
    "arbetstagarrepresentant": "ARBETSTAGARREPRESENTANT",
    "extern ledamot": "EXTERN_LEDAMOT",
}


def normalize_role(role: str) -> str:
    """Normalize a Swedish role string to standard format."""
    role_lower = role.lower().strip()
    return ROLE_MAPPINGS.get(role_lower, "UNKNOWN")


class PDFExtractor:
    """
    Extract directors from PDF annual reports.

    Looks for signature pages and extracts name/role pairs.
    """

    # Markers that indicate signature page
    SIGNATURE_MARKERS = [
        r"undertecknas?\s+med",
        r"underskrift",
        r"undertecknad",
        r"årsredovisningen\s+har\s+undertecknats",
        r"styrelsen\s+och\s+verkställande",
        r"ort\s+och\s+datum",
        r"har\s+avgetts",
    ]

    # Sections to skip (not signature pages)
    SKIP_SECTIONS = [
        "revisionsberättelse",
        "bolagsstyrningsrapport",
        "revisors yttrande",
        "granskning av",
    ]

    # Role patterns with Swedish keywords
    ROLE_PATTERNS = {
        "VD": [
            r"verkställande\s+direktör",
            r"\bv\.?d\.?\b",
            r"chief\s+executive",
            r"\bceo\b",
        ],
        "Styrelseordförande": [
            r"styrelseordförande",
            r"styrelsens\s+ordförande",
            r"ordförande",
            r"chairman",
        ],
        "Styrelseledamot": [
            r"styrelseledamot",
            r"ledamot(?!\s*suppleant)",
            r"board\s+member",
        ],
        "Styrelsesuppleant": [
            r"styrelsesuppleant",
            r"suppleant",
            r"alternate",
        ],
        "Vice VD": [
            r"vice\s+verkställande\s+direktör",
            r"vice\s+v\.?d\.?",
        ],
    }

    # Swedish name pattern - matches "Firstname Lastname" or "Firstname Middle Lastname"
    NAME_PATTERN = re.compile(
        r"""
        (?P<name>
            [A-ZÅÄÖÉ][a-zåäöéèü]+           # First name (capitalized)
            (?:[\s-]+[A-ZÅÄÖÉ][a-zåäöéèü]+)*  # Middle names/double surnames
        )
        """,
        re.VERBOSE | re.UNICODE
    )

    # Names to exclude (common false positives)
    EXCLUDE_NAMES = {
        "verkställande direktör", "styrelseordförande", "styrelseledamot",
        "styrelsesuppleant", "stockholm", "göteborg", "malmö", "uppsala",
        "örebro", "linköping", "västerås", "helsingborg", "norrköping",
        "revisionsberättelse", "den svenska", "enligt not", "på uppdrag",
        "auktoriserad revisor", "godkänd revisor", "registrerat revisionsbolag",
        "ernst young", "kpmg", "deloitte", "pwc", "grant thornton",
    }

    def __init__(self, min_confidence: float = 0.5):
        self.min_confidence = min_confidence

        # Compile signature pattern
        self.signature_pattern = re.compile(
            "|".join(self.SIGNATURE_MARKERS),
            re.IGNORECASE
        )

        # Compile role patterns
        self.role_regexes = {}
        for role, patterns in self.ROLE_PATTERNS.items():
            combined = "|".join(f"({p})" for p in patterns)
            self.role_regexes[role] = re.compile(combined, re.IGNORECASE)

    def extract_from_zip(
        self,
        zip_bytes: bytes,
        orgnr: str,
        document_id: str,
    ) -> ExtractionResult:
        """
        Extract directors from a ZIP file containing annual report.

        The ZIP may contain:
        - PDF file (årsredovisning.pdf or similar)
        - XHTML file (for iXBRL - not handled here)
        """
        start_time = time.time()
        result = ExtractionResult(
            orgnr=orgnr,
            document_id=document_id,
            extraction_method="pdf",
        )

        try:
            with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
                # Find PDF file in archive
                pdf_name = None
                for name in zf.namelist():
                    if name.lower().endswith(".pdf"):
                        pdf_name = name
                        break

                if not pdf_name:
                    result.warnings.append("No PDF file found in archive")
                    return result

                # Extract and process PDF
                pdf_bytes = zf.read(pdf_name)
                directors = self._extract_from_pdf(pdf_bytes)

                result.directors = directors
                result.extraction_confidence = self._calculate_confidence(directors)

        except zipfile.BadZipFile:
            # Try as raw PDF
            try:
                directors = self._extract_from_pdf(zip_bytes)
                result.directors = directors
                result.extraction_confidence = self._calculate_confidence(directors)
            except Exception as e:
                result.warnings.append(f"Failed to parse as PDF: {e}")
        except Exception as e:
            result.warnings.append(f"Extraction failed: {e}")
            logger.error(f"PDF extraction failed for {orgnr}: {e}")

        result.processing_time_ms = int((time.time() - start_time) * 1000)
        return result

    def _extract_from_pdf(self, pdf_bytes: bytes) -> list[ExtractedDirector]:
        """Extract directors from PDF bytes."""
        directors = []

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

        try:
            # Find signature pages
            signature_pages = self._find_signature_pages(doc)

            if not signature_pages:
                # Fallback: use last 5 pages
                logger.debug("No signature pages found, using last pages as fallback")
                signature_pages = list(range(max(0, len(doc) - 5), len(doc)))

            # Extract from signature pages
            for page_idx in signature_pages:
                page = doc[page_idx]
                text = page.get_text("text")
                page_directors = self._parse_directors(text)
                directors.extend(page_directors)

            # Deduplicate
            directors = self._deduplicate(directors)

        finally:
            doc.close()

        return directors

    def _find_signature_pages(self, doc) -> list[int]:
        """Find pages that likely contain board signatures."""
        signature_pages = []

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            text = page.get_text("text").lower()

            # Skip if it's clearly not a signature page
            if any(skip in text for skip in self.SKIP_SECTIONS):
                continue

            # Check for signature markers
            matches = self.signature_pattern.findall(text)
            if len(matches) >= 1:
                # Also check for role keywords as confirmation
                has_roles = any(
                    regex.search(text)
                    for regex in self.role_regexes.values()
                )
                if has_roles:
                    signature_pages.append(page_idx)

        return signature_pages

    def _parse_directors(self, text: str) -> list[ExtractedDirector]:
        """Parse director names and roles from page text."""
        directors = []
        lines = text.split("\n")

        # Find all role positions in text
        role_positions = []
        for line_idx, line in enumerate(lines):
            for role, regex in self.role_regexes.items():
                for match in regex.finditer(line):
                    role_positions.append({
                        "line_idx": line_idx,
                        "role": role,
                        "match_text": match.group(),
                    })

        # For each role, find nearby names
        for role_info in role_positions:
            line_idx = role_info["line_idx"]
            role = role_info["role"]

            # Search lines before and after the role
            search_range = range(
                max(0, line_idx - 2),
                min(len(lines), line_idx + 3)
            )

            for search_idx in search_range:
                line = lines[search_idx]
                names = self._extract_names(line)

                for name in names:
                    if len(name) < 4:
                        continue
                    if name.lower() in self.EXCLUDE_NAMES:
                        continue

                    # Calculate confidence based on distance
                    distance = abs(search_idx - line_idx)
                    confidence = 0.8 - (distance * 0.15)

                    if confidence >= self.min_confidence:
                        # Split name into first/last
                        parts = name.split()
                        if len(parts) >= 2:
                            first_name = parts[0]
                            last_name = " ".join(parts[1:])
                        else:
                            first_name = name
                            last_name = ""

                        directors.append(ExtractedDirector(
                            first_name=first_name,
                            last_name=last_name,
                            role=role,
                            role_normalized=normalize_role(role),
                            confidence=max(self.min_confidence, confidence),
                            source_field="pdf_signature_page",
                        ))

        return directors

    def _extract_names(self, text: str) -> list[str]:
        """Extract potential person names from text."""
        names = []

        # Find capitalized word sequences that look like names
        for match in self.NAME_PATTERN.finditer(text):
            name = match.group("name").strip()
            parts = name.split()

            # Must have at least 2 parts (first + last name)
            if len(parts) >= 2:
                # Filter out obvious non-names
                if not any(p.lower() in self.EXCLUDE_NAMES for p in parts):
                    names.append(name)

        return names

    def _deduplicate(
        self, directors: list[ExtractedDirector]
    ) -> list[ExtractedDirector]:
        """Remove duplicate directors, keeping highest confidence."""
        seen: dict[str, ExtractedDirector] = {}

        for d in directors:
            key = d.name_normalized
            if key not in seen or d.confidence > seen[key].confidence:
                seen[key] = d

        return list(seen.values())

    def _calculate_confidence(
        self, directors: list[ExtractedDirector]
    ) -> float:
        """Calculate overall extraction confidence."""
        if not directors:
            return 0.0

        # Base confidence on:
        # 1. Number of directors found (expect 2-10)
        # 2. Whether we found VD
        # 3. Whether we found ordförande
        # 4. Average individual confidence

        count_score = min(1.0, len(directors) / 3)  # 3+ directors = full score
        has_vd = any(d.role_normalized == "VD" for d in directors)
        has_ordf = any(d.role_normalized == "STYRELSEORDFORANDE" for d in directors)
        avg_confidence = sum(d.confidence for d in directors) / len(directors)

        role_score = 0.5 + (0.25 if has_vd else 0) + (0.25 if has_ordf else 0)

        return (count_score * 0.3 + role_score * 0.3 + avg_confidence * 0.4)
