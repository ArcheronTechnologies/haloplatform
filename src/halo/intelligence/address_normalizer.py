"""
Swedish Address Normalization.

Normalizes Swedish addresses to enable clustering and registration mill detection.
Handles variations in formatting, abbreviations, and c/o addresses.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class NormalizedAddress:
    """Normalized Swedish address."""
    street: str
    street_number: Optional[str]
    postal_code: str  # Format: NNNNN (no space)
    city: str
    co_name: Optional[str]  # c/o recipient
    box_number: Optional[str]  # Box number if PO Box
    is_virtual: bool  # Known virtual office provider
    raw: str  # Original input

    @property
    def cluster_key(self) -> str:
        """
        Key for clustering addresses.

        Two addresses with the same cluster_key should be considered the same
        physical location for company clustering purposes.
        """
        if self.box_number:
            # PO Boxes cluster by box number + postal code
            return f"BOX-{self.box_number}-{self.postal_code}"
        else:
            # Street addresses cluster by street + number + postal code
            num = self.street_number or ""
            return f"{self.street.upper()}-{num}-{self.postal_code}"

    def to_dict(self) -> dict:
        return {
            "street": self.street,
            "street_number": self.street_number,
            "postal_code": self.postal_code,
            "city": self.city,
            "co_name": self.co_name,
            "box_number": self.box_number,
            "is_virtual": self.is_virtual,
            "cluster_key": self.cluster_key,
            "raw": self.raw,
        }


# Known virtual office providers in Sweden
# These addresses are commonly used for shell companies
VIRTUAL_OFFICE_PATTERNS = [
    # Major virtual office providers
    r"regus",
    r"spaces",
    r"mindspace",
    r"epicenter",
    r"convendum",
    r"no18",
    r"norrsken",
    r"the park",
    r"united spaces",
    r"work\s*club",
    # Generic patterns
    r"kontorshotell",
    r"business\s*center",
    r"företagshotell",
]

# Street name abbreviations to normalize
STREET_ABBREVIATIONS = {
    "g.": "gatan",
    "gt.": "gatan",
    "gt": "gatan",
    "v.": "vägen",
    "vg.": "vägen",
    "vg": "vägen",
    "pl.": "plan",
    "str.": "stråket",
    "all.": "allén",
    "t.": "torget",
    "tg.": "torget",
}


class AddressNormalizer:
    """
    Swedish address normalizer.

    Handles:
    - c/o addresses
    - PO Boxes (Box, Postbox)
    - Street abbreviations
    - Postal code formatting
    - Virtual office detection
    """

    def __init__(self):
        self.virtual_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in VIRTUAL_OFFICE_PATTERNS
        ]

    def normalize(self, raw_address: str) -> NormalizedAddress:
        """
        Normalize a Swedish address string.

        Examples:
        - "Box 911, 251 09 Helsingborg" -> PO Box
        - "c/o Sabis AB, Box 6015, 102 31 Stockholm" -> c/o + PO Box
        - "Herkulesgatan 72, 405 08 Göteborg" -> Street address
        - "Kungsg. 12, 111 43 Stockholm" -> Expand abbreviation
        """
        if not raw_address:
            return NormalizedAddress(
                street="",
                street_number=None,
                postal_code="",
                city="",
                co_name=None,
                box_number=None,
                is_virtual=False,
                raw=raw_address or "",
            )

        # Clean input
        addr = raw_address.strip()
        original = addr

        # Extract c/o
        co_name = None
        co_match = re.match(r"c/o\s+([^,]+),?\s*", addr, re.IGNORECASE)
        if co_match:
            co_name = co_match.group(1).strip()
            addr = addr[co_match.end():].strip()

        # Extract postal code and city (usually at the end)
        # Swedish postal codes: NNN NN or NNNNN
        postal_city_match = re.search(
            r",?\s*(\d{3})\s*(\d{2})\s+([A-Za-zÅÄÖåäö\s]+)\s*$",
            addr
        )

        postal_code = ""
        city = ""
        if postal_city_match:
            postal_code = postal_city_match.group(1) + postal_city_match.group(2)
            city = postal_city_match.group(3).strip()
            addr = addr[:postal_city_match.start()].strip().rstrip(",")

        # Check for PO Box
        box_number = None
        box_match = re.match(r"(?:post)?box\s*(\d+)", addr, re.IGNORECASE)
        if box_match:
            box_number = box_match.group(1)
            addr = addr[box_match.end():].strip().lstrip(",").strip()

        # Parse street address
        street = ""
        street_number = None

        if addr and not box_number:
            # Try to extract street number
            # Handle formats like "Kungsgatan 12", "Kungsg. 12 A", "Storgatan 5-7"
            street_match = re.match(
                r"(.+?)\s+(\d+(?:\s*[-–]\s*\d+)?(?:\s*[A-Za-z])?)\s*$",
                addr
            )
            if street_match:
                street = street_match.group(1).strip()
                street_number = street_match.group(2).strip()
            else:
                street = addr
        elif addr:
            street = addr

        # Expand street abbreviations
        street = self._expand_abbreviations(street)

        # Check for virtual office
        is_virtual = self._is_virtual_office(original)

        return NormalizedAddress(
            street=street,
            street_number=street_number,
            postal_code=postal_code,
            city=city,
            co_name=co_name,
            box_number=box_number,
            is_virtual=is_virtual,
            raw=original,
        )

    def _expand_abbreviations(self, street: str) -> str:
        """Expand common Swedish street abbreviations."""
        result = street
        for abbr, full in STREET_ABBREVIATIONS.items():
            # Match the abbreviation (case insensitive)
            # Handle both with and without trailing period
            if abbr.endswith("."):
                # With period - exact match
                pattern = re.compile(
                    re.escape(abbr),
                    re.IGNORECASE
                )
            else:
                # Without period - match at word boundary or before period
                pattern = re.compile(
                    re.escape(abbr) + r"\.?(?=\s|$)",
                    re.IGNORECASE
                )
            result = pattern.sub(full, result)
        return result

    def _is_virtual_office(self, address: str) -> bool:
        """Check if address matches known virtual office patterns."""
        for pattern in self.virtual_patterns:
            if pattern.search(address):
                return True
        return False

    def get_cluster_key(self, raw_address: str) -> str:
        """Get clustering key for an address."""
        normalized = self.normalize(raw_address)
        return normalized.cluster_key

    def same_location(self, addr1: str, addr2: str) -> bool:
        """Check if two addresses represent the same physical location."""
        norm1 = self.normalize(addr1)
        norm2 = self.normalize(addr2)
        return norm1.cluster_key == norm2.cluster_key


def normalize_graph_addresses(g) -> dict:
    """
    Normalize all addresses in a graph and return clustering stats.

    Args:
        g: NetworkX graph with Address nodes

    Returns:
        dict with clustering statistics and cluster assignments
    """
    from collections import defaultdict

    normalizer = AddressNormalizer()
    clusters = defaultdict(list)
    virtual_count = 0

    for node_id, data in g.nodes(data=True):
        if data.get("_type") != "Address":
            continue

        # Get raw address string
        raw_strings = data.get("raw_strings", [])
        raw_addr = raw_strings[0] if raw_strings else ""

        # Normalize
        normalized = normalizer.normalize(raw_addr)

        # Update node with normalized data
        g.nodes[node_id]["normalized_v2"] = normalized.to_dict()
        g.nodes[node_id]["cluster_key"] = normalized.cluster_key
        g.nodes[node_id]["is_virtual"] = normalized.is_virtual

        # Track clusters
        clusters[normalized.cluster_key].append(node_id)

        if normalized.is_virtual:
            virtual_count += 1

    # Calculate stats
    cluster_sizes = [len(v) for v in clusters.values()]
    multi_company_clusters = sum(1 for v in clusters.values() if len(v) > 1)

    return {
        "total_addresses": len(cluster_sizes),
        "unique_clusters": len(clusters),
        "multi_company_clusters": multi_company_clusters,
        "virtual_office_addresses": virtual_count,
        "largest_cluster": max(cluster_sizes) if cluster_sizes else 0,
        "clusters": dict(clusters),
    }
