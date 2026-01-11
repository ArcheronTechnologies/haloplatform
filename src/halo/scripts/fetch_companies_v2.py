#!/usr/bin/env python3
"""
Fetch Swedish companies using properly validated org numbers.

Swedish organisationsnummer structure (10 digits):
- Digit 1: Group number (5 = Aktiebolag, 8 = Ideell förening, etc.)
- Digits 2-3: Part of birth century/grouping
- Digit 4-9: Sequential number
- Digit 10: Luhn checksum (calculated on digits 2-9)

The Luhn checksum for Swedish org numbers:
- Take digits 2-9 (8 digits)
- From the right, double every second digit
- Sum all digits (if doubled value > 9, sum its digits)
- Checksum = (10 - (sum mod 10)) mod 10
"""

import asyncio
import sys
import json
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/Users/timothyaikenhead/Desktop/new-folder")


def luhn_validate(number_str: str) -> bool:
    """Validate a number using standard Luhn algorithm."""
    digits = [int(d) for d in number_str]
    odd_sum = sum(digits[-1::-2])  # Every other digit from the right (including last)
    even_sum = sum(sum(divmod(2 * d, 10)) for d in digits[-2::-2])  # Double and sum digits
    return (odd_sum + even_sum) % 10 == 0


def luhn_checksum(base_9: str) -> int:
    """Calculate Luhn checksum digit for a 9-digit base."""
    # Standard Luhn: we need to find check digit that makes full number valid
    # For 9 digits, append 0-9 and find which passes
    for check in range(10):
        if luhn_validate(base_9 + str(check)):
            return check
    return 0


def validate_orgnr(orgnr: str) -> bool:
    """Validate a Swedish organisationsnummer using standard Luhn."""
    orgnr = orgnr.replace("-", "").replace(" ", "")
    if len(orgnr) != 10:
        return False
    if not orgnr.isdigit():
        return False
    return luhn_validate(orgnr)


def generate_valid_orgnr(prefix_9: str) -> str:
    """Generate a valid 10-digit org number from a 9-digit prefix."""
    check = luhn_checksum(prefix_9)
    return prefix_9 + str(check)


# Test the validation
assert validate_orgnr("5560360793"), "SAAB should be valid"


# Known working org numbers (verified against API)
VERIFIED_ORGNRS = [
    "5560360793",  # SAAB Aktiebolag
    "5566778899",  # Amitre AB (deregistered but exists)
]

# Generate valid org numbers in 556 range (Aktiebolag)
def generate_orgnr_batch(prefix_4: str, start: int, end: int) -> list[str]:
    """Generate batch of valid org numbers for a 4-digit prefix."""
    valid = []
    for i in range(start, end):
        # Build 9-digit base: prefix (4 digits) + running (5 digits)
        running = str(i).zfill(5)
        base_9 = prefix_4 + running

        # Generate valid orgnr with correct checksum
        orgnr = generate_valid_orgnr(base_9)
        valid.append(orgnr)

    return valid


async def fetch_with_retry(adapter, orgnr: str, retries: int = 2) -> dict | None:
    """Fetch company with retries on network errors."""
    for attempt in range(retries):
        try:
            record = await adapter.fetch_company(orgnr)
            if record:
                raw = record.raw_data

                namn_data = raw.get("organisationsnamn", {}).get("organisationsnamnLista", [])
                namn = namn_data[0].get("namn") if namn_data else None

                org_form = raw.get("organisationsform", {})
                legal_form = org_form.get("kod", "")

                sni_data = raw.get("naringsgrenOrganisation", {}).get("sni", [])
                sni_codes = [s.get("kod") for s in sni_data if s.get("kod")]

                addr = raw.get("postadressOrganisation", {}).get("postadress") or {}

                is_active = raw.get("verksamOrganisation", {}).get("kod") == "JA"
                is_deregistered = raw.get("avregistreradOrganisation") is not None

                return {
                    "orgnr": orgnr,
                    "name": namn,
                    "legal_form": legal_form,
                    "sni_codes": sni_codes,
                    "city": addr.get("postort"),
                    "is_active": is_active,
                    "is_deregistered": is_deregistered,
                    "raw": raw,
                }
            return None
        except Exception as e:
            if "400" in str(e) or "404" in str(e):
                return None
            if attempt < retries - 1:
                await asyncio.sleep(0.5)
                continue
            raise
    return None


async def main():
    from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter

    print("=" * 60)
    print("Fetching Swedish Companies from Bolagsverket")
    print("Strategy: Generate Luhn-valid org numbers and probe API")
    print("=" * 60)

    adapter = BolagsverketHVDAdapter(
        client_id="AnQ27kXW8z4sdOMJHJuFJGf5AFIa",
        client_secret="L4bi0Wh_pDiMZ7GrKb9PYd1274oa",
        use_test=False,
    )

    all_companies = []
    target = 1000

    # First, test with known working ones
    print(f"\n1. Testing {len(VERIFIED_ORGNRS)} verified org numbers...")
    for orgnr in VERIFIED_ORGNRS:
        result = await fetch_with_retry(adapter, orgnr)
        if result:
            all_companies.append(result)
            print(f"   ✓ {orgnr}: {result['name']}")

    print(f"   Found: {len(all_companies)} verified companies")

    # Generate and scan 556 range (Aktiebolag - limited companies)
    # Focus on ranges that are more likely to be populated
    ranges_to_scan = [
        # Older company ranges (more likely to exist)
        ("5560", 0, 10000),      # 556000xxxxx
        ("5561", 0, 10000),      # 556100xxxxx
        ("5562", 0, 5000),       # 556200xxxxx
        ("5563", 0, 5000),       # 556300xxxxx
        ("5564", 0, 5000),       # 556400xxxxx
        ("5565", 0, 5000),       # 556500xxxxx
        ("5566", 0, 5000),       # 556600xxxxx
        ("5567", 0, 3000),       # 556700xxxxx
        ("5568", 0, 3000),       # 556800xxxxx
        ("5569", 0, 3000),       # 556900xxxxx
    ]

    print(f"\n2. Scanning Luhn-valid org numbers in 556x ranges...")

    for prefix, start, end in ranges_to_scan:
        if len(all_companies) >= target:
            break

        batch = generate_orgnr_batch(prefix, start, end)
        print(f"   Scanning {prefix}xxxxx ({len(batch)} candidates)...")

        found_in_range = 0
        for i, orgnr in enumerate(batch):
            if len(all_companies) >= target:
                break

            # Skip duplicates
            if any(c["orgnr"] == orgnr for c in all_companies):
                continue

            result = await fetch_with_retry(adapter, orgnr)
            if result:
                all_companies.append(result)
                found_in_range += 1
                status = "ACTIVE" if result["is_active"] else "DEREGISTERED"
                print(f"      ✓ {orgnr}: {result['name']} [{status}]")

            # Progress every 500
            if (i + 1) % 500 == 0:
                print(f"      ... {i+1}/{len(batch)}, found {found_in_range} in range, total {len(all_companies)}")

            # Small delay
            await asyncio.sleep(0.02)

        print(f"   Range {prefix}: found {found_in_range} companies")

    await adapter.close()

    # Report
    print(f"\n{'=' * 60}")
    print(f"Total companies found: {len(all_companies)}")
    print(f"Active: {sum(1 for c in all_companies if c['is_active'])}")
    print(f"Deregistered: {sum(1 for c in all_companies if c['is_deregistered'])}")

    # Save results
    data_dir = Path("/Users/timothyaikenhead/Desktop/new-folder/halo/data")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Slim version (no raw data)
    slim_file = data_dir / "companies.json"
    slim = [{k: v for k, v in c.items() if k != "raw"} for c in all_companies]
    with open(slim_file, "w") as f:
        json.dump(slim, f, indent=2, default=str)
    print(f"\nSlim data saved to {slim_file}")

    # Full version
    full_file = data_dir / "companies_full.json"
    with open(full_file, "w") as f:
        json.dump(all_companies, f, indent=2, default=str)
    print(f"Full data saved to {full_file}")

    # Just org numbers (active)
    orgnr_file = data_dir / "orgnrs.txt"
    with open(orgnr_file, "w") as f:
        for c in all_companies:
            if not c["is_deregistered"]:
                f.write(c["orgnr"] + "\n")
    print(f"Active orgnrs saved to {orgnr_file}")


if __name__ == "__main__":
    asyncio.run(main())
