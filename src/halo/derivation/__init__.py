"""
Derived fact computation module.

Computes derived facts from source facts:
- Risk scores for persons and companies
- Director velocity (changes per year)
- Shell company indicators
- Network cluster assignments
- Address statistics

Supports both:
1. In-memory calculation (for testing/small datasets)
2. Database-backed derivation (for nightly batch jobs)
"""

from halo.derivation.risk_score import (
    PersonRiskScorer,
    CompanyRiskScorer,
    AddressRiskScorer,
    RiskFactors,
    RiskScoreResult,
)
from halo.derivation.velocity import (
    DirectorVelocityCalculator,
    DirectorChange,
    VelocityResult,
)
from halo.derivation.shell_indicators import (
    ShellIndicatorCalculator,
    ShellIndicators,
)
from halo.derivation.scheduler import (
    DerivationScheduler,
    DerivationJob,
    DerivationResult,
    DerivationRule,
    DerivationRuleType,
)
from halo.derivation.db_service import (
    DerivationDBService,
    DerivationJobStats,
    run_nightly_derivation,
)

__all__ = [
    # Risk scoring
    "PersonRiskScorer",
    "CompanyRiskScorer",
    "AddressRiskScorer",
    "RiskFactors",
    "RiskScoreResult",
    # Director velocity
    "DirectorVelocityCalculator",
    "DirectorChange",
    "VelocityResult",
    # Shell indicators
    "ShellIndicatorCalculator",
    "ShellIndicators",
    # Scheduler (in-memory)
    "DerivationScheduler",
    "DerivationJob",
    "DerivationResult",
    "DerivationRule",
    "DerivationRuleType",
    # Database service
    "DerivationDBService",
    "DerivationJobStats",
    "run_nightly_derivation",
]
