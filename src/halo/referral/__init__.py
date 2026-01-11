"""
Referral pipeline for multi-authority case routing.

Handles routing of detected intelligence to appropriate Swedish authorities:
- EBM (Ekobrottsmyndigheten) - Economic crime
- Skatteverket - Tax fraud
- Försäkringskassan - Welfare fraud
- IVO - Healthcare fraud
- FIU - Financial Intelligence Unit (money laundering)
- Polisen - General criminal activity
"""

from halo.referral.pipeline import (
    ReferralPipeline,
    ReferralRequest,
    ReferralResult,
    ReferralStatus,
)
from halo.referral.router import (
    AuthorityRouter,
    Authority,
    RoutingDecision,
)
from halo.referral.formats import (
    ReferralFormatter,
    EBMFormat,
    SkatteverketFormat,
)

__all__ = [
    "ReferralPipeline",
    "ReferralRequest",
    "ReferralResult",
    "ReferralStatus",
    "AuthorityRouter",
    "Authority",
    "RoutingDecision",
    "ReferralFormatter",
    "EBMFormat",
    "SkatteverketFormat",
]
