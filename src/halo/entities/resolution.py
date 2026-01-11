"""
Entity resolution engine for matching and deduplicating entities.

This module handles:
- Matching incoming records to existing entities
- Fuzzy name matching for Swedish names
- Merging duplicate entities
- Confidence scoring for matches
"""

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional
from uuid import UUID

from halo.swedish.organisationsnummer import validate_organisationsnummer
from halo.swedish.personnummer import validate_personnummer

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of matching an entity against the database."""

    entity_id: Optional[UUID]
    match_score: float
    match_type: str  # 'exact_id', 'exact_name', 'fuzzy_name', 'no_match'
    matched_fields: list[str]

    @property
    def is_match(self) -> bool:
        """Check if this is a valid match (score > threshold)."""
        return self.match_score >= 0.85


class SwedishNameMatcher:
    """
    Fuzzy matching for Swedish names.

    Handles common Swedish name variations:
    - Ä/Ö/Å normalization
    - Common misspellings
    - Nickname variations
    - Company suffix normalization (AB, HB, etc.)
    """

    # Common Swedish name variations
    NICKNAME_MAP = {
        "kalle": "karl",
        "lansen": "lars",
        "pelle": "per",
        "nansen": "göran",
        "benansen": "bengt",
        "oansen": "ola",
        "lansen": "lennart",
        "sansen": "sven",
        "lansen": "lars",
    }

    # Company suffixes to normalize
    COMPANY_SUFFIXES = [
        " aktiebolag",
        " ab",
        " handelsbolag",
        " hb",
        " kommanditbolag",
        " kb",
        " ek. för.",
        " ekonomisk förening",
    ]

    @staticmethod
    def normalize_swedish(text: str) -> str:
        """Normalize Swedish text for comparison."""
        text = text.lower().strip()

        # Normalize Swedish characters
        replacements = {
            "å": "a",
            "ä": "a",
            "ö": "o",
            "é": "e",
            "ü": "u",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    @classmethod
    def normalize_company_name(cls, name: str) -> str:
        """Normalize company name for comparison."""
        name = name.lower().strip()

        # Remove company suffixes
        for suffix in cls.COMPANY_SUFFIXES:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break

        return cls.normalize_swedish(name.strip())

    @classmethod
    def normalize_person_name(cls, name: str) -> str:
        """Normalize person name for comparison."""
        name = cls.normalize_swedish(name)

        # Replace nicknames with formal names
        parts = name.split()
        normalized_parts = []
        for part in parts:
            normalized_parts.append(cls.NICKNAME_MAP.get(part, part))

        return " ".join(normalized_parts)

    @staticmethod
    def similarity(s1: str, s2: str) -> float:
        """Calculate similarity ratio between two strings."""
        return SequenceMatcher(None, s1, s2).ratio()

    @classmethod
    def match_company_names(cls, name1: str, name2: str) -> float:
        """
        Calculate match score for two company names.

        Returns:
            Score from 0.0 to 1.0
        """
        norm1 = cls.normalize_company_name(name1)
        norm2 = cls.normalize_company_name(name2)

        # Exact match after normalization
        if norm1 == norm2:
            return 1.0

        # Fuzzy match
        return cls.similarity(norm1, norm2)

    @classmethod
    def match_person_names(cls, name1: str, name2: str) -> float:
        """
        Calculate match score for two person names.

        Returns:
            Score from 0.0 to 1.0
        """
        norm1 = cls.normalize_person_name(name1)
        norm2 = cls.normalize_person_name(name2)

        # Exact match after normalization
        if norm1 == norm2:
            return 1.0

        # Try matching with name parts reordered
        parts1 = set(norm1.split())
        parts2 = set(norm2.split())

        if parts1 == parts2:
            return 0.95

        # Calculate Jaccard similarity for name parts
        intersection = len(parts1 & parts2)
        union = len(parts1 | parts2)

        if union == 0:
            return 0.0

        jaccard = intersection / union

        # Also consider string similarity
        string_sim = cls.similarity(norm1, norm2)

        # Combine both measures
        return max(jaccard, string_sim)


class EntityResolver:
    """
    Entity resolution engine.

    Matches incoming records against existing entities using:
    1. Exact ID matching (personnummer, organisationsnummer)
    2. Fuzzy name matching
    3. Attribute matching (address, etc.)
    """

    def __init__(
        self,
        exact_match_threshold: float = 1.0,
        fuzzy_match_threshold: float = 0.85,
        low_confidence_threshold: float = 0.50,
    ):
        """
        Initialize the entity resolver.

        Args:
            exact_match_threshold: Score for exact ID matches
            fuzzy_match_threshold: Minimum score to consider a fuzzy match
            low_confidence_threshold: Minimum score to flag for review
        """
        self.exact_match_threshold = exact_match_threshold
        self.fuzzy_match_threshold = fuzzy_match_threshold
        self.low_confidence_threshold = low_confidence_threshold
        self.name_matcher = SwedishNameMatcher()

    def match_by_id(
        self,
        personnummer: Optional[str] = None,
        organisationsnummer: Optional[str] = None,
        existing_entities: list[dict] = None,
    ) -> Optional[MatchResult]:
        """
        Try to match entity by exact ID.

        Args:
            personnummer: Swedish personal ID to match
            organisationsnummer: Swedish org number to match
            existing_entities: List of existing entities to match against

        Returns:
            MatchResult if exact match found, None otherwise
        """
        existing_entities = existing_entities or []

        # Validate and normalize personnummer
        if personnummer:
            pnr_info = validate_personnummer(personnummer)
            if pnr_info.is_valid:
                normalized_pnr = pnr_info.normalized
                for entity in existing_entities:
                    if entity.get("personnummer") == normalized_pnr:
                        return MatchResult(
                            entity_id=entity.get("id"),
                            match_score=1.0,
                            match_type="exact_id",
                            matched_fields=["personnummer"],
                        )

        # Validate and normalize organisationsnummer
        if organisationsnummer:
            org_info = validate_organisationsnummer(organisationsnummer)
            if org_info.is_valid:
                normalized_org = org_info.normalized
                for entity in existing_entities:
                    if entity.get("organisationsnummer") == normalized_org:
                        return MatchResult(
                            entity_id=entity.get("id"),
                            match_score=1.0,
                            match_type="exact_id",
                            matched_fields=["organisationsnummer"],
                        )

        return None

    def match_by_name(
        self,
        name: str,
        entity_type: str,
        existing_entities: list[dict] = None,
    ) -> list[MatchResult]:
        """
        Match entity by name using fuzzy matching.

        Args:
            name: Name to match
            entity_type: 'person' or 'company'
            existing_entities: List of existing entities to match against

        Returns:
            List of potential matches sorted by score
        """
        existing_entities = existing_entities or []
        matches = []

        for entity in existing_entities:
            if entity.get("entity_type") != entity_type:
                continue

            existing_name = entity.get("display_name", "")

            if entity_type == "company":
                score = self.name_matcher.match_company_names(name, existing_name)
            else:
                score = self.name_matcher.match_person_names(name, existing_name)

            if score >= self.low_confidence_threshold:
                match_type = "exact_name" if score >= 0.99 else "fuzzy_name"
                matches.append(
                    MatchResult(
                        entity_id=entity.get("id"),
                        match_score=score,
                        match_type=match_type,
                        matched_fields=["display_name"],
                    )
                )

        # Sort by score descending
        matches.sort(key=lambda m: m.match_score, reverse=True)
        return matches

    def resolve(
        self,
        entity_type: str,
        display_name: str,
        personnummer: Optional[str] = None,
        organisationsnummer: Optional[str] = None,
        attributes: Optional[dict] = None,
        existing_entities: list[dict] = None,
    ) -> MatchResult:
        """
        Resolve an entity against existing records.

        This is the main entry point for entity resolution.

        Args:
            entity_type: Type of entity ('person', 'company', etc.)
            display_name: Name of the entity
            personnummer: Swedish personal ID (for persons)
            organisationsnummer: Swedish org number (for companies)
            attributes: Additional attributes for matching
            existing_entities: List of existing entities to match against

        Returns:
            MatchResult with the best match or no_match
        """
        existing_entities = existing_entities or []

        # Step 1: Try exact ID match
        id_match = self.match_by_id(
            personnummer=personnummer,
            organisationsnummer=organisationsnummer,
            existing_entities=existing_entities,
        )
        if id_match:
            logger.debug(f"Exact ID match found for {display_name}")
            return id_match

        # Step 2: Try name matching
        name_matches = self.match_by_name(
            name=display_name,
            entity_type=entity_type,
            existing_entities=existing_entities,
        )

        if name_matches:
            best_match = name_matches[0]
            if best_match.match_score >= self.fuzzy_match_threshold:
                logger.debug(
                    f"Name match found for {display_name}: score={best_match.match_score}"
                )
                return best_match
            else:
                logger.debug(
                    f"Low confidence name match for {display_name}: score={best_match.match_score}"
                )
                # Return the low-confidence match for review
                return best_match

        # Step 3: No match found
        logger.debug(f"No match found for {display_name}")
        return MatchResult(
            entity_id=None,
            match_score=0.0,
            match_type="no_match",
            matched_fields=[],
        )
