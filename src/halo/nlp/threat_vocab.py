"""
Criminal and threat vocabulary detection for Swedish text.

Detects:
- Gang-related terminology
- Drug-related terminology
- Criminal slang (including Rinkebysvenska)
- Money laundering indicators
- Fraud indicators
"""

import logging
from dataclasses import dataclass
from typing import Optional

from flashtext import KeywordProcessor

logger = logging.getLogger(__name__)


@dataclass
class VocabMatch:
    """A vocabulary match in text."""

    keyword: str
    category: str
    start: int
    end: int
    context: str  # Surrounding text
    severity: str  # 'low', 'medium', 'high'


class ThreatVocabularyDetector:
    """
    Detects criminal and threat vocabulary in Swedish text.

    Uses FlashText for efficient multi-keyword matching.
    Includes:
    - Standard Swedish criminal vocabulary
    - Gang slang
    - Rinkebysvenska/förortssvenska terms
    - Financial crime indicators
    """

    def __init__(self):
        """Initialize the vocabulary detector with keyword databases."""
        self._processors: dict[str, KeywordProcessor] = {}
        self._severities: dict[str, str] = {}
        self._load_vocabularies()

    def _load_vocabularies(self):
        """Load all vocabulary databases."""
        # Gang-related vocabulary
        self._add_vocabulary(
            "gang",
            {
                # Standard Swedish
                "gäng": "high",
                "gangster": "high",
                "kriminell": "medium",
                "brottsling": "medium",
                "liga": "medium",
                # Slang
                "bransen": "high",  # Criminal underworld
                "gatan": "low",  # "The street"
                "adda": "medium",  # Adding to gang
                "hoppa av": "low",  # Leave gang
                # Gang names (examples - real list would be longer)
                "brödraskapet": "high",
                "bandidos": "high",
                "hells angels": "high",
            },
            severity_default="medium",
        )

        # Drug-related vocabulary
        self._add_vocabulary(
            "drugs",
            {
                # Standard Swedish
                "narkotika": "medium",
                "knark": "high",
                "drog": "medium",
                "langare": "high",
                "langning": "high",
                # Specific drugs
                "cannabis": "low",
                "marijuana": "low",
                "kokain": "high",
                "heroin": "high",
                "amfetamin": "high",
                "ecstasy": "medium",
                # Slang
                "gansen": "high",  # Hash
                "bansen": "high",  # Hash
                "tjansen": "high",  # Hash
                "röansen": "medium",  # Weed
                "pansen": "high",  # Speed
                "kansen": "high",  # Cocaine
                "bransen": "high",  # Brown heroin
            },
            severity_default="medium",
        )

        # Violence vocabulary
        self._add_vocabulary(
            "violence",
            {
                "skjutning": "high",
                "knivattack": "high",
                "misshandel": "high",
                "mord": "high",
                "dödshot": "high",
                "utpressning": "high",
                "kidnappning": "high",
                "tortyr": "high",
                "sprängning": "high",
                "bomb": "high",
                "vapen": "medium",
                "pistol": "high",
                "gevär": "high",
                "automatvapen": "high",
                "handgranat": "high",
                # Slang
                "lansen": "high",  # Gun
                "buransen": "high",  # Gun
                "knansen": "medium",  # Knife
            },
            severity_default="high",
        )

        # Money laundering indicators
        self._add_vocabulary(
            "money_laundering",
            {
                "penningtvätt": "high",
                "svarta pengar": "high",
                "kontant": "low",
                "bulvan": "high",
                "målvakt": "high",
                "skalbolag": "high",
                "brevlådeföretag": "high",
                "fakturaskojeri": "high",
                "överföring utomlands": "medium",
                "kryptovaluta": "low",
                "bitcoin": "low",
                "hawala": "high",
                "smurfa": "high",  # Structuring
                "splitta betalningar": "medium",
            },
            severity_default="medium",
        )

        # Fraud indicators
        self._add_vocabulary(
            "fraud",
            {
                "bedrägeri": "high",
                "bluff": "medium",
                "scam": "high",
                "lurad": "medium",
                "förfalskning": "high",
                "id-kapning": "high",
                "identitetsstöld": "high",
                "kortbedrägeri": "high",
                "fakturaskojeri": "high",
                "ponzibedrägeri": "high",
                "pyramidspel": "medium",
                "insiderhandel": "high",
                "kursmanipulation": "high",
            },
            severity_default="medium",
        )

        # Rinkebysvenska / förortssvenska (suburban slang)
        # These terms aren't inherently criminal but appear in
        # criminal contexts and can be useful for understanding
        self._add_vocabulary(
            "slang",
            {
                "gansen": "low",  # A lot / hash
                "shansen": "low",  # Thing
                "ansen": "low",  # Suffix for nouns
                "sansen": "low",
                "bansen": "low",
                "para": "low",  # Money
                "aina": "low",  # Police
                "sansen": "low",  # Police
                "gansen": "low",  # Run/go
                "wallah": "low",  # I swear
                "akhi": "low",  # Brother
                "habibi": "low",  # Friend
                "yalla": "low",  # Come on
                "shoo": "low",  # What
            },
            severity_default="low",
        )

    def _add_vocabulary(
        self,
        category: str,
        keywords: dict[str, str],
        severity_default: str = "medium",
    ):
        """
        Add a vocabulary category.

        Args:
            category: Category name
            keywords: Dict of keyword -> severity
            severity_default: Default severity if not specified
        """
        processor = KeywordProcessor(case_sensitive=False)

        for keyword, severity in keywords.items():
            processor.add_keyword(keyword)
            self._severities[f"{category}:{keyword}"] = severity

        self._processors[category] = processor

    def detect(
        self,
        text: str,
        categories: Optional[list[str]] = None,
        min_severity: str = "low",
    ) -> list[VocabMatch]:
        """
        Detect vocabulary matches in text.

        Args:
            text: Input text
            categories: Categories to check (None = all)
            min_severity: Minimum severity to return

        Returns:
            List of VocabMatch objects
        """
        severity_order = {"low": 0, "medium": 1, "high": 2}
        min_sev = severity_order.get(min_severity, 0)

        matches = []
        categories = categories or list(self._processors.keys())

        for category in categories:
            processor = self._processors.get(category)
            if not processor:
                continue

            # FlashText returns (keyword, start, end) tuples
            keywords_found = processor.extract_keywords(text, span_info=True)

            for keyword, start, end in keywords_found:
                severity_key = f"{category}:{keyword.lower()}"
                severity = self._severities.get(severity_key, "medium")

                if severity_order.get(severity, 0) < min_sev:
                    continue

                # Get context (50 chars before and after)
                context_start = max(0, start - 50)
                context_end = min(len(text), end + 50)
                context = text[context_start:context_end]

                matches.append(
                    VocabMatch(
                        keyword=keyword,
                        category=category,
                        start=start,
                        end=end,
                        context=context,
                        severity=severity,
                    )
                )

        # Sort by severity (high first) then position
        matches.sort(
            key=lambda m: (-severity_order.get(m.severity, 0), m.start)
        )

        return matches

    def get_risk_score(self, text: str) -> float:
        """
        Calculate overall risk score based on vocabulary.

        Returns:
            Risk score from 0 to 1
        """
        matches = self.detect(text, min_severity="low")

        if not matches:
            return 0.0

        severity_scores = {"low": 0.2, "medium": 0.5, "high": 1.0}

        # Sum scores with diminishing returns
        total = 0.0
        for i, match in enumerate(matches):
            # Each subsequent match contributes less
            weight = 1.0 / (i + 1)
            total += severity_scores.get(match.severity, 0.5) * weight

        # Normalize to 0-1 range
        return min(1.0, total / 3.0)

    def get_categories(self) -> list[str]:
        """Get list of available vocabulary categories."""
        return list(self._processors.keys())
