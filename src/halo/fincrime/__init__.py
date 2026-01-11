"""
Financial crime detection module for Halo platform.

Provides:
- AML (Anti-Money Laundering) pattern detection
- SAR (Suspicious Activity Report) generation
- Transaction monitoring rules
- Risk scoring for entities and transactions
- Regulatory compliance helpers (Swedish FI, EU AMLD)
"""

from halo.fincrime.aml_patterns import (
    AMLPattern,
    AMLPatternDetector,
    PatternMatch,
    StructuringDetector,
    LayeringDetector,
    RapidMovementDetector,
    RoundTripDetector,
    SmurfingDetector,
)
from halo.fincrime.sar_generator import (
    SARGenerator,
    SARReport,
    SARStatus,
    SARType,
)
from halo.fincrime.risk_scoring import (
    EntityRiskScorer,
    TransactionRiskScorer,
    RiskScore,
    RiskFactor,
    RiskLevel,
)
from halo.fincrime.watchlist import (
    WatchlistChecker,
    WatchlistMatch,
    WatchlistType,
)

__all__ = [
    # AML Patterns
    "AMLPattern",
    "AMLPatternDetector",
    "PatternMatch",
    "StructuringDetector",
    "LayeringDetector",
    "RapidMovementDetector",
    "RoundTripDetector",
    "SmurfingDetector",
    # SAR
    "SARGenerator",
    "SARReport",
    "SARStatus",
    "SARType",
    # Risk Scoring
    "EntityRiskScorer",
    "TransactionRiskScorer",
    "RiskScore",
    "RiskFactor",
    "RiskLevel",
    # Watchlist
    "WatchlistChecker",
    "WatchlistMatch",
    "WatchlistType",
]
