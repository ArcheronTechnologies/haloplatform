#!/usr/bin/env python3
"""
Enumerate org numbers from SCB Företagsregistret.

This replaces random org number generation with actual enumeration
from the official Swedish company register (1.3M+ companies).

Output: List of org numbers ready for enrichment via allabolag scraper.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from halo.ingestion.scb_foretag import SCBForetagAdapter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TARGET_COMPANIES = 10000
BATCH_SIZE = 2000  # SCB max per request
RATE_LIMIT_DELAY = 1.0  # Seconds between batches (SCB: 10 req/10sec)


async def enumerate_companies(
    adapter: SCBForetagAdapter,
    target: int = TARGET_COMPANIES,
    only_active: bool = True,
    legal_form: str = None,
    start_offset: int = 0,
    existing_orgnrs: set = None,
) -> list[str]:
    """
    Enumerate org numbers from SCB.

    Args:
        adapter: SCB API adapter
        target: Number of NEW org numbers to fetch (not duplicates)
        only_active: Only fetch active companies
        legal_form: Filter by legal form (e.g., "49" for Aktiebolag)
        start_offset: Starting offset for pagination
        existing_orgnrs: Set of already-known org numbers to skip

    Returns:
        List of 10-digit org numbers (excluding duplicates)
    """
    org_numbers = []
    offset = start_offset
    existing = existing_orgnrs or set()

    # Get total available
    total_available = await adapter.count_companies(
        only_active=only_active,
        legal_form=legal_form
    )
    logger.info(f"Total available companies: {total_available:,}")

    logger.info(f"Fetching {target:,} new org numbers (starting from offset {offset})...")

    # We need to keep fetching until we have enough NEW org numbers
    while len(org_numbers) < target and offset < total_available:
        batch_size = BATCH_SIZE

        try:
            batch = await adapter.fetch_companies_batch(
                offset=offset,
                limit=batch_size,
                only_active=only_active,
                legal_form=legal_form,
            )

            if not batch:
                logger.warning(f"Empty batch at offset {offset}, stopping")
                break

            # Extract org numbers (convert from 12-digit to 10-digit)
            for record in batch:
                orgnr = record.raw_data.get("OrgNr", "")
                # SCB returns 12-digit (YYYYMMDDNNNN or 16NNNNNNNNNN)
                # We need 10-digit format
                if len(orgnr) == 12 and orgnr.startswith("16"):
                    orgnr = orgnr[2:]  # Remove "16" prefix
                elif len(orgnr) == 12:
                    orgnr = orgnr[2:]  # Remove birth year prefix for sole traders

                if len(orgnr) == 10 and orgnr.isdigit():
                    # Only add if not already known
                    if orgnr not in existing:
                        org_numbers.append(orgnr)

            offset += len(batch)

            # Progress
            if len(org_numbers) % 1000 == 0 or len(org_numbers) >= target:
                logger.info(f"Progress: {len(org_numbers):,}/{target:,} new found (offset {offset:,})")

            # Rate limiting
            await asyncio.sleep(RATE_LIMIT_DELAY)

        except Exception as e:
            logger.error(f"Error at offset {offset}: {e}")
            await asyncio.sleep(5)  # Wait and retry
            continue

    return org_numbers


async def main():
    print("=" * 70)
    print("SCB COMPANY ENUMERATION")
    print("=" * 70)

    # Initialize adapter with certificate
    cert_path = Path("data/[REDACTED_CERT]")
    cert_password = "[REDACTED_PASSWORD]"

    if not cert_path.exists():
        print(f"ERROR: Certificate not found at {cert_path}")
        return

    adapter = SCBForetagAdapter(
        cert_path=cert_path,
        cert_password=cert_password
    )

    try:
        # Test connection
        print("\nTesting SCB API connection...")
        if not await adapter.healthcheck():
            print("ERROR: SCB API not available")
            return
        print("Connection OK!")

        # Get total count
        total = await adapter.count_companies(only_active=True)
        print(f"\nTotal active companies in SCB: {total:,}")

        # Load existing org numbers to avoid duplicates
        existing_orgnrs = set()

        # Check extraction results
        results_path = Path("data/extraction_combined/results.json")
        if results_path.exists():
            with open(results_path) as f:
                existing = json.load(f)
            existing_orgnrs.update(c["orgnr"] for c in existing)
            print(f"Existing in database: {len(existing_orgnrs)}")

        # Check previously found org numbers
        new_batch_path = Path("data/orgnrs_new_batch.json")
        if new_batch_path.exists():
            with open(new_batch_path) as f:
                previous = json.load(f)
            existing_orgnrs.update(previous)
            print(f"Previously found: {len(previous)}")

        # Calculate how many we need
        have = len(existing_orgnrs)
        need = max(0, TARGET_COMPANIES - have)
        print(f"\nCurrent total: {have}")
        print(f"Target: {TARGET_COMPANIES}")
        print(f"Need: {need}")

        if need == 0:
            print("\nAlready have enough org numbers!")
            return

        # Enumerate from SCB
        print(f"\n[1/2] Enumerating {need} org numbers from SCB...")

        # Load the last offset we used (to continue from there)
        offset_file = Path("data/scb_offset.json")
        start_offset = 0
        if offset_file.exists():
            with open(offset_file) as f:
                start_offset = json.load(f).get("offset", 0)
            print(f"Resuming from offset: {start_offset}")

        # Focus on Aktiebolag (legal form 49) - most likely to have useful data
        org_numbers = await enumerate_companies(
            adapter,
            target=need,
            only_active=True,
            legal_form="49",  # Aktiebolag
            start_offset=start_offset,
            existing_orgnrs=existing_orgnrs,
        )

        # Save the offset for next run
        with open(offset_file, "w") as f:
            json.dump({"offset": start_offset + len(org_numbers) * 2}, f)  # Approximate

        print(f"\nFetched {len(org_numbers)} org numbers from SCB")

        # Remove duplicates with existing
        new_orgnrs = [o for o in org_numbers if o not in existing_orgnrs]
        print(f"New (not already in system): {len(new_orgnrs)}")

        # Take what we need
        final_orgnrs = new_orgnrs[:need]

        # Save results
        print(f"\n[2/2] Saving {len(final_orgnrs)} org numbers...")

        output_path = Path("data/orgnrs_scb.json")
        with open(output_path, "w") as f:
            json.dump(final_orgnrs, f, indent=2)
        print(f"Saved to {output_path}")

        # Also update the combined batch file
        combined = list(existing_orgnrs) + final_orgnrs
        combined = list(set(combined))  # Dedupe

        with open(new_batch_path, "w") as f:
            json.dump(combined, f, indent=2)
        print(f"Updated {new_batch_path} with {len(combined)} total org numbers")

        # Summary
        print(f"\n{'=' * 70}")
        print("SUMMARY")
        print(f"{'=' * 70}")
        print(f"Existing: {have}")
        print(f"New from SCB: {len(final_orgnrs)}")
        print(f"Total: {len(combined)}")
        print(f"Target: {TARGET_COMPANIES}")

        if len(combined) >= TARGET_COMPANIES:
            print(f"\nTARGET REACHED!")
        else:
            print(f"\nNeed {TARGET_COMPANIES - len(combined)} more")

        print(f"\n{'=' * 70}")
        print("Next steps:")
        print("1. Feed org numbers to allabolag scraper for enrichment")
        print("2. Run load_and_analyze.py to rebuild graph")
        print(f"{'=' * 70}")

    finally:
        await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
