#!/usr/bin/env python3
"""
Test Bolagsverket HVD API connection.

Tests:
1. OAuth2 token fetch
2. Health check endpoint
3. Single company lookup
"""

import asyncio
import sys

# Add project root to path
sys.path.insert(0, "/Users/timothyaikenhead/Desktop/new-folder")

from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter


async def main():
    # Initialize adapter with credentials from demo_goal.md
    adapter = BolagsverketHVDAdapter(
        client_id="AnQ27kXW8z4sdOMJHJuFJGf5AFIa",
        client_secret="L4bi0Wh_pDiMZ7GrKb9PYd1274oa",
        use_test=False,  # Use production API
    )

    print("=" * 60)
    print("Testing Bolagsverket HVD API")
    print("=" * 60)

    # Test 1: Health check
    print("\n1. Testing health check...")
    try:
        is_healthy = await adapter.healthcheck()
        print(f"   Health check: {'PASS' if is_healthy else 'FAIL'}")
    except Exception as e:
        print(f"   Health check FAILED: {e}")
        return

    # Test 2: Fetch a known company
    # Using IKEA (5566778899) as a test - large well-known Swedish company
    test_orgnrs = [
        "5566778899",  # Inter IKEA Systems B.V. (might not be in Swedish registry)
        "5560360793",  # Volvo AB
        "5021234567",  # Random test
        "5564866341",  # From demo_goal.md example
    ]

    print("\n2. Testing company lookups...")
    for orgnr in test_orgnrs:
        try:
            print(f"\n   Looking up: {orgnr}")
            record = await adapter.fetch_company(orgnr)

            if record:
                raw = record.raw_data
                print(f"   ✓ Found: {raw}")

                # Print key fields if available
                namn = raw.get("namn") or raw.get("organisationsnamn")
                if namn:
                    print(f"     Name: {namn}")

                juridisk = raw.get("juridiskForm") or raw.get("foretagsform")
                if juridisk:
                    print(f"     Legal form: {juridisk}")

                sni = raw.get("sniKod") or raw.get("sni")
                if sni:
                    print(f"     SNI: {sni}")
            else:
                print(f"   ✗ Not found")

        except Exception as e:
            print(f"   ✗ Error: {e}")

    # Test 3: List annual reports for a company
    print("\n3. Testing annual reports list...")
    try:
        reports = await adapter.list_annual_reports("5560360793")  # Volvo
        print(f"   Found {len(reports)} annual reports")
        for report in reports[:3]:
            print(f"     - {report}")
    except Exception as e:
        print(f"   Annual reports FAILED: {e}")

    # Cleanup
    await adapter.close()

    print("\n" + "=" * 60)
    print("Test complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
