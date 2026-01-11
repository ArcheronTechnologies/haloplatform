"""
Fusion layer for cross-domain intelligence correlation.

Provides capabilities to:
- Correlate entities across different data domains
- Analyze temporal patterns and sequences
- Track flows (financial, physical, organizational)
- Generate network visualizations
"""

from halo.fusion.engine import (
    FusionEngine,
    CorrelationResult,
    DomainCorrelation,
)
from halo.fusion.temporal import (
    TemporalAnalyzer,
    TimelineEvent,
    TemporalPattern,
)
from halo.fusion.flow import (
    FlowAnalyzer,
    FlowPath,
    FlowNode,
)

__all__ = [
    # Engine
    "FusionEngine",
    "CorrelationResult",
    "DomainCorrelation",
    # Temporal
    "TemporalAnalyzer",
    "TimelineEvent",
    "TemporalPattern",
    # Flow
    "FlowAnalyzer",
    "FlowPath",
    "FlowNode",
]
