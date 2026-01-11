"""
Anomaly detection module for financial transaction analysis.

Provides:
- Transaction pattern detection (velocity, structuring, round amounts)
- Statistical anomaly detection
- Network-based analysis
- Rule-based alert generation
- Risk scoring
"""

from halo.anomaly.transaction_patterns import (
    TransactionPatternDetector,
    PatternMatch,
    PatternType,
)
from halo.anomaly.scorer import RiskScorer, RiskScore
from halo.anomaly.rules_engine import RulesEngine, Rule

__all__ = [
    "TransactionPatternDetector",
    "PatternMatch",
    "PatternType",
    "RiskScorer",
    "RiskScore",
    "RulesEngine",
    "Rule",
]
