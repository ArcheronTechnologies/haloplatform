"""
Blocking strategies for efficient candidate generation.

Blocking reduces the O(n²) comparison problem by grouping
entities that are likely to match using blocking keys.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class BlockingStrategy(str, Enum):
    """Available blocking strategies."""

    EXACT_IDENTIFIER = "exact_identifier"  # Personnummer, orgnummer exact match
    PHONETIC = "phonetic"  # Double Metaphone phonetic encoding
    NAME_PREFIX_YEAR = "name_prefix_year"  # First 4 chars + birth year
    POSTAL_PREFIX = "postal_prefix"  # First 3 digits of postal code
    NAME_TOKENS = "name_tokens"  # Individual name tokens


@dataclass
class BlockingKey:
    """A blocking key for candidate lookup."""

    strategy: BlockingStrategy
    key_value: str
    entity_type: str


@dataclass
class CandidateEntity:
    """A candidate entity for resolution."""

    id: UUID
    entity_type: str
    canonical_name: str
    identifiers: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class Mention:
    """A mention to be resolved."""

    id: UUID
    mention_type: str  # PERSON, COMPANY, ADDRESS
    surface_form: str
    normalized_form: str
    extracted_personnummer: Optional[str] = None
    extracted_orgnummer: Optional[str] = None
    extracted_attributes: dict[str, Any] = field(default_factory=dict)
    provenance_id: Optional[UUID] = None
    source_document: Optional[str] = None


class BlockingIndex:
    """
    Blocking index for efficient candidate generation.

    Uses multiple blocking strategies to balance recall vs performance.
    """

    def __init__(self):
        # In-memory indices for fast lookup
        self._identifier_index: dict[str, list[CandidateEntity]] = {}
        self._phonetic_index: dict[str, list[CandidateEntity]] = {}
        self._prefix_year_index: dict[str, list[CandidateEntity]] = {}
        self._postal_index: dict[str, list[CandidateEntity]] = {}
        self._token_index: dict[str, list[CandidateEntity]] = {}

    def add_entity(self, entity: CandidateEntity) -> None:
        """Add an entity to the blocking indices."""
        # Index by identifiers
        for id_type, id_value in entity.identifiers.items():
            key = f"{id_type}:{id_value}"
            if key not in self._identifier_index:
                self._identifier_index[key] = []
            self._identifier_index[key].append(entity)

        # Index by phonetic key
        phonetic_key = self._get_phonetic_key(entity.canonical_name)
        type_phonetic = f"{entity.entity_type}:{phonetic_key}"
        if type_phonetic not in self._phonetic_index:
            self._phonetic_index[type_phonetic] = []
        self._phonetic_index[type_phonetic].append(entity)

        # Index by name prefix + birth year (persons only)
        if entity.entity_type == "PERSON":
            birth_year = entity.attributes.get("birth_year")
            if birth_year and entity.canonical_name:
                prefix_key = f"{entity.canonical_name[:4].upper()}_{birth_year}"
                if prefix_key not in self._prefix_year_index:
                    self._prefix_year_index[prefix_key] = []
                self._prefix_year_index[prefix_key].append(entity)

        # Index by postal prefix (addresses only)
        if entity.entity_type == "ADDRESS":
            postal_code = entity.attributes.get("postal_code", "")
            if postal_code and len(postal_code) >= 3:
                postal_prefix = postal_code[:3]
                if postal_prefix not in self._postal_index:
                    self._postal_index[postal_prefix] = []
                self._postal_index[postal_prefix].append(entity)

        # Index by name tokens
        tokens = self._tokenize_name(entity.canonical_name)
        for token in tokens:
            type_token = f"{entity.entity_type}:{token}"
            if type_token not in self._token_index:
                self._token_index[type_token] = []
            self._token_index[type_token].append(entity)

    def get_candidates(self, mention: Mention) -> list[CandidateEntity]:
        """
        Get candidate entities for a mention.

        Uses multiple blocking strategies for high recall.
        """
        candidates: dict[UUID, CandidateEntity] = {}

        # Strategy 1: Exact identifier match (highest priority)
        if mention.extracted_personnummer:
            key = f"PERSONNUMMER:{mention.extracted_personnummer}"
            for entity in self._identifier_index.get(key, []):
                candidates[entity.id] = entity
                # If we have an exact identifier match, that's definitive
                logger.debug(f"Exact personnummer match for {mention.id}")
                return list(candidates.values())

        if mention.extracted_orgnummer:
            key = f"ORGANISATIONSNUMMER:{mention.extracted_orgnummer}"
            for entity in self._identifier_index.get(key, []):
                candidates[entity.id] = entity
                logger.debug(f"Exact orgnummer match for {mention.id}")
                return list(candidates.values())

        # Strategy 2: Phonetic blocking
        phonetic_key = self._get_phonetic_key(mention.normalized_form)
        type_phonetic = f"{mention.mention_type}:{phonetic_key}"
        for entity in self._phonetic_index.get(type_phonetic, []):
            candidates[entity.id] = entity

        # Strategy 3: Name prefix + birth year (persons only)
        if mention.mention_type == "PERSON":
            birth_year = mention.extracted_attributes.get("birth_year")
            if birth_year and mention.normalized_form:
                prefix_key = f"{mention.normalized_form[:4].upper()}_{birth_year}"
                for entity in self._prefix_year_index.get(prefix_key, []):
                    candidates[entity.id] = entity

        # Strategy 4: Postal prefix (addresses only)
        if mention.mention_type == "ADDRESS":
            postal_code = mention.extracted_attributes.get("postal_code", "")
            if postal_code and len(postal_code) >= 3:
                postal_prefix = postal_code[:3]
                for entity in self._postal_index.get(postal_prefix, []):
                    candidates[entity.id] = entity

        # Strategy 5: Token overlap (fallback for fuzzy matching)
        if not candidates:
            tokens = self._tokenize_name(mention.normalized_form)
            for token in tokens:
                type_token = f"{mention.mention_type}:{token}"
                for entity in self._token_index.get(type_token, []):
                    candidates[entity.id] = entity

        logger.debug(f"Found {len(candidates)} candidates for mention {mention.id}")
        return list(candidates.values())

    def _get_phonetic_key(self, name: str) -> str:
        """Generate phonetic key using Double Metaphone."""
        try:
            import metaphone

            primary, secondary = metaphone.doublemetaphone(name)
            return primary or secondary or name[:4].upper()
        except ImportError:
            # Fallback if metaphone not installed
            return name[:4].upper()

    def _tokenize_name(self, name: str) -> set[str]:
        """Tokenize a name into normalized tokens."""
        if not name:
            return set()
        # Remove common titles and normalize
        tokens = name.lower().split()
        # Filter out very short tokens and common words
        stopwords = {"ab", "i", "och", "av", "för", "med", "den", "det"}
        return {t for t in tokens if len(t) > 2 and t not in stopwords}

    def clear(self) -> None:
        """Clear all indices."""
        self._identifier_index.clear()
        self._phonetic_index.clear()
        self._prefix_year_index.clear()
        self._postal_index.clear()
        self._token_index.clear()

    def stats(self) -> dict[str, int]:
        """Get index statistics."""
        return {
            "identifier_keys": len(self._identifier_index),
            "phonetic_keys": len(self._phonetic_index),
            "prefix_year_keys": len(self._prefix_year_index),
            "postal_keys": len(self._postal_index),
            "token_keys": len(self._token_index),
        }
