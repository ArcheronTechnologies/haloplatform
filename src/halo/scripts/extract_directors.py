#!/usr/bin/env python3
"""
Director Extraction Pipeline - Test Implementation

Extracts board members and directors from Swedish annual reports (årsredovisningar)
using Bolagsverket HVD API based on extraction_spec.md.

Usage:
    python -m halo.scripts.extract_directors --sample
    python -m halo.scripts.extract_directors --orgnr 5560125790
"""

import asyncio
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pymupdf  # PyMuPDF for PDF extraction

from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Document:
    """Document metadata from dokumentlista endpoint."""
    document_id: str
    document_type: str
    fiscal_year_start: Optional[str] = None
    fiscal_year_end: Optional[str] = None


@dataclass
class ExtractedDirector:
    """Extracted director information."""
    name: str
    role: str
    confidence: float = 0.0


@dataclass
class ExtractionResult:
    """Result of processing a single company."""
    orgnr: str
    company_name: str = ""
    documents_found: int = 0
    documents_processed: int = 0
    directors: list[ExtractedDirector] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ============================================================================
# PDF Extractor
# ============================================================================

class PDFExtractor:
    """Extract text from Swedish annual report PDFs."""

    # Markers that indicate signature page
    SIGNATURE_MARKERS = [
        r"undertecknas?\s+med",
        r"underskrift",
        r"undertecknad",
        r"verkställande\s+direktör",
        r"styrelseordförande",
        r"styrelseledamot",
        r"styrelsesuppleant",
        r"ort.*datum",
        r"\d{4}-\d{2}-\d{2}",
        r"stockholm\s+den",
        r"göteborg\s+den",
        r"malmö\s+den",
    ]

    SKIP_SECTIONS = [
        "revisionsberättelse",
        "bolagsstyrningsrapport",
    ]

    def __init__(self):
        self.signature_pattern = re.compile(
            "|".join(self.SIGNATURE_MARKERS),
            re.IGNORECASE
        )

    def extract_text(self, pdf_bytes: bytes) -> list[tuple[int, str, bool]]:
        """
        Extract text from all pages.

        Returns list of (page_num, text, is_signature_page) tuples.
        """
        pages = []

        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                is_signature = self._is_signature_page(text)
                pages.append((page_num + 1, text, is_signature))

            doc.close()

        except Exception as e:
            logger.error(f"Failed to extract PDF: {e}")
            raise

        return pages

    def _is_signature_page(self, text: str) -> bool:
        """Check if page contains board signatures."""
        text_lower = text.lower()

        for skip in self.SKIP_SECTIONS:
            if skip in text_lower:
                return False

        matches = self.signature_pattern.findall(text_lower)
        return len(matches) >= 2

    def get_signature_pages(self, pdf_bytes: bytes) -> list[tuple[int, str]]:
        """Get only signature pages from PDF."""
        all_pages = self.extract_text(pdf_bytes)
        return [(num, text) for num, text, is_sig in all_pages if is_sig]

    def get_last_pages(self, pdf_bytes: bytes, n: int = 5) -> list[tuple[int, str]]:
        """Fallback: get last N pages."""
        all_pages = self.extract_text(pdf_bytes)
        last_n = all_pages[-n:] if len(all_pages) >= n else all_pages
        return [(num, text) for num, text, _ in last_n]


# ============================================================================
# Director Parser
# ============================================================================

class DirectorParser:
    """Parse Swedish annual report text to extract director names and roles."""

    ROLE_PATTERNS = {
        "VD": [
            r"verkställande\s+direktör",
            r"\bvd\b",
            r"chief\s+executive\s+officer",
            r"\bceo\b",
        ],
        "Styrelseordförande": [
            r"styrelseordförande",
            r"ordförande",
            r"chairman",
        ],
        "Styrelseledamot": [
            r"styrelseledamot",
            r"ledamot",
            r"board\s+member",
        ],
        "Styrelsesuppleant": [
            r"styrelsesuppleant",
            r"suppleant",
        ],
        "Vice VD": [
            r"vice\s+verkställande\s+direktör",
            r"vice\s+vd",
        ],
    }

    # Swedish name pattern
    NAME_PATTERN = re.compile(
        r"""
        (?P<name>
            [A-ZÅÄÖ][a-zåäöé]+           # First name
            (?:\s+[A-ZÅÄÖ][a-zåäöé]+)*   # Middle names
            \s+
            [A-ZÅÄÖ][a-zåäöé]+           # Last name
            (?:-[A-ZÅÄÖ][a-zåäöé]+)?     # Optional hyphenated surname
        )
        """,
        re.VERBOSE | re.UNICODE
    )

    EXCLUDE_NAMES = {
        "verkställande direktör",
        "styrelseordförande",
        "styrelseledamot",
        "styrelsesuppleant",
        "stockholm",
        "göteborg",
        "malmö",
        "revisionsberättelse",
        "den svenska",
        "enligt not",
    }

    def __init__(self):
        self.role_regexes = {}
        for role, patterns in self.ROLE_PATTERNS.items():
            combined = "|".join(f"({p})" for p in patterns)
            self.role_regexes[role] = re.compile(combined, re.IGNORECASE)

    def parse(self, text: str) -> list[ExtractedDirector]:
        """Extract directors from signature page text."""
        directors = []
        lines = text.split("\n")

        # Find all role positions
        role_positions = []

        for line_idx, line in enumerate(lines):
            for role, regex in self.role_regexes.items():
                for match in regex.finditer(line):
                    role_positions.append((line_idx, role, match.start(), match.end()))

        # Find names near roles
        for line_idx, role, _, _ in role_positions:
            search_range = range(max(0, line_idx - 2), min(len(lines), line_idx + 3))

            for search_idx in search_range:
                line = lines[search_idx]
                names = self._extract_names(line)

                for name in names:
                    if len(name) < 5:
                        continue
                    if name.lower() in self.EXCLUDE_NAMES:
                        continue

                    distance = abs(search_idx - line_idx)
                    confidence = 1.0 - (distance * 0.2)

                    directors.append(ExtractedDirector(
                        name=name,
                        role=role,
                        confidence=max(0.5, confidence)
                    ))

        return self._deduplicate(directors)

    def _extract_names(self, text: str) -> list[str]:
        """Extract potential person names from text."""
        names = []

        for match in self.NAME_PATTERN.finditer(text):
            name = match.group("name").strip()
            parts = name.split()
            if len(parts) >= 2:
                names.append(name)

        return names

    def _deduplicate(self, directors: list[ExtractedDirector]) -> list[ExtractedDirector]:
        """Remove duplicate directors, keeping highest confidence."""
        seen: dict[tuple[str, str], ExtractedDirector] = {}

        for d in directors:
            key = (d.name.lower(), d.role)
            if key not in seen or d.confidence > seen[key].confidence:
                seen[key] = d

        return list(seen.values())


# ============================================================================
# Main Pipeline
# ============================================================================

class DirectorExtractionPipeline:
    """Pipeline to extract directors from company annual reports."""

    def __init__(self, adapter: Optional[BolagsverketHVDAdapter] = None):
        self.adapter = adapter or BolagsverketHVDAdapter()
        self.pdf_extractor = PDFExtractor()
        self.director_parser = DirectorParser()
        self.stats = {
            "companies_processed": 0,
            "documents_found": 0,
            "documents_downloaded": 0,
            "directors_extracted": 0,
            "errors": 0,
        }

    async def process_company(self, orgnr: str) -> ExtractionResult:
        """Process a single company: get documents, download PDFs, extract directors."""
        start_time = time.monotonic()
        result = ExtractionResult(orgnr=orgnr)

        try:
            # Get company info first
            company_record = await self.adapter.fetch_company(orgnr)
            if company_record:
                raw = company_record.raw_data
                result.company_name = (
                    raw.get("namn") or
                    raw.get("foretagsnamn") or
                    raw.get("organisationsnamn") or
                    "Unknown"
                )

            # Get document list
            documents = await self.adapter.list_annual_reports(orgnr)
            result.documents_found = len(documents)
            self.stats["documents_found"] += len(documents)

            if not documents:
                logger.info(f"{orgnr}: No annual reports found")
                return result

            # Process each document (limit to most recent 2)
            for doc in documents[:2]:
                try:
                    directors = await self._process_document(orgnr, doc)
                    result.directors.extend(directors)
                    result.documents_processed += 1
                    self.stats["documents_downloaded"] += 1
                except Exception as e:
                    error_msg = f"Document {doc.get('dokumentId', 'unknown')}: {str(e)}"
                    result.errors.append(error_msg)
                    logger.error(f"{orgnr}: {error_msg}")
                    self.stats["errors"] += 1

            self.stats["directors_extracted"] += len(result.directors)

        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"{orgnr}: Failed to process company: {e}")
            self.stats["errors"] += 1

        result.elapsed_seconds = time.monotonic() - start_time
        self.stats["companies_processed"] += 1
        return result

    async def _process_document(
        self,
        orgnr: str,
        doc: dict[str, Any]
    ) -> list[ExtractedDirector]:
        """Download and process a single document."""
        doc_id = doc.get("dokumentId")
        if not doc_id:
            return []

        logger.debug(f"{orgnr}: Downloading document {doc_id}")

        # Download PDF
        pdf_bytes = await self.adapter.download_document(doc_id)

        # Extract signature pages
        signature_pages = self.pdf_extractor.get_signature_pages(pdf_bytes)

        if not signature_pages:
            # Fallback to last pages
            logger.debug(f"{orgnr}: No signature pages found, using last 3 pages")
            signature_pages = self.pdf_extractor.get_last_pages(pdf_bytes, n=3)

        # Parse directors from signature pages
        all_directors: list[ExtractedDirector] = []

        for page_num, text in signature_pages:
            directors = self.director_parser.parse(text)
            logger.debug(f"{orgnr}: Page {page_num} - found {len(directors)} directors")
            all_directors.extend(directors)

        # Deduplicate across pages
        seen: set[tuple[str, str]] = set()
        unique_directors: list[ExtractedDirector] = []

        for d in all_directors:
            key = (d.name.lower(), d.role)
            if key not in seen:
                seen.add(key)
                unique_directors.append(d)

        logger.info(
            f"{orgnr}: Extracted {len(unique_directors)} directors from {doc_id}"
        )
        return unique_directors

    async def process_batch(self, orgnrs: list[str]) -> list[ExtractionResult]:
        """Process multiple companies sequentially."""
        results = []
        total = len(orgnrs)

        for i, orgnr in enumerate(orgnrs, 1):
            logger.info(f"[{i}/{total}] Processing {orgnr}...")
            result = await self.process_company(orgnr)
            results.append(result)

            # Small delay between companies
            if i < total:
                await asyncio.sleep(0.5)

        return results

    def print_stats(self) -> None:
        """Print extraction statistics."""
        print("\n" + "=" * 60)
        print("EXTRACTION COMPLETE")
        print("=" * 60)
        print(f"Companies processed:    {self.stats['companies_processed']}")
        print(f"Documents found:        {self.stats['documents_found']}")
        print(f"Documents downloaded:   {self.stats['documents_downloaded']}")
        print(f"Directors extracted:    {self.stats['directors_extracted']}")
        print(f"Errors:                 {self.stats['errors']}")
        print("=" * 60)

    def print_results(self, results: list[ExtractionResult]) -> None:
        """Print detailed results."""
        print("\n" + "=" * 60)
        print("DETAILED RESULTS")
        print("=" * 60)

        for r in results:
            print(f"\n{r.orgnr} - {r.company_name}")
            print(f"  Documents: {r.documents_found} found, {r.documents_processed} processed")
            print(f"  Time: {r.elapsed_seconds:.2f}s")

            if r.directors:
                print(f"  Directors ({len(r.directors)}):")
                for d in r.directors:
                    print(f"    - {d.name} ({d.role}) [conf: {d.confidence:.2f}]")
            else:
                print("  No directors extracted")

            if r.errors:
                print(f"  Errors: {r.errors}")

    async def close(self) -> None:
        """Close the adapter."""
        await self.adapter.close()


# ============================================================================
# Sample Companies
# ============================================================================

SAMPLE_ORGNUMBERS = [
    "5560125790",  # Aktiebolaget Volvo
    "5560005328",  # Telefonaktiebolaget LM Ericsson
    "5560098138",  # Aktiebolaget Parkab
    "5567879696",  # Mat & Hotell i Luleå AB
    "5569813313",  # SWEDCO Ekonomi AB
]


# ============================================================================
# Main
# ============================================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract directors from Swedish annual reports"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Process sample companies for testing",
    )
    parser.add_argument(
        "--orgnr",
        type=str,
        nargs="+",
        help="Specific organisation number(s) to process",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine which companies to process
    if args.orgnr:
        orgnrs = args.orgnr
    elif args.sample:
        orgnrs = SAMPLE_ORGNUMBERS
    else:
        print("No input specified. Use --sample or --orgnr")
        parser.print_help()
        sys.exit(1)

    print(f"Processing {len(orgnrs)} companies...")

    pipeline = DirectorExtractionPipeline()

    try:
        # Health check
        logger.info("Checking API health...")
        if await pipeline.adapter.healthcheck():
            logger.info("API is healthy")
        else:
            logger.warning("API healthcheck failed")

        # Process companies
        start = time.monotonic()
        results = await pipeline.process_batch(orgnrs)
        total_time = time.monotonic() - start

        # Print results
        pipeline.print_results(results)
        pipeline.print_stats()

        print(f"\nTotal time: {total_time:.2f}s")
        print(f"Average per company: {total_time/len(orgnrs):.2f}s")

    finally:
        await pipeline.close()


if __name__ == "__main__":
    asyncio.run(main())
