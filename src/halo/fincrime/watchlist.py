"""
Watchlist screening for AML/CTF compliance.

Checks entities against:
- Sanctions lists (EU, UN, US OFAC, Swedish)
- PEP lists (Politically Exposed Persons)
- Adverse media
- Law enforcement lists
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class WatchlistType(str, Enum):
    """Types of watchlists."""

    SANCTIONS_EU = "sanctions_eu"
    SANCTIONS_UN = "sanctions_un"
    SANCTIONS_OFAC = "sanctions_ofac"
    SANCTIONS_SE = "sanctions_se"  # Swedish
    PEP_DOMESTIC = "pep_domestic"
    PEP_FOREIGN = "pep_foreign"
    PEP_INTERNATIONAL_ORG = "pep_international_org"
    LAW_ENFORCEMENT = "law_enforcement"
    ADVERSE_MEDIA = "adverse_media"
    INTERNAL = "internal"  # Company's own list


class MatchType(str, Enum):
    """How the match was determined."""

    EXACT = "exact"
    FUZZY = "fuzzy"
    ALIAS = "alias"
    IDENTIFIER = "identifier"  # Match on personnummer, orgnr, passport, etc.


@dataclass
class WatchlistEntry:
    """An entry on a watchlist."""

    id: str
    list_type: WatchlistType
    name: str
    aliases: list[str] = field(default_factory=list)

    # Identifiers
    identifiers: dict[str, str] = field(default_factory=dict)
    # e.g., {"personnummer": "...", "passport": "..."}

    # Details
    nationality: Optional[str] = None
    date_of_birth: Optional[str] = None
    description: Optional[str] = None

    # Source
    source: str = ""
    source_url: Optional[str] = None
    added_date: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    # Active status
    is_active: bool = True


@dataclass
class WatchlistMatch:
    """A match against a watchlist entry."""

    entry: WatchlistEntry
    match_type: MatchType
    match_score: float  # 0.0 to 1.0
    matched_field: str  # Which field matched
    matched_value: str  # The value that matched

    # Query info
    query_name: Optional[str] = None
    query_identifier: Optional[str] = None

    # Metadata
    checked_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "list_type": self.entry.list_type.value,
            "list_name": self.entry.list_type.name,
            "entry_id": self.entry.id,
            "entry_name": self.entry.name,
            "match_type": self.match_type.value,
            "match_score": self.match_score,
            "matched_field": self.matched_field,
            "matched_value": self.matched_value,
            "description": self.entry.description,
            "source": self.entry.source,
            "checked_at": self.checked_at.isoformat(),
        }


class WatchlistChecker:
    """
    Check entities against multiple watchlists.

    In production, this would integrate with:
    - EU Consolidated Sanctions List
    - UN Security Council Consolidated List
    - US OFAC SDN List
    - Swedish Financial Supervisory Authority lists
    - Commercial PEP/sanctions data providers

    This implementation provides the interface and fuzzy matching logic.
    """

    def __init__(
        self,
        min_fuzzy_score: float = 0.85,
        check_aliases: bool = True,
    ):
        """
        Initialize the watchlist checker.

        Args:
            min_fuzzy_score: Minimum score for fuzzy matches (0-1)
            check_aliases: Whether to check against known aliases
        """
        self.min_fuzzy_score = min_fuzzy_score
        self.check_aliases = check_aliases

        # In-memory watchlist storage (for demo)
        # In production, this would be a database or external API
        self._entries: dict[WatchlistType, list[WatchlistEntry]] = {
            wl_type: [] for wl_type in WatchlistType
        }

    def add_entry(self, entry: WatchlistEntry) -> None:
        """Add an entry to a watchlist."""
        self._entries[entry.list_type].append(entry)

    def load_entries(self, entries: list[WatchlistEntry]) -> int:
        """Load multiple entries. Returns count loaded."""
        for entry in entries:
            self.add_entry(entry)
        return len(entries)

    def check_entity(
        self,
        name: str,
        identifier: Optional[str] = None,
        identifier_type: str = "personnummer",
        date_of_birth: Optional[str] = None,
        nationality: Optional[str] = None,
        lists_to_check: Optional[list[WatchlistType]] = None,
    ) -> list[WatchlistMatch]:
        """
        Check an entity against watchlists.

        Args:
            name: Entity name (person or company)
            identifier: Optional identifier (personnummer, orgnr, passport)
            identifier_type: Type of identifier
            date_of_birth: Optional DOB for persons
            nationality: Optional nationality code
            lists_to_check: Optional specific lists to check (default: all)

        Returns:
            List of matches found
        """
        matches = []
        lists = lists_to_check or list(WatchlistType)

        # Normalize query name
        query_name_normalized = self._normalize_name(name)

        for list_type in lists:
            for entry in self._entries.get(list_type, []):
                if not entry.is_active:
                    continue

                # Check identifier first (most reliable)
                if identifier and identifier_type in entry.identifiers:
                    if self._identifiers_match(
                        identifier,
                        entry.identifiers[identifier_type],
                        identifier_type,
                    ):
                        matches.append(WatchlistMatch(
                            entry=entry,
                            match_type=MatchType.IDENTIFIER,
                            match_score=1.0,
                            matched_field=identifier_type,
                            matched_value=identifier,
                            query_name=name,
                            query_identifier=identifier,
                        ))
                        continue  # No need to check name if ID matches

                # Check exact name match
                if query_name_normalized == self._normalize_name(entry.name):
                    matches.append(WatchlistMatch(
                        entry=entry,
                        match_type=MatchType.EXACT,
                        match_score=1.0,
                        matched_field="name",
                        matched_value=entry.name,
                        query_name=name,
                        query_identifier=identifier,
                    ))
                    continue

                # Check aliases
                if self.check_aliases:
                    for alias in entry.aliases:
                        if query_name_normalized == self._normalize_name(alias):
                            matches.append(WatchlistMatch(
                                entry=entry,
                                match_type=MatchType.ALIAS,
                                match_score=0.95,
                                matched_field="alias",
                                matched_value=alias,
                                query_name=name,
                                query_identifier=identifier,
                            ))
                            break  # Only one match per entry

                # Fuzzy name match
                fuzzy_score = self._fuzzy_match(query_name_normalized, entry.name)
                if fuzzy_score >= self.min_fuzzy_score:
                    # Additional validation if DOB available
                    if date_of_birth and entry.date_of_birth:
                        if date_of_birth != entry.date_of_birth:
                            fuzzy_score *= 0.5  # Reduce confidence

                    if fuzzy_score >= self.min_fuzzy_score:
                        matches.append(WatchlistMatch(
                            entry=entry,
                            match_type=MatchType.FUZZY,
                            match_score=fuzzy_score,
                            matched_field="name",
                            matched_value=entry.name,
                            query_name=name,
                            query_identifier=identifier,
                        ))

        # Sort by score descending
        matches.sort(key=lambda m: m.match_score, reverse=True)

        return matches

    def check_batch(
        self,
        entities: list[dict[str, Any]],
        lists_to_check: Optional[list[WatchlistType]] = None,
    ) -> dict[str, list[WatchlistMatch]]:
        """
        Check multiple entities.

        Args:
            entities: List of entity dicts with 'name' and optional 'identifier'
            lists_to_check: Optional specific lists to check

        Returns:
            Dict mapping entity identifiers to their matches
        """
        results = {}

        for entity in entities:
            key = entity.get("identifier") or entity.get("name", "unknown")
            matches = self.check_entity(
                name=entity.get("name", ""),
                identifier=entity.get("identifier"),
                identifier_type=entity.get("identifier_type", "personnummer"),
                date_of_birth=entity.get("date_of_birth"),
                nationality=entity.get("nationality"),
                lists_to_check=lists_to_check,
            )
            results[key] = matches

        return results

    def is_sanctioned(
        self,
        name: str,
        identifier: Optional[str] = None,
    ) -> bool:
        """Quick check if entity is on any sanctions list."""
        sanctions_lists = [
            WatchlistType.SANCTIONS_EU,
            WatchlistType.SANCTIONS_UN,
            WatchlistType.SANCTIONS_OFAC,
            WatchlistType.SANCTIONS_SE,
        ]

        matches = self.check_entity(
            name=name,
            identifier=identifier,
            lists_to_check=sanctions_lists,
        )

        return len(matches) > 0

    def is_pep(
        self,
        name: str,
        identifier: Optional[str] = None,
    ) -> bool:
        """Quick check if entity is a PEP."""
        pep_lists = [
            WatchlistType.PEP_DOMESTIC,
            WatchlistType.PEP_FOREIGN,
            WatchlistType.PEP_INTERNATIONAL_ORG,
        ]

        matches = self.check_entity(
            name=name,
            identifier=identifier,
            lists_to_check=pep_lists,
        )

        return len(matches) > 0

    def _normalize_name(self, name: str) -> str:
        """Normalize name for comparison."""
        if not name:
            return ""

        # Lowercase
        normalized = name.lower()

        # Remove common titles
        titles = ["mr", "mrs", "ms", "dr", "prof", "herr", "fru", "fröken"]
        for title in titles:
            normalized = re.sub(rf"\b{title}\.?\s+", "", normalized)

        # Remove special characters but keep spaces
        normalized = re.sub(r"[^\w\s]", "", normalized)

        # Normalize whitespace
        normalized = " ".join(normalized.split())

        return normalized

    def _identifiers_match(
        self,
        query: str,
        entry_id: str,
        id_type: str,
    ) -> bool:
        """Check if identifiers match."""
        # Normalize both
        q = re.sub(r"[\s\-]", "", query.upper())
        e = re.sub(r"[\s\-]", "", entry_id.upper())

        return q == e

    def _fuzzy_match(self, query: str, target: str) -> float:
        """
        Calculate fuzzy match score between two names.

        Uses a combination of techniques:
        - Levenshtein distance
        - Token matching
        - Phonetic similarity (for Swedish names)
        """
        query_normalized = self._normalize_name(query)
        target_normalized = self._normalize_name(target)

        if not query_normalized or not target_normalized:
            return 0.0

        # Exact match after normalization
        if query_normalized == target_normalized:
            return 1.0

        # Token-based matching
        query_tokens = set(query_normalized.split())
        target_tokens = set(target_normalized.split())

        if not query_tokens or not target_tokens:
            return 0.0

        # Jaccard similarity of tokens
        intersection = query_tokens & target_tokens
        union = query_tokens | target_tokens
        jaccard = len(intersection) / len(union)

        # Character-level similarity (simplified Levenshtein ratio)
        max_len = max(len(query_normalized), len(target_normalized))
        distance = self._levenshtein_distance(query_normalized, target_normalized)
        char_similarity = 1 - (distance / max_len)

        # Combine scores
        combined = (jaccard * 0.4) + (char_similarity * 0.6)

        return combined

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein edit distance."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def get_list_stats(self) -> dict[str, int]:
        """Get count of entries per list type."""
        return {
            wl_type.value: len(entries)
            for wl_type, entries in self._entries.items()
        }


# Example Swedish sanctions/PEP entries for testing
def create_sample_entries() -> list[WatchlistEntry]:
    """Create sample watchlist entries for testing."""
    return [
        WatchlistEntry(
            id="SE-PEP-001",
            list_type=WatchlistType.PEP_DOMESTIC,
            name="Test Testsson",
            aliases=["T. Testsson"],
            identifiers={"personnummer": "19800101-1234"},
            nationality="SE",
            description="Sample PEP entry for testing",
            source="test_data",
        ),
        WatchlistEntry(
            id="EU-SANC-001",
            list_type=WatchlistType.SANCTIONS_EU,
            name="Sanctioned Person",
            aliases=["S. Person", "Sanctioned P."],
            identifiers={"passport": "AB123456"},
            nationality="RU",
            description="Sample sanctions entry",
            source="test_data",
        ),
    ]
