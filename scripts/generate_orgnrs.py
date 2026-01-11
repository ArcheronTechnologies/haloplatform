#!/usr/bin/env python3
"""
Generate valid Swedish org numbers for demo.

Swedish org numbers use Luhn checksum (mod 10).
Format: XXXXXX-XXXX (10 digits, dash optional)

559xxx range = companies registered ~2016+
"""

import random
import json
from pathlib import Path


def luhn_checksum(digits: list[int]) -> int:
    """Calculate Luhn checksum digit."""
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 0:  # Even positions (0-indexed) are doubled
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - (total % 10)) % 10


def generate_orgnr(prefix: str) -> str:
    """Generate a valid org number with given prefix."""
    # Org number is 10 digits: XXXXXX-XXXX
    # First 6 digits often follow patterns, last 4 include checksum

    prefix_digits = [int(d) for d in prefix]
    remaining = 9 - len(prefix_digits)  # Need 9 digits before checksum

    # Generate random middle digits
    middle = [random.randint(0, 9) for _ in range(remaining)]

    # Combine and calculate checksum
    base = prefix_digits + middle
    check = luhn_checksum(base)

    return "".join(str(d) for d in base) + str(check)


def validate_orgnr(orgnr: str) -> bool:
    """Validate org number checksum."""
    orgnr = orgnr.replace("-", "").replace(" ", "")
    if len(orgnr) != 10 or not orgnr.isdigit():
        return False

    digits = [int(d) for d in orgnr[:9]]
    expected_check = luhn_checksum(digits)
    return int(orgnr[9]) == expected_check


def main():
    orgnrs = set()

    # Known working org numbers from our tests
    known_working = [
        "5592584386",  # Avado AB - confirmed has documents
        "5560360793",  # SAAB
        "5565475489",  # Mölnlycke Health Care
        "5560006538",  # Volvo AB
        "5564649860",  # From earlier tests
    ]
    orgnrs.update(known_working)

    # Generate 559xxx range (newer companies, more likely to have iXBRL)
    print("Generating 559xxx org numbers...")
    for prefix in ["5590", "5591", "5592", "5593", "5594", "5595", "5596", "5597", "5598", "5599"]:
        for _ in range(100):  # 100 per prefix = 1000 total
            orgnr = generate_orgnr(prefix)
            if validate_orgnr(orgnr):
                orgnrs.add(orgnr)

    # Also generate some 556xxx (older companies, established)
    print("Generating 556xxx org numbers...")
    for prefix in ["5560", "5561", "5562", "5563", "5564", "5565", "5566", "5567", "5568", "5569"]:
        for _ in range(20):  # 20 per prefix = 200 total
            orgnr = generate_orgnr(prefix)
            if validate_orgnr(orgnr):
                orgnrs.add(orgnr)

    orgnrs_list = sorted(list(orgnrs))

    print(f"\nGenerated {len(orgnrs_list)} unique valid org numbers")
    print(f"  559xxx range: {len([o for o in orgnrs_list if o.startswith('559')])}")
    print(f"  556xxx range: {len([o for o in orgnrs_list if o.startswith('556')])}")

    # Validate a few
    print("\nValidation check:")
    for orgnr in orgnrs_list[:5]:
        print(f"  {orgnr}: valid={validate_orgnr(orgnr)}")

    # Save to file
    output_path = Path(__file__).parent.parent / "data" / "orgnrs_demo.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(orgnrs_list, f, indent=2)

    print(f"\nSaved to {output_path}")

    return orgnrs_list


if __name__ == "__main__":
    main()
