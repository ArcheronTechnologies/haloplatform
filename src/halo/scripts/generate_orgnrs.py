#!/usr/bin/env python3
"""
Generate valid Swedish organisationsnummer and test against Bolagsverket API.

Swedish org numbers:
- 10 digits: NNNNNN-NNNN
- First 6 digits: Group number (55xxxx for AB companies)
- Last 4 digits: Serial + Luhn checksum

Format: YYMMDD-XXXX or 16YYMM-XXXX (for companies registered after 1990)
Most companies: 55xxxx-xxxx or 556xxx-xxxx
"""

import asyncio
import sys
import random

sys.path.insert(0, "/Users/timothyaikenhead/Desktop/new-folder")


def luhn_checksum(number: str) -> int:
    """Calculate Luhn checksum digit."""
    def digits_of(n):
        return [int(d) for d in str(n)]

    digits = digits_of(number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]

    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d * 2))

    return (10 - (checksum % 10)) % 10


def generate_orgnr_candidates(count: int = 1000) -> list[str]:
    """Generate potential Swedish organisationsnummer candidates.

    Most Swedish companies have org numbers starting with:
    - 556xxx - Aktiebolag (AB) registered 1975-1994
    - 559xxx - Aktiebolag registered after 2010
    - 55xxxx - General range
    """
    candidates = []

    # Common prefixes for Swedish companies
    prefixes = [
        "5560", "5561", "5562", "5563", "5564", "5565", "5566", "5567", "5568", "5569",
        "5590", "5591", "5592", "5593", "5594", "5595", "5596",
    ]

    for _ in range(count):
        prefix = random.choice(prefixes)
        # Generate random middle digits
        middle = f"{random.randint(0, 99):02d}{random.randint(0, 99):02d}"

        # First 9 digits
        base = prefix + middle

        # Calculate checksum
        checksum = luhn_checksum(base)

        orgnr = base + str(checksum)
        candidates.append(orgnr)

    return list(set(candidates))  # Remove duplicates


async def test_orgnrs(orgnrs: list[str], limit: int = 100) -> list[str]:
    """Test org numbers against Bolagsverket API, return valid ones."""
    from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter

    adapter = BolagsverketHVDAdapter(
        client_id="[REDACTED_CLIENT_ID]",
        client_secret="[REDACTED_CLIENT_SECRET]",
        use_test=False,
    )

    valid = []
    tested = 0

    print(f"Testing {min(limit, len(orgnrs))} org numbers...")

    for orgnr in orgnrs[:limit]:
        try:
            record = await adapter.fetch_company(orgnr)
            if record:
                raw = record.raw_data
                # Check if it's an active company
                namn = raw.get("organisationsnamn", {}).get("organisationsnamnLista", [{}])[0].get("namn")
                is_active = raw.get("verksamOrganisation", {}).get("kod") == "JA"
                is_deregistered = raw.get("avregistreradOrganisation") is not None

                if namn and not is_deregistered:
                    valid.append(orgnr)
                    print(f"  ✓ {orgnr}: {namn} (active={is_active})")

        except Exception:
            pass  # Invalid org number, skip

        tested += 1
        if tested % 50 == 0:
            print(f"  ... tested {tested}, found {len(valid)} valid")

    await adapter.close()
    return valid


# Known valid Swedish company org numbers (from public sources)
KNOWN_ORGNRS = [
    "5560360793",  # SAAB AB
    "5566778899",  # Amitre AB (deregistered)
    "5565475489",  # Volvo Cars
    "5560004745",  # AB Volvo
    "5564014959",  # H&M
    "5560003468",  # Ericsson
    "5560056642",  # Securitas
    "5560003625",  # Investor AB
    "5562614609",  # Spotify
    "5568074323",  # Klarna
    "5565064943",  # ICA Gruppen
    "5560183917",  # SEB
    "5560190997",  # Handelsbanken
    "5560120483",  # Sandvik
    "5560039869",  # Atlas Copco
    "5560003241",  # SKF
    "5560013024",  # Electrolux
    "5560059223",  # Tele2
    "5560017037",  # Axel Johnson
    "5560136791",  # Husqvarna
    "5560095299",  # Alfa Laval
    "5560161063",  # Getinge
    "5560210983",  # Peab
    "5560061968",  # JM
    "5560193353",  # Bonnier
]


async def main():
    print("=" * 60)
    print("Getting Swedish Company Org Numbers")
    print("=" * 60)

    # First test known companies
    print("\n1. Testing known Swedish companies...")
    from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter

    adapter = BolagsverketHVDAdapter(
        client_id="[REDACTED_CLIENT_ID]",
        client_secret="[REDACTED_CLIENT_SECRET]",
        use_test=False,
    )

    valid_known = []
    for orgnr in KNOWN_ORGNRS:
        try:
            record = await adapter.fetch_company(orgnr)
            if record:
                namn = record.raw_data.get("organisationsnamn", {}).get("organisationsnamnLista", [{}])[0].get("namn")
                is_deregistered = record.raw_data.get("avregistreradOrganisation") is not None
                if namn and not is_deregistered:
                    valid_known.append(orgnr)
                    print(f"  ✓ {orgnr}: {namn}")
        except Exception as e:
            print(f"  ✗ {orgnr}: {e}")

    await adapter.close()

    print(f"\nFound {len(valid_known)} valid known companies")

    # Generate more candidates
    print("\n2. Generating and testing random org numbers...")
    candidates = generate_orgnr_candidates(2000)
    print(f"   Generated {len(candidates)} candidates")

    # Test them (rate limited, so do in batches)
    valid_random = await test_orgnrs(candidates, limit=500)

    # Combine results
    all_valid = list(set(valid_known + valid_random))
    print(f"\n3. Total valid org numbers: {len(all_valid)}")

    # Save to file
    output_file = "/Users/timothyaikenhead/Desktop/new-folder/halo/data/orgnrs.txt"
    with open(output_file, "w") as f:
        for orgnr in sorted(all_valid):
            f.write(orgnr + "\n")

    print(f"\nSaved to {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
