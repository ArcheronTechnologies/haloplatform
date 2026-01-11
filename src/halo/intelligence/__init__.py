"""
Halo Intelligence Module.

Proactive detection framework with three layers:
- Layer 1: Anomaly Detection (statistical deviation)
- Layer 2: Pattern-Based (fraud typology matching)
- Layer 3: Predictive (ML-based risk scoring)
"""

from halo.intelligence.anomaly import (
    AnomalyDetector,
    AnomalyScore,
    BaselineStats,
    ANOMALY_THRESHOLDS,
)
from halo.intelligence.patterns import (
    PatternMatcher,
    FraudPattern,
    FRAUD_PATTERNS,
)
from halo.intelligence.predictive import (
    RiskPredictor,
    FraudPrediction,
    propagate_risk,
    extract_graph_features,
)
from halo.intelligence.formation_agent import FormationAgentTracker
from halo.intelligence.sequence_detector import FraudSequenceDetector
from halo.intelligence.evasion import EvasionDetector
from halo.intelligence.sar_generator import SARGenerator
from halo.intelligence.konkurs import KonkursPrediction

__all__ = [
    # Layer 1: Anomaly
    "AnomalyDetector",
    "AnomalyScore",
    "BaselineStats",
    "ANOMALY_THRESHOLDS",
    # Layer 2: Pattern
    "PatternMatcher",
    "FraudPattern",
    "FRAUD_PATTERNS",
    # Layer 3: Predictive
    "RiskPredictor",
    "FraudPrediction",
    "propagate_risk",
    "extract_graph_features",
    # Advanced Features
    "FormationAgentTracker",
    "FraudSequenceDetector",
    "EvasionDetector",
    "SARGenerator",
    "KonkursPrediction",
]
