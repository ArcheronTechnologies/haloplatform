#!/usr/bin/env python3
"""
Scan for valid Swedish org numbers around known valid ones.

Strategy: Start from known valid org numbers and scan sequentially.
Swedish org numbers follow patterns, so scanning nearby numbers should find more.
"""

import asyncio
import sys
import json
from datetime import datetime

sys.path.insert(0, "/Users/timothyaikenhead/Desktop/new-folder")


# These are VERIFIED WORKING with the API
SEED_ORGNRS = [
    "5560360793",  # SAAB AB - VERIFIED
    "5566778899",  # Amitre AB - VERIFIED (deregistered)
]


async def scan_range(adapter, base: str, count: int = 100) -> list[dict]:
    """Scan org numbers in a range around base."""
    results = []
    base_int = int(base)

    # Scan both directions
    for offset in range(-count, count + 1):
        orgnr = str(base_int + offset)

        # Pad to 10 digits
        orgnr = orgnr.zfill(10)

        try:
            record = await adapter.fetch_company(orgnr)
            if record:
                raw = record.raw_data

                # Extract key info
                namn_data = raw.get("organisationsnamn", {}).get("organisationsnamnLista", [])
                namn = namn_data[0].get("namn") if namn_data else None

                org_form = raw.get("organisationsform", {})
                legal_form = org_form.get("kod", "")

                sni_data = raw.get("naringsgrenOrganisation", {}).get("sni", [])
                sni_codes = [s.get("kod") for s in sni_data if s.get("kod")]

                addr = raw.get("postadressOrganisation", {}).get("postadress", {})

                is_active = raw.get("verksamOrganisation", {}).get("kod") == "JA"
                is_deregistered = raw.get("avregistreradOrganisation") is not None

                results.append({
                    "orgnr": orgnr,
                    "name": namn,
                    "legal_form": legal_form,
                    "sni_codes": sni_codes,
                    "city": addr.get("postort"),
                    "is_active": is_active,
                    "is_deregistered": is_deregistered,
                    "raw": raw,
                })

                status = "ACTIVE" if is_active else ("DEREGISTERED" if is_deregistered else "UNKNOWN")
                print(f"  ✓ {orgnr}: {namn} [{status}]")

        except Exception:
            pass  # Most will fail - that's expected

        # Progress indicator
        if (offset + count) % 50 == 0:
            print(f"    ... scanned {offset + count + 1} / {2 * count + 1}")

        # Rate limit - small delay
        await asyncio.sleep(0.1)

    return results


async def main():
    from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter

    print("=" * 60)
    print("Scanning for Swedish Companies")
    print("=" * 60)

    adapter = BolagsverketHVDAdapter(
        client_id="[REDACTED_CLIENT_ID]",
        client_secret="[REDACTED_CLIENT_SECRET]",
        use_test=False,
    )

    all_companies = []

    # Scan around each seed
    for seed in SEED_ORGNRS:
        print(f"\nScanning around {seed}...")
        results = await scan_range(adapter, seed, count=200)
        all_companies.extend(results)
        print(f"  Found {len(results)} companies in this range")

    # Also try some specific ranges known to have many companies
    # 556000xxxx is a common prefix
    print("\nScanning 5560000000 range...")
    results = await scan_range(adapter, "5560000000", count=500)
    all_companies.extend(results)

    await adapter.close()

    # Deduplicate
    seen = set()
    unique = []
    for c in all_companies:
        if c["orgnr"] not in seen:
            seen.add(c["orgnr"])
            unique.append(c)

    print(f"\n{'=' * 60}")
    print(f"Total unique companies found: {len(unique)}")
    print(f"Active: {sum(1 for c in unique if c['is_active'])}")
    print(f"Deregistered: {sum(1 for c in unique if c['is_deregistered'])}")

    # Save results
    output_file = "/Users/timothyaikenhead/Desktop/new-folder/halo/data/companies.json"
    with open(output_file, "w") as f:
        json.dump(unique, f, indent=2, default=str)
    print(f"\nSaved to {output_file}")

    # Also save just org numbers
    orgnr_file = "/Users/timothyaikenhead/Desktop/new-folder/halo/data/orgnrs.txt"
    with open(orgnr_file, "w") as f:
        for c in unique:
            if not c["is_deregistered"]:
                f.write(c["orgnr"] + "\n")
    print(f"Active orgnrs saved to {orgnr_file}")


if __name__ == "__main__":
    asyncio.run(main())
