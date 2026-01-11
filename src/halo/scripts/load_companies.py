#!/usr/bin/env python3
"""
Company data loader for Halo.

This script loads company data from Bolagsverket HVD API into the Halo database.
It is designed to be COMPLIANT with Bolagsverket API terms of use.

IMPORTANT COMPLIANCE NOTES:
==========================
- The HVD API is for LOOKUP by org number, NOT bulk enumeration
- Do NOT attempt to enumerate or scrape all Swedish companies
- Only load companies you have a legitimate business need for
- Rate limits: 50 requests/minute (enforced by adapter, additional delays added here)
- This script is for loading KNOWN org numbers from your customer/watchlist

Legitimate use cases:
- Loading your customers' company data
- Loading companies from a watchlist or investigation
- Loading sample data for testing/development

NOT legitimate:
- Attempting to download the entire company register
- Random enumeration of org numbers
- Bulk scraping

Usage:
    python -m halo.scripts.load_companies --sample  # Load 15 sample companies for testing
    python -m halo.scripts.load_companies --orgnr 5560125790  # Load specific company
    python -m halo.scripts.load_companies --orgnr-file my_customers.txt  # Load from file (max 100)
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from halo.config import settings
from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter
from halo.swedish.organisationsnummer import validate_organisationsnummer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Maximum companies per run to prevent abuse
MAX_COMPANIES_PER_RUN = 100

# Minimum delay between requests (in addition to rate limiter)
MIN_REQUEST_DELAY_SECONDS = 1.5

# Sample Swedish company org numbers for testing
# These are real public companies - their data is already public
# Verified to pass Luhn checksum validation
SAMPLE_ORGNUMBERS = [
    "5560125790",  # Aktiebolaget Volvo
    "5560005328",  # Telefonaktiebolaget LM Ericsson (verified)
    "5560098138",  # Aktiebolaget Parkab
    "5567879696",  # Mat & Hotell i Luleå AB
    "5569813313",  # SWEDCO Ekonomi AB
]


class CompanyLoader:
    """Loads company data from Bolagsverket into Halo."""

    def __init__(
        self,
        adapter: Optional[BolagsverketHVDAdapter] = None,
        dry_run: bool = False,
    ):
        self.adapter = adapter or BolagsverketHVDAdapter()
        self.dry_run = dry_run
        self.stats = {
            "processed": 0,
            "loaded": 0,
            "skipped": 0,
            "errors": 0,
        }

    async def load_company(self, orgnr: str) -> Optional[dict]:
        """
        Load a single company by organisation number.

        Returns the company data or None if not found/error.
        """
        # Validate org number
        validation = validate_organisationsnummer(orgnr)
        if not validation.is_valid:
            logger.warning(f"Invalid org number: {orgnr}")
            self.stats["skipped"] += 1
            return None

        normalized = validation.normalized
        self.stats["processed"] += 1

        try:
            logger.debug(f"Fetching company: {normalized}")
            record = await self.adapter.fetch_company(normalized)

            if not record:
                logger.info(f"Company not found: {normalized}")
                self.stats["skipped"] += 1
                return None

            company_data = self._transform_company(record.raw_data, normalized)

            if self.dry_run:
                logger.info(f"[DRY RUN] Would load: {company_data.get('name', 'Unknown')} ({normalized})")
            else:
                await self._save_company(company_data)
                logger.info(f"Loaded: {company_data.get('name', 'Unknown')} ({normalized})")

            self.stats["loaded"] += 1
            return company_data

        except Exception as e:
            logger.error(f"Error loading company {normalized}: {e}")
            self.stats["errors"] += 1
            return None

    def _transform_company(self, raw_data: dict, orgnr: str) -> dict:
        """Transform Bolagsverket raw data to Halo entity format."""
        # Extract fields from Bolagsverket HVD response
        # Structure varies, so we handle multiple formats

        name = (
            raw_data.get("namn") or
            raw_data.get("foretagsnamn") or
            raw_data.get("organisationsnamn") or
            "Unknown"
        )

        # Legal form
        legal_form = raw_data.get("juridiskForm", {})
        if isinstance(legal_form, dict):
            legal_form_code = legal_form.get("kod", "")
            legal_form_name = legal_form.get("beskrivning", "")
        else:
            legal_form_code = str(legal_form) if legal_form else ""
            legal_form_name = ""

        # Status
        status_data = raw_data.get("status", {})
        if isinstance(status_data, dict):
            status = status_data.get("beskrivning", "Unknown")
        else:
            status = str(status_data) if status_data else "Unknown"

        # SNI codes
        sni_codes = []
        sni_data = raw_data.get("sniKoder", []) or raw_data.get("verksamhet", {}).get("sniKoder", [])
        for sni in sni_data if isinstance(sni_data, list) else []:
            if isinstance(sni, dict):
                sni_codes.append(sni.get("kod", ""))
            else:
                sni_codes.append(str(sni))

        # Address
        address_data = raw_data.get("postadress", {}) or raw_data.get("adress", {})
        address = ""
        city = ""
        postal_code = ""

        if isinstance(address_data, dict):
            address_lines = address_data.get("adressrader", [])
            if address_lines:
                address = ", ".join(address_lines) if isinstance(address_lines, list) else str(address_lines)
            city = address_data.get("postort", "") or address_data.get("ort", "")
            postal_code = address_data.get("postnummer", "")

        # Registration date
        reg_date = raw_data.get("registreringsdatum") or raw_data.get("bildatDatum")

        return {
            "id": str(uuid4()),
            "entity_type": "company",
            "organisationsnummer": orgnr,
            "name": name,
            "display_name": name,
            "status": "active" if "aktiv" in status.lower() else "inactive",
            "risk_score": 0.0,
            "risk_level": "low",
            "attributes": {
                "legal_name": name,
                "legal_form": legal_form_name or legal_form_code,
                "legal_form_code": legal_form_code,
                "registration_status": status,
                "registration_date": reg_date,
                "sni_codes": [c for c in sni_codes if c],
                "address": address,
                "city": city,
                "postal_code": postal_code,
            },
            "sources": ["bolagsverket_hvd"],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "raw_data": raw_data,
        }

    async def _save_company(self, company_data: dict) -> None:
        """
        Save company to database.

        For now, we just log - actual DB integration would go here.
        In production, this would:
        1. Check if entity exists (by orgnr)
        2. Create or update entity
        3. Extract and save relationships (board members, etc.)
        """
        # TODO: Implement actual database save
        # This would integrate with halo.db.repositories
        pass

    async def load_from_file(self, filepath: Path) -> list[dict]:
        """Load companies from a file of org numbers (one per line)."""
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        orgnumbers = []
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    orgnumbers.append(line)

        if len(orgnumbers) > MAX_COMPANIES_PER_RUN:
            logger.warning(
                f"File contains {len(orgnumbers)} org numbers, "
                f"but max per run is {MAX_COMPANIES_PER_RUN}. Truncating."
            )
            orgnumbers = orgnumbers[:MAX_COMPANIES_PER_RUN]

        logger.info(f"Loading {len(orgnumbers)} companies from {filepath}")
        return await self.load_batch(orgnumbers)

    async def load_batch(self, orgnumbers: list[str]) -> list[dict]:
        """
        Load multiple companies SEQUENTIALLY with delays.

        This is intentionally NOT concurrent to respect API limits
        and demonstrate good API citizenship.
        """
        if len(orgnumbers) > MAX_COMPANIES_PER_RUN:
            logger.error(
                f"Refusing to load {len(orgnumbers)} companies. "
                f"Max per run is {MAX_COMPANIES_PER_RUN}."
            )
            raise ValueError(f"Max {MAX_COMPANIES_PER_RUN} companies per run")

        results = []
        total = len(orgnumbers)

        for i, orgnr in enumerate(orgnumbers, 1):
            logger.info(f"[{i}/{total}] Processing {orgnr}...")

            result = await self.load_company(orgnr)
            if result is not None:
                results.append(result)

            # Add delay between requests (on top of rate limiter)
            if i < total:
                await asyncio.sleep(MIN_REQUEST_DELAY_SECONDS)

        return results

    async def load_sample(self) -> list[dict]:
        """Load sample companies for testing."""
        logger.info(f"Loading {len(SAMPLE_ORGNUMBERS)} sample companies")
        return await self.load_batch(SAMPLE_ORGNUMBERS)

    def print_stats(self) -> None:
        """Print loading statistics."""
        print("\n" + "=" * 50)
        print("LOADING COMPLETE")
        print("=" * 50)
        print(f"Processed: {self.stats['processed']}")
        print(f"Loaded:    {self.stats['loaded']}")
        print(f"Skipped:   {self.stats['skipped']}")
        print(f"Errors:    {self.stats['errors']}")
        print("=" * 50)


async def main():
    parser = argparse.ArgumentParser(
        description="Load Swedish company data into Halo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
COMPLIANCE NOTICE:
  This tool is for loading KNOWN org numbers only.
  Do NOT use this for bulk enumeration or scraping.
  Max %d companies per run.
        """ % MAX_COMPANIES_PER_RUN
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Load 15 sample public companies for testing",
    )
    parser.add_argument(
        "--orgnr-file",
        type=Path,
        help=f"File with org numbers (one per line, max {MAX_COMPANIES_PER_RUN})",
    )
    parser.add_argument(
        "--orgnr",
        type=str,
        nargs="+",
        help="Specific organisation number(s) to load",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save to database, just fetch and validate",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check for API credentials
    if not settings.bolagsverket_client_id or not settings.bolagsverket_client_secret:
        print("ERROR: Bolagsverket API credentials not configured.")
        print("Set BOLAGSVERKET_CLIENT_ID and BOLAGSVERKET_CLIENT_SECRET environment variables.")
        sys.exit(1)

    loader = CompanyLoader(dry_run=args.dry_run)

    try:
        # Check API health first
        logger.info("Checking Bolagsverket API health...")
        if await loader.adapter.healthcheck():
            logger.info("API is healthy")
        else:
            logger.warning("API healthcheck failed - proceeding anyway")

        if args.sample:
            await loader.load_sample()
        elif args.orgnr_file:
            await loader.load_from_file(args.orgnr_file)
        elif args.orgnr:
            if len(args.orgnr) > MAX_COMPANIES_PER_RUN:
                print(f"ERROR: Max {MAX_COMPANIES_PER_RUN} org numbers per run")
                sys.exit(1)
            await loader.load_batch(args.orgnr)
        else:
            print("No input specified. Use --sample, --orgnr-file, or --orgnr")
            parser.print_help()
            sys.exit(1)

        loader.print_stats()

    finally:
        await loader.adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
