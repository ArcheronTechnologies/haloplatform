"""
Swedish personnummer (personal identity number) validation and parsing.

Format: YYMMDD-XXXX or YYYYMMDD-XXXX
- First 6/8 digits: birth date
- 7th-9th digits: birth number (odd for male, even for female)
- 10th digit: Luhn checksum

Coordination numbers (samordningsnummer) add 60 to the day.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class PersonnummerInfo:
    """Parsed personnummer information."""

    normalized: str  # 12-digit format: YYYYMMDDXXXX
    birth_date: date
    gender: str  # 'M' or 'F'
    is_coordination: bool  # True if samordningsnummer
    is_valid: bool


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


def validate_personnummer(pnr: str) -> PersonnummerInfo:
    """
    Validate and parse a Swedish personnummer.

    Accepts formats:
    - YYMMDD-XXXX
    - YYMMDDXXXX
    - YYYYMMDD-XXXX
    - YYYYMMDDXXXX

    Also handles:
    - '+' separator for people over 100 years old
    - Coordination numbers (samordningsnummer) where day is +60

    Returns PersonnummerInfo with validation result and parsed data.
    """
    # Store original for error reporting
    original = pnr

    # Check for '+' separator (indicates person over 100)
    is_over_100 = "+" in pnr

    # Remove whitespace and common separators
    pnr = re.sub(r"[\s\-\+]", "", pnr)

    # Validate format - must be 10 or 12 digits
    if not re.match(r"^\d{10,12}$", pnr):
        return PersonnummerInfo(
            normalized="",
            birth_date=date(1900, 1, 1),
            gender="",
            is_coordination=False,
            is_valid=False,
        )

    # Normalize to 12 digits
    if len(pnr) == 10:
        # Determine century
        year_short = int(pnr[:2])
        current_year = date.today().year % 100

        # Standard rule: 00-current = 2000s, otherwise 1900s
        if year_short <= current_year:
            century = "20"
        else:
            century = "19"

        if is_over_100:
            # '+' means born more than 100 years ago
            # Go back one century from the normal interpretation
            century = "19" if century == "20" else "18"

        pnr = century + pnr

    # Extract components
    year = int(pnr[:4])
    month = int(pnr[4:6])
    day = int(pnr[6:8])
    birth_number = pnr[8:11]
    checksum = int(pnr[11])

    # Check for coordination number (day + 60)
    is_coordination = day > 60
    if is_coordination:
        day -= 60

    # Validate date
    try:
        birth_date = date(year, month, day)

        # Check that birth date is not in the future
        if birth_date > date.today():
            return PersonnummerInfo(
                normalized=pnr,
                birth_date=birth_date,
                gender="",
                is_coordination=is_coordination,
                is_valid=False,
            )
    except ValueError:
        return PersonnummerInfo(
            normalized=pnr,
            birth_date=date(1900, 1, 1),
            gender="",
            is_coordination=is_coordination,
            is_valid=False,
        )

    # Validate Luhn checksum (on 10-digit format: YYMMDDXXX)
    check_digits = pnr[2:11]  # Skip century, include 9 digits
    expected_checksum = luhn_checksum(check_digits)

    if checksum != expected_checksum:
        return PersonnummerInfo(
            normalized=pnr,
            birth_date=birth_date,
            gender="M" if int(birth_number[2]) % 2 == 1 else "F",
            is_coordination=is_coordination,
            is_valid=False,
        )

    # Determine gender (9th digit: odd = male, even = female)
    gender = "M" if int(birth_number[2]) % 2 == 1 else "F"

    return PersonnummerInfo(
        normalized=pnr,
        birth_date=birth_date,
        gender=gender,
        is_coordination=is_coordination,
        is_valid=True,
    )


def format_personnummer(pnr: str, separator: str = "-") -> Optional[str]:
    """
    Format personnummer as YYYYMMDD-XXXX.

    Args:
        pnr: The personnummer to format
        separator: The separator to use (default: '-')

    Returns:
        Formatted personnummer or None if invalid
    """
    info = validate_personnummer(pnr)
    if not info.is_valid:
        return None
    return f"{info.normalized[:8]}{separator}{info.normalized[8:]}"


def generate_personnummer(
    birth_date: date, gender: str = "M", birth_number: int = 1
) -> str:
    """
    Generate a valid personnummer for testing purposes.

    Args:
        birth_date: Date of birth
        gender: 'M' for male, 'F' for female
        birth_number: Birth number (1-999)

    Returns:
        A valid personnummer in YYYYMMDDXXXX format
    """
    # Format date part
    date_part = birth_date.strftime("%Y%m%d")

    # Adjust birth number for gender (odd for male, even for female)
    if gender == "M" and birth_number % 2 == 0:
        birth_number += 1
    elif gender == "F" and birth_number % 2 == 1:
        birth_number += 1

    birth_str = f"{birth_number:03d}"

    # Calculate checksum on 10-digit format
    check_digits = date_part[2:] + birth_str
    checksum = luhn_checksum(check_digits)

    return f"{date_part}{birth_str}{checksum}"
