"""
Feature comparison for entity resolution.

Computes similarity features between mentions and candidate entities.
Uses rule-based weighted scoring (no ML for MVP).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from halo.resolution.blocking import CandidateEntity, Mention

logger = logging.getLogger(__name__)


@dataclass
class FeatureScores:
    """Comparison feature scores between a mention and candidate."""

    # Identifier features
    identifier_match: float = 0.0  # 1.0 if exact match, 0.0 otherwise

    # Name similarity features
    name_jaro_winkler: float = 0.0  # Jaro-Winkler similarity [0,1]
    name_token_jaccard: float = 0.0  # Jaccard similarity of name tokens
    name_levenshtein_norm: float = 0.0  # Normalized Levenshtein distance

    # Attribute features
    birth_year_match: float = 0.0  # 1.0 if years match
    birth_date_match: float = 0.0  # 1.0 if full dates match
    gender_match: float = 0.0  # 1.0 if genders match

    # Address features
    address_similarity: float = 0.0  # Overall address similarity
    postal_code_match: float = 0.0  # 1.0 if postal codes match
    city_match: float = 0.0  # 1.0 if cities match

    # Network features
    network_overlap: float = 0.0  # Jaccard of shared connections
    company_overlap: float = 0.0  # For persons: shared companies
    director_overlap: float = 0.0  # For companies: shared directors

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "identifier_match": self.identifier_match,
            "name_jaro_winkler": self.name_jaro_winkler,
            "name_token_jaccard": self.name_token_jaccard,
            "name_levenshtein_norm": self.name_levenshtein_norm,
            "birth_year_match": self.birth_year_match,
            "birth_date_match": self.birth_date_match,
            "gender_match": self.gender_match,
            "address_similarity": self.address_similarity,
            "postal_code_match": self.postal_code_match,
            "city_match": self.city_match,
            "network_overlap": self.network_overlap,
            "company_overlap": self.company_overlap,
            "director_overlap": self.director_overlap,
        }


@dataclass
class WeightConfig:
    """Feature weights for scoring."""

    identifier_match: float = 10.0  # Definitive signal
    name_jaro_winkler: float = 2.0
    name_token_jaccard: float = 1.5
    name_levenshtein_norm: float = 1.0
    birth_year_match: float = 1.5
    birth_date_match: float = 3.0
    gender_match: float = 0.5
    address_similarity: float = 1.0
    postal_code_match: float = 0.5
    city_match: float = 0.3
    network_overlap: float = 2.5  # Strong signal
    company_overlap: float = 2.0
    director_overlap: float = 2.0


# Default weights per entity type
PERSON_WEIGHTS = WeightConfig(
    identifier_match=10.0,
    name_jaro_winkler=2.0,
    name_token_jaccard=1.5,
    name_levenshtein_norm=1.0,
    birth_year_match=1.5,
    birth_date_match=3.0,
    gender_match=0.5,
    network_overlap=2.5,
    company_overlap=2.0,
)

COMPANY_WEIGHTS = WeightConfig(
    identifier_match=10.0,
    name_jaro_winkler=3.0,
    name_token_jaccard=2.0,
    name_levenshtein_norm=1.5,
    address_similarity=1.5,
    postal_code_match=1.0,
    director_overlap=2.0,
)

ADDRESS_WEIGHTS = WeightConfig(
    name_jaro_winkler=2.0,
    address_similarity=3.0,
    postal_code_match=2.5,
    city_match=1.5,
)


class FeatureComparator:
    """
    Compute pairwise features for entity resolution.

    Uses string similarity, attribute matching, and network overlap.
    """

    def __init__(
        self,
        person_weights: Optional[WeightConfig] = None,
        company_weights: Optional[WeightConfig] = None,
        address_weights: Optional[WeightConfig] = None,
    ):
        self.person_weights = person_weights or PERSON_WEIGHTS
        self.company_weights = company_weights or COMPANY_WEIGHTS
        self.address_weights = address_weights or ADDRESS_WEIGHTS

    def compute_features(
        self,
        mention: Mention,
        entity: CandidateEntity,
    ) -> FeatureScores:
        """
        Compute all comparison features between mention and entity.
        """
        if mention.mention_type == "PERSON":
            return self._compute_person_features(mention, entity)
        elif mention.mention_type == "COMPANY":
            return self._compute_company_features(mention, entity)
        elif mention.mention_type == "ADDRESS":
            return self._compute_address_features(mention, entity)
        else:
            return FeatureScores()

    def score_features(
        self,
        features: FeatureScores,
        entity_type: str,
    ) -> float:
        """
        Compute weighted score from features.

        Returns a score between 0 and 1.
        """
        # Definitive identifier match
        if features.identifier_match == 1.0:
            return 0.99

        # Get weights for entity type
        if entity_type == "PERSON":
            weights = self.person_weights
        elif entity_type == "COMPANY":
            weights = self.company_weights
        else:
            weights = self.address_weights

        feature_dict = features.to_dict()

        total = 0.0
        max_possible = 0.0

        for feature_name, value in feature_dict.items():
            weight = getattr(weights, feature_name, 0.0)
            if weight > 0 and value > 0:
                total += value * weight
                max_possible += weight
            elif weight > 0:
                # Count towards max but not total
                max_possible += weight

        if max_possible == 0:
            return 0.0

        return min(total / max_possible, 1.0)

    def _compute_person_features(
        self,
        mention: Mention,
        entity: CandidateEntity,
    ) -> FeatureScores:
        """Compute features for person resolution."""
        scores = FeatureScores()

        # Identifier match
        if mention.extracted_personnummer:
            entity_pnr = entity.identifiers.get("PERSONNUMMER")
            if entity_pnr and entity_pnr == mention.extracted_personnummer:
                scores.identifier_match = 1.0

        # Name similarity
        scores.name_jaro_winkler = self._jaro_winkler(
            mention.normalized_form, entity.canonical_name
        )
        scores.name_token_jaccard = self._token_jaccard(
            mention.normalized_form, entity.canonical_name
        )
        scores.name_levenshtein_norm = self._levenshtein_normalized(
            mention.normalized_form, entity.canonical_name
        )

        # Birth year/date
        mention_year = mention.extracted_attributes.get("birth_year")
        entity_year = entity.attributes.get("birth_year")
        if mention_year and entity_year:
            scores.birth_year_match = 1.0 if mention_year == entity_year else 0.0

        mention_date = mention.extracted_attributes.get("birth_date")
        entity_date = entity.attributes.get("birth_date")
        if mention_date and entity_date:
            scores.birth_date_match = 1.0 if mention_date == entity_date else 0.0

        # Gender
        mention_gender = mention.extracted_attributes.get("gender")
        entity_gender = entity.attributes.get("gender")
        if mention_gender and entity_gender:
            scores.gender_match = 1.0 if mention_gender == entity_gender else 0.0

        # Network overlap (shared companies)
        mention_companies = set(mention.extracted_attributes.get("companies", []))
        entity_companies = set(entity.attributes.get("companies", []))
        if mention_companies and entity_companies:
            intersection = len(mention_companies & entity_companies)
            union = len(mention_companies | entity_companies)
            scores.company_overlap = intersection / union if union > 0 else 0.0
            scores.network_overlap = scores.company_overlap

        return scores

    def _compute_company_features(
        self,
        mention: Mention,
        entity: CandidateEntity,
    ) -> FeatureScores:
        """Compute features for company resolution."""
        scores = FeatureScores()

        # Identifier match
        if mention.extracted_orgnummer:
            entity_org = entity.identifiers.get("ORGANISATIONSNUMMER")
            if entity_org and entity_org == mention.extracted_orgnummer:
                scores.identifier_match = 1.0

        # Name similarity (more important for companies)
        scores.name_jaro_winkler = self._jaro_winkler(
            mention.normalized_form, entity.canonical_name
        )
        scores.name_token_jaccard = self._token_jaccard(
            mention.normalized_form, entity.canonical_name
        )
        scores.name_levenshtein_norm = self._levenshtein_normalized(
            mention.normalized_form, entity.canonical_name
        )

        # Address similarity
        mention_postal = mention.extracted_attributes.get("postal_code")
        entity_postal = entity.attributes.get("postal_code")
        if mention_postal and entity_postal:
            scores.postal_code_match = 1.0 if mention_postal == entity_postal else 0.0

        mention_city = mention.extracted_attributes.get("city", "").lower()
        entity_city = entity.attributes.get("city", "").lower()
        if mention_city and entity_city:
            scores.city_match = 1.0 if mention_city == entity_city else 0.0

        # Director overlap
        mention_directors = set(mention.extracted_attributes.get("directors", []))
        entity_directors = set(entity.attributes.get("directors", []))
        if mention_directors and entity_directors:
            intersection = len(mention_directors & entity_directors)
            union = len(mention_directors | entity_directors)
            scores.director_overlap = intersection / union if union > 0 else 0.0
            scores.network_overlap = scores.director_overlap

        return scores

    def _compute_address_features(
        self,
        mention: Mention,
        entity: CandidateEntity,
    ) -> FeatureScores:
        """Compute features for address resolution."""
        scores = FeatureScores()

        # Street name similarity
        scores.name_jaro_winkler = self._jaro_winkler(
            mention.normalized_form, entity.canonical_name
        )

        # Postal code
        mention_postal = mention.extracted_attributes.get("postal_code")
        entity_postal = entity.attributes.get("postal_code")
        if mention_postal and entity_postal:
            scores.postal_code_match = 1.0 if mention_postal == entity_postal else 0.0

        # City
        mention_city = mention.extracted_attributes.get("city", "").lower()
        entity_city = entity.attributes.get("city", "").lower()
        if mention_city and entity_city:
            scores.city_match = self._jaro_winkler(mention_city, entity_city)

        # Overall address similarity
        address_components = []
        if scores.postal_code_match > 0:
            address_components.append(scores.postal_code_match * 0.4)
        if scores.city_match > 0:
            address_components.append(scores.city_match * 0.3)
        if scores.name_jaro_winkler > 0:
            address_components.append(scores.name_jaro_winkler * 0.3)

        scores.address_similarity = sum(address_components) if address_components else 0.0

        return scores

    def _jaro_winkler(self, s1: str, s2: str) -> float:
        """Compute Jaro-Winkler similarity."""
        if not s1 or not s2:
            return 0.0
        try:
            import jellyfish

            return jellyfish.jaro_winkler_similarity(s1.lower(), s2.lower())
        except ImportError:
            # Fallback to basic comparison
            return 1.0 if s1.lower() == s2.lower() else 0.0

    def _token_jaccard(self, s1: str, s2: str) -> float:
        """Compute Jaccard similarity of tokens."""
        if not s1 or not s2:
            return 0.0

        tokens1 = set(s1.lower().split())
        tokens2 = set(s2.lower().split())

        if not tokens1 or not tokens2:
            return 0.0

        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    def _levenshtein_normalized(self, s1: str, s2: str) -> float:
        """Compute normalized Levenshtein similarity (1 - normalized distance)."""
        if not s1 or not s2:
            return 0.0
        try:
            import jellyfish

            distance = jellyfish.levenshtein_distance(s1.lower(), s2.lower())
            max_len = max(len(s1), len(s2))
            return 1.0 - (distance / max_len) if max_len > 0 else 0.0
        except ImportError:
            return 1.0 if s1.lower() == s2.lower() else 0.0
