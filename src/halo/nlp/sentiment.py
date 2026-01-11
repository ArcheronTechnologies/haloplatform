"""
Sentiment analysis for Swedish text.

Focused on detecting:
- Fear indicators
- Violence indicators
- Threat language
- Urgency/pressure

Used for risk scoring in financial crime and threat detection.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from halo.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""

    # Overall sentiment (-1 to 1)
    polarity: float

    # Specific indicators (0 to 1)
    fear_score: float
    violence_score: float
    urgency_score: float
    threat_score: float

    # Aggregate risk score
    risk_score: float

    # Detected keywords
    detected_keywords: list[str]

    @property
    def is_concerning(self) -> bool:
        """Check if the text shows concerning indicators."""
        return (
            self.fear_score > 0.5
            or self.violence_score > 0.5
            or self.threat_score > 0.5
        )


class SentimentAnalyzer:
    """
    Sentiment analyzer for Swedish text.

    Uses both keyword-based and ML-based analysis to detect
    concerning language patterns.
    """

    # Fear-related keywords (Swedish)
    FEAR_KEYWORDS = {
        "rädd",
        "rädsla",
        "skräck",
        "orolig",
        "oro",
        "ångest",
        "panik",
        "fruktan",
        "hotad",
        "farlig",
        "fara",
        "risk",
        "osäker",
        "nervös",
        "ängslig",
        "bekymrad",
        "desperat",
        "hjälp",
    }

    # Violence-related keywords (Swedish)
    VIOLENCE_KEYWORDS = {
        "slå",
        "mörda",
        "döda",
        "skada",
        "misshandla",
        "våld",
        "våldsam",
        "blod",
        "kniv",
        "vapen",
        "pistol",
        "gevär",
        "skjuta",
        "attackera",
        "angripa",
        "hota",
        "hämnd",
        "straffa",
        "tortera",
        "kidnappa",
        "bränna",
        "explodera",
        "bomba",
    }

    # Urgency-related keywords (Swedish)
    URGENCY_KEYWORDS = {
        "nu",
        "genast",
        "omedelbart",
        "snabbt",
        "fort",
        "brådskande",
        "akut",
        "måste",
        "tvungen",
        "deadline",
        "sista chansen",
        "snart",
        "idag",
        "ikväll",
        "strax",
    }

    # Threat indicators (Swedish)
    THREAT_KEYWORDS = {
        "om du inte",
        "annars",
        "konsekvenser",
        "ångra",
        "betala",
        "överför",
        "skicka pengar",
        "säg inget",
        "berätta inte",
        "hemlighet",
        "ingen får veta",
        "jag vet var",
        "jag hittar",
        "du kommer",
        "din familj",
        "dina barn",
        "ditt hus",
    }

    def __init__(self, model_path: Optional[Path] = None):
        """
        Initialize the sentiment analyzer.

        Args:
            model_path: Path to sentiment model (optional)
        """
        self.model_path = model_path
        self._model = None
        self._model_loaded = False

    def analyze(self, text: str) -> SentimentResult:
        """
        Analyze sentiment and risk indicators in text.

        Args:
            text: Input text

        Returns:
            SentimentResult with scores and detected keywords
        """
        text_lower = text.lower()
        detected_keywords = []

        # Calculate keyword-based scores
        fear_score = self._calculate_keyword_score(
            text_lower, self.FEAR_KEYWORDS, detected_keywords
        )
        violence_score = self._calculate_keyword_score(
            text_lower, self.VIOLENCE_KEYWORDS, detected_keywords
        )
        urgency_score = self._calculate_keyword_score(
            text_lower, self.URGENCY_KEYWORDS, detected_keywords
        )
        threat_score = self._calculate_keyword_score(
            text_lower, self.THREAT_KEYWORDS, detected_keywords
        )

        # Calculate overall polarity (simplified)
        polarity = self._calculate_polarity(text_lower)

        # Calculate aggregate risk score
        risk_score = self._calculate_risk_score(
            fear_score, violence_score, urgency_score, threat_score
        )

        return SentimentResult(
            polarity=polarity,
            fear_score=fear_score,
            violence_score=violence_score,
            urgency_score=urgency_score,
            threat_score=threat_score,
            risk_score=risk_score,
            detected_keywords=detected_keywords,
        )

    def _calculate_keyword_score(
        self,
        text: str,
        keywords: set,
        detected: list,
    ) -> float:
        """
        Calculate score based on keyword presence.

        Args:
            text: Lowercase text
            keywords: Set of keywords to check
            detected: List to append found keywords to

        Returns:
            Score from 0 to 1
        """
        found = []

        for keyword in keywords:
            if keyword in text:
                found.append(keyword)

        detected.extend(found)

        if not found:
            return 0.0

        # Score based on number of keywords found
        # More keywords = higher score, but diminishing returns
        count = len(found)
        max_count = len(keywords)

        # Use logarithmic scaling
        import math

        return min(1.0, math.log(count + 1) / math.log(max_count + 1) * 2)

    def _calculate_polarity(self, text: str) -> float:
        """
        Calculate overall sentiment polarity.

        Simplified approach using positive/negative word lists.

        Returns:
            Polarity from -1 (negative) to 1 (positive)
        """
        positive_words = {
            "bra",
            "fantastisk",
            "utmärkt",
            "glad",
            "lycklig",
            "underbar",
            "perfekt",
            "fin",
            "trevlig",
            "positiv",
            "succé",
            "framgång",
            "vänlig",
            "vacker",
            "rolig",
        }

        negative_words = {
            "dålig",
            "hemsk",
            "fruktansvärd",
            "ledsen",
            "olycklig",
            "besviken",
            "fel",
            "misslyckad",
            "ful",
            "elak",
            "dum",
            "svår",
            "jobbig",
            "problematisk",
            "katastrof",
        }

        pos_count = sum(1 for word in positive_words if word in text)
        neg_count = sum(1 for word in negative_words if word in text)

        total = pos_count + neg_count
        if total == 0:
            return 0.0

        return (pos_count - neg_count) / total

    def _calculate_risk_score(
        self,
        fear: float,
        violence: float,
        urgency: float,
        threat: float,
    ) -> float:
        """
        Calculate aggregate risk score.

        Weights different factors based on importance.

        Returns:
            Risk score from 0 to 1
        """
        # Weights for different factors
        weights = {
            "violence": 0.35,
            "threat": 0.30,
            "fear": 0.20,
            "urgency": 0.15,
        }

        score = (
            violence * weights["violence"]
            + threat * weights["threat"]
            + fear * weights["fear"]
            + urgency * weights["urgency"]
        )

        return min(1.0, score)
