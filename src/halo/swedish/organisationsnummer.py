"""
Swedish organisationsnummer (organization number) validation.

Format: NNNNNN-NNNN (10 digits)
- First digit: Organization type
  - 1: Estates of deceased persons
  - 2: State, county, municipality
  - 5: Partnerships (HB, KB)
  - 6: Limited partnerships
  - 7: Foundations, associations
  - 8: Foundations, associations
  - 9: Foreign companies, others
- Digits 3-4: >= 20 (to distinguish from personnummer)
- Last digit: Luhn checksum
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class OrganisationsnummerInfo:
    """Parsed organisationsnummer information."""

    normalized: str
    organization_type: str
    organization_type_code: str
    is_valid: bool


ORGANIZATION_TYPES = {
    "1": "Dödsbo (Estate of deceased)",
    "2": "Stat, landsting, kommun (Government)",
    "5": "Handelsbolag, kommanditbolag (Partnership)",
    "6": "Kommanditbolag (Limited partnership)",
    "7": "Ekonomisk förening, stiftelse (Foundation/Association)",
    "8": "Ideell förening, stiftelse (Non-profit/Foundation)",
    "9": "Utländskt företag m.fl. (Foreign company)",
}


def luhn_checksum(digits: str) -> int:
    """
    Calculate Luhn checksum digit.

    The Luhn algorithm:
    1. Double every second digit from the right
    2. If doubling results in > 9, subtract 9
    3. Sum all digits
    4. Checksum is (10 - (sum % 10)) % 10
    """
    total = 0
    for i, digit in enumerate(digits):
        d = int(digit)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - (total % 10)) % 10


def validate_organisationsnummer(orgnr: str) -> OrganisationsnummerInfo:
    """
    Validate a Swedish organisationsnummer.

    Accepts formats:
    - NNNNNN-NNNN
    - NNNNNNNNNN
    - 16NNNNNN-NNNN (with prefix)
    - 16NNNNNNNNNN (with prefix)

    Note: Limited companies (AB) often use 16XXXXXX-XXXX format where
    16 is the prefix. We strip this prefix if present.
    """
    # Remove whitespace and separators
    orgnr = re.sub(r"[\s\-]", "", orgnr)

    # Handle 16-prefix (sometimes used for display)
    if len(orgnr) == 12 and orgnr.startswith("16"):
        orgnr = orgnr[2:]

    # Validate format - must be exactly 10 digits
    if not re.match(r"^\d{10}$", orgnr):
        return OrganisationsnummerInfo(
            normalized="",
            organization_type="",
            organization_type_code="",
            is_valid=False,
        )

    # Check that digits 3-4 are >= 20 (distinguishes from personnummer)
    group_number = int(orgnr[2:4])
    if group_number < 20:
        return OrganisationsnummerInfo(
            normalized=orgnr,
            organization_type="",
            organization_type_code="",
            is_valid=False,
        )

    # Validate Luhn checksum
    check_digits = orgnr[:9]
    expected_checksum = luhn_checksum(check_digits)
    actual_checksum = int(orgnr[9])

    if actual_checksum != expected_checksum:
        return OrganisationsnummerInfo(
            normalized=orgnr,
            organization_type="",
            organization_type_code="",
            is_valid=False,
        )

    # Determine organization type
    org_type_code = orgnr[0]
    org_type = ORGANIZATION_TYPES.get(org_type_code, "Unknown")

    return OrganisationsnummerInfo(
        normalized=orgnr,
        organization_type=org_type,
        organization_type_code=org_type_code,
        is_valid=True,
    )


def format_organisationsnummer(orgnr: str, separator: str = "-") -> Optional[str]:
    """
    Format organisationsnummer as NNNNNN-NNNN.

    Args:
        orgnr: The organisationsnummer to format
        separator: The separator to use (default: '-')

    Returns:
        Formatted organisationsnummer or None if invalid
    """
    info = validate_organisationsnummer(orgnr)
    if not info.is_valid:
        return None
    return f"{info.normalized[:6]}{separator}{info.normalized[6:]}"


def format_with_prefix(orgnr: str, separator: str = "-") -> Optional[str]:
    """
    Format organisationsnummer with 16 prefix as 16NNNNNN-NNNN.

    This is the format commonly used by Swedish Tax Authority and banks.

    Args:
        orgnr: The organisationsnummer to format
        separator: The separator to use (default: '-')

    Returns:
        Formatted organisationsnummer with prefix or None if invalid
    """
    info = validate_organisationsnummer(orgnr)
    if not info.is_valid:
        return None
    return f"16{info.normalized[:6]}{separator}{info.normalized[6:]}"


def is_aktiebolag(orgnr: str) -> bool:
    """
    Check if the organisationsnummer belongs to an Aktiebolag (AB).

    Swedish limited companies (Aktiebolag) have:
    - First digit: 5 (most common)
    - Group number (digits 3-4): typically 56-99

    Args:
        orgnr: The organisationsnummer to check

    Returns:
        True if likely an AB, False otherwise
    """
    info = validate_organisationsnummer(orgnr)
    if not info.is_valid:
        return False

    # Most ABs start with 5
    if info.normalized[0] == "5":
        group_number = int(info.normalized[2:4])
        # Group numbers 56-99 are typically ABs
        return group_number >= 56

    return False


def generate_organisationsnummer(org_type: str = "5", group_number: int = 56) -> str:
    """
    Generate a valid organisationsnummer for testing purposes.

    Args:
        org_type: Organization type digit (default: '5' for partnerships/AB)
        group_number: Group number (20-99, default: 56 for AB)

    Returns:
        A valid organisationsnummer in NNNNNNNNNN format
    """
    if not 20 <= group_number <= 99:
        raise ValueError("Group number must be between 20 and 99")

    # Generate random middle digits
    import random

    middle = f"{random.randint(0, 99):02d}"

    # Build first 9 digits
    first_nine = f"{org_type}{random.randint(0, 9)}{group_number:02d}{middle}{random.randint(0, 999):03d}"

    # Calculate checksum
    checksum = luhn_checksum(first_nine)

    return f"{first_nine}{checksum}"
