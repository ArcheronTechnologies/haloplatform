"""
Swedish address parsing and normalization utilities.

Handles parsing of Swedish addresses including:
- Street addresses (Storgatan 12, Kungsgatan 5A)
- Postal codes (postnummer) - 5 digits
- Cities (postort)
- C/O addresses
- Box addresses

Swedish postal codes are managed by PostNord and follow a geographic structure:
- First 2 digits: Region
- Last 3 digits: Local area
"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class SwedishAddress:
    """Parsed Swedish address components."""

    street: Optional[str] = None
    street_number: Optional[str] = None
    floor: Optional[str] = None  # e.g., "2 tr" (2nd floor)
    apartment: Optional[str] = None  # e.g., "lgh 1201"
    co_name: Optional[str] = None  # C/O name
    box_number: Optional[str] = None  # Box/PO Box number
    postal_code: Optional[str] = None  # 5 digits, no space
    city: Optional[str] = None
    municipality: Optional[str] = None
    raw_input: str = ""

    @property
    def formatted_postal_code(self) -> Optional[str]:
        """Return postal code formatted with space (XXX XX)."""
        if self.postal_code and len(self.postal_code) == 5:
            return f"{self.postal_code[:3]} {self.postal_code[3:]}"
        return self.postal_code

    @property
    def street_address(self) -> Optional[str]:
        """Return formatted street address."""
        if not self.street:
            return None
        parts = [self.street]
        if self.street_number:
            parts.append(self.street_number)
        if self.floor:
            parts.append(self.floor)
        if self.apartment:
            parts.append(self.apartment)
        return " ".join(parts)

    @property
    def full_address(self) -> str:
        """Return full formatted address."""
        lines = []
        if self.co_name:
            lines.append(f"c/o {self.co_name}")
        if self.box_number:
            lines.append(f"Box {self.box_number}")
        elif self.street_address:
            lines.append(self.street_address)
        if self.postal_code and self.city:
            lines.append(f"{self.formatted_postal_code} {self.city}")
        return ", ".join(lines)

    def normalized_key(self) -> str:
        """Return normalized key for deduplication."""
        parts = []
        if self.street:
            parts.append(normalize_street_name(self.street).lower())
        if self.street_number:
            parts.append(self.street_number.lower())
        if self.postal_code:
            parts.append(self.postal_code)
        if self.city:
            parts.append(normalize_city_name(self.city).lower())
        return "|".join(parts)


# Common Swedish street suffixes
STREET_SUFFIXES = [
    "gatan", "vägen", "gränd", "stigen", "torget", "platsen", "allén",
    "backen", "backe", "kullen", "höjden", "ängen", "parken", "plan",
    "bron", "kajen", "stranden", "udden", "holmen", "berget",
]

# Patterns for address parsing
PATTERNS = {
    # Postal code: 5 digits, optionally with space after 3rd digit
    "postal_code": re.compile(r"(\d{3})\s?(\d{2})"),
    # Street number with optional letter/apartment, e.g., "12", "12A", "12 A", "12-14"
    "street_number": re.compile(r"(\d+(?:\s?[A-Za-z])?(?:-\d+)?)\s*$"),
    # Floor indicator: "1 tr", "2:a tr", "3e tr", "bv" (bottenvåning)
    "floor": re.compile(r"(\d+(?::?[ae])?\s*tr\.?|bv\.?)(?:\s|$)", re.IGNORECASE),
    # Apartment: "lgh 1201", "lägenhet 5"
    "apartment": re.compile(r"(l(?:gh|ägenhet)\s*\d+)", re.IGNORECASE),
    # C/O line
    "co": re.compile(r"c/?o\s+(.+?)(?:,|\n|$)", re.IGNORECASE),
    # Box/PO Box
    "box": re.compile(r"(?:post)?box\s+(\d+)", re.IGNORECASE),
}

# Swedish postal code regions (first 2 digits)
POSTAL_REGIONS = {
    "10": "Stockholm",
    "11": "Stockholm",
    "12": "Stockholm",
    "13": "Stockholm",
    "14": "Stockholm",
    "15": "Stockholm",
    "16": "Stockholm",
    "17": "Stockholm",
    "18": "Stockholm",
    "19": "Stockholm",
    "20": "Malmö",
    "21": "Malmö",
    "22": "Lund",
    "23": "Skåne",
    "24": "Skåne",
    "25": "Skåne",
    "26": "Skåne",
    "27": "Skåne",
    "28": "Skåne",
    "29": "Skåne",
    "30": "Halland",
    "31": "Halland",
    "40": "Göteborg",
    "41": "Göteborg",
    "42": "Göteborg",
    "43": "Göteborg",
    "44": "Västra Götaland",
    "45": "Västra Götaland",
    "50": "Västra Götaland",
    "51": "Västra Götaland",
    "52": "Västra Götaland",
    "53": "Västra Götaland",
    "54": "Västra Götaland",
    "55": "Östergötland",
    "56": "Östergötland",
    "57": "Östergötland",
    "58": "Östergötland",
    "59": "Östergötland",
    "60": "Östergötland",
    "61": "Östergötland",
    "62": "Jönköping",
    "63": "Jönköping",
    "64": "Jönköping",
    "65": "Kronoberg",
    "66": "Kronoberg",
    "67": "Kalmar",
    "68": "Kalmar",
    "69": "Gotland",
    "70": "Örebro",
    "71": "Örebro",
    "72": "Västmanland",
    "73": "Västmanland",
    "74": "Uppsala",
    "75": "Uppsala",
    "76": "Uppsala",
    "77": "Uppsala",
    "78": "Dalarna",
    "79": "Dalarna",
    "80": "Gävleborg",
    "81": "Gävleborg",
    "82": "Gävleborg",
    "83": "Gävleborg",
    "84": "Västernorrland",
    "85": "Västernorrland",
    "86": "Västernorrland",
    "87": "Västernorrland",
    "88": "Jämtland",
    "89": "Jämtland",
    "90": "Västerbotten",
    "91": "Västerbotten",
    "92": "Västerbotten",
    "93": "Norrbotten",
    "94": "Norrbotten",
    "95": "Norrbotten",
    "96": "Norrbotten",
    "97": "Norrbotten",
    "98": "Norrbotten",
}

# Common city name normalizations
CITY_NORMALIZATIONS = {
    "gbg": "Göteborg",
    "götheborg": "Göteborg",
    "sthlm": "Stockholm",
    "malmö c": "Malmö",
    "malmö centrum": "Malmö",
}


def validate_postal_code(postal_code: str) -> bool:
    """
    Validate a Swedish postal code.

    Args:
        postal_code: String to validate (with or without space)

    Returns:
        True if valid Swedish postal code format
    """
    # Remove spaces and check length
    clean = postal_code.replace(" ", "")
    if not clean.isdigit() or len(clean) != 5:
        return False

    # Check first digit is not 0
    if clean[0] == "0":
        return False

    return True


def normalize_postal_code(postal_code: str) -> Optional[str]:
    """
    Normalize a postal code to 5 digits without space.

    Args:
        postal_code: Input postal code string

    Returns:
        5-digit postal code or None if invalid
    """
    if not postal_code:
        return None

    clean = postal_code.replace(" ", "").replace("-", "")
    if validate_postal_code(clean):
        return clean
    return None


def normalize_street_name(street: str) -> str:
    """
    Normalize a Swedish street name.

    - Capitalizes first letter of each word
    - Handles common abbreviations
    - Removes extra whitespace
    """
    if not street:
        return ""

    # Common abbreviations
    replacements = {
        "g.": "gatan",
        "v.": "vägen",
        "gr.": "gränd",
        "pl.": "plan",
        "st.": "stigen",
        "alle": "allén",
    }

    normalized = street.strip()

    # Apply replacements
    for abbrev, full in replacements.items():
        if normalized.lower().endswith(abbrev):
            normalized = normalized[: -len(abbrev)] + full

    # Title case, but keep internal words like "på" lowercase
    words = normalized.split()
    result = []
    for i, word in enumerate(words):
        if i == 0 or word.lower() not in ["på", "i", "av", "vid"]:
            result.append(word.capitalize())
        else:
            result.append(word.lower())

    return " ".join(result)


def normalize_city_name(city: str) -> str:
    """
    Normalize a Swedish city name.

    Handles common abbreviations and variations.
    """
    if not city:
        return ""

    normalized = city.strip().lower()

    # Check for known normalizations
    if normalized in CITY_NORMALIZATIONS:
        return CITY_NORMALIZATIONS[normalized]

    # Title case
    return city.strip().title()


def get_region_from_postal_code(postal_code: str) -> Optional[str]:
    """
    Get the region/län from a postal code.

    Args:
        postal_code: 5-digit postal code

    Returns:
        Region name or None if unknown
    """
    clean = normalize_postal_code(postal_code)
    if not clean:
        return None

    prefix = clean[:2]
    return POSTAL_REGIONS.get(prefix)


def parse_address(address_text: str) -> SwedishAddress:
    """
    Parse a Swedish address string into components.

    Handles various formats:
    - "Storgatan 12, 123 45 Stockholm"
    - "c/o Andersson, Kungsgatan 5, 111 22 Stockholm"
    - "Box 1234, 123 45 Malmö"

    Args:
        address_text: Raw address string

    Returns:
        SwedishAddress with parsed components
    """
    result = SwedishAddress(raw_input=address_text)

    if not address_text:
        return result

    text = address_text.strip()

    # Extract C/O
    co_match = PATTERNS["co"].search(text)
    if co_match:
        result.co_name = co_match.group(1).strip()
        text = PATTERNS["co"].sub("", text)

    # Extract Box number
    box_match = PATTERNS["box"].search(text)
    if box_match:
        result.box_number = box_match.group(1)
        text = PATTERNS["box"].sub("", text)

    # Extract postal code
    postal_match = PATTERNS["postal_code"].search(text)
    if postal_match:
        result.postal_code = postal_match.group(1) + postal_match.group(2)
        # City is typically after postal code
        after_postal = text[postal_match.end() :].strip()
        if after_postal:
            # Take first word/phrase as city (up to comma or end)
            city_part = after_postal.split(",")[0].strip()
            result.city = normalize_city_name(city_part)
        text = text[: postal_match.start()].strip()

    # Extract floor
    floor_match = PATTERNS["floor"].search(text)
    if floor_match:
        result.floor = floor_match.group(1).strip()
        text = PATTERNS["floor"].sub("", text)

    # Extract apartment
    apt_match = PATTERNS["apartment"].search(text)
    if apt_match:
        result.apartment = apt_match.group(1).strip()
        text = PATTERNS["apartment"].sub("", text)

    # Clean up remaining text - should be street address
    text = re.sub(r"[,\n]+", " ", text).strip()
    text = re.sub(r"\s+", " ", text)

    if text and not result.box_number:
        # Try to extract street number from end
        number_match = PATTERNS["street_number"].search(text)
        if number_match:
            result.street_number = number_match.group(1).strip()
            text = text[: number_match.start()].strip()

        if text:
            result.street = normalize_street_name(text)

    # Try to determine municipality from postal code
    if result.postal_code:
        result.municipality = get_region_from_postal_code(result.postal_code)

    return result


def extract_addresses_from_text(text: str) -> list[SwedishAddress]:
    """
    Extract multiple Swedish addresses from a text block.

    Looks for patterns that might be addresses and attempts to parse them.

    Args:
        text: Text that may contain addresses

    Returns:
        List of parsed SwedishAddress objects
    """
    addresses = []

    # Split on common separators that might delimit addresses
    # but only if they contain postal code patterns
    postal_pattern = re.compile(r"\d{3}\s?\d{2}")
    potential_addresses = re.split(r"(?:;|\n{2,}|•|\|)", text)

    for chunk in potential_addresses:
        chunk = chunk.strip()
        if postal_pattern.search(chunk):
            addr = parse_address(chunk)
            if addr.postal_code:  # Only include if we found a postal code
                addresses.append(addr)

    return addresses


def is_swedish_address(text: str) -> bool:
    """
    Check if a text string appears to be a Swedish address.

    Args:
        text: String to check

    Returns:
        True if it looks like a Swedish address
    """
    if not text:
        return False

    # Must have a valid Swedish postal code
    postal_match = PATTERNS["postal_code"].search(text)
    if not postal_match:
        return False

    postal = postal_match.group(1) + postal_match.group(2)
    return validate_postal_code(postal)


def addresses_match(addr1: SwedishAddress, addr2: SwedishAddress, fuzzy: bool = False) -> bool:
    """
    Check if two addresses refer to the same location.

    Args:
        addr1: First address
        addr2: Second address
        fuzzy: If True, allow fuzzy matching

    Returns:
        True if addresses match
    """
    # Postal code must match exactly
    if addr1.postal_code != addr2.postal_code:
        return False

    # If both have streets, they must match
    if addr1.street and addr2.street:
        street1 = normalize_street_name(addr1.street).lower()
        street2 = normalize_street_name(addr2.street).lower()
        if street1 != street2:
            return False

        # If both have numbers, they must match
        if addr1.street_number and addr2.street_number:
            num1 = addr1.street_number.lower().replace(" ", "")
            num2 = addr2.street_number.lower().replace(" ", "")
            if num1 != num2:
                return False

    return True


def format_address_for_display(address: SwedishAddress) -> str:
    """
    Format an address for user display.

    Args:
        address: SwedishAddress to format

    Returns:
        Nicely formatted address string
    """
    return address.full_address


def format_address_for_search(address: SwedishAddress) -> str:
    """
    Format an address for search indexing.

    Produces a normalized, lowercase string suitable for full-text search.

    Args:
        address: SwedishAddress to format

    Returns:
        Normalized search string
    """
    parts = []

    if address.street:
        parts.append(normalize_street_name(address.street).lower())
    if address.street_number:
        parts.append(address.street_number.lower())
    if address.postal_code:
        parts.append(address.postal_code)
        # Also add spaced version for search
        parts.append(f"{address.postal_code[:3]} {address.postal_code[3:]}")
    if address.city:
        parts.append(normalize_city_name(address.city).lower())

    return " ".join(parts)
