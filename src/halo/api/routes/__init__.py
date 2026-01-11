"""
API route modules.
"""

from halo.api.routes.entities import router as entities_router
from halo.api.routes.search import router as search_router
from halo.api.routes.alerts import router as alerts_router
from halo.api.routes.cases import router as cases_router
from halo.api.routes.audit import router as audit_router
from halo.api.routes.documents import router as documents_router
from halo.api.routes.auth import router as auth_router
from halo.api.routes.graph import router as graph_router
from halo.api.routes.intelligence import router as intelligence_router
from halo.api.routes.referrals import router as referrals_router
from halo.api.routes.evidence import router as evidence_router
from halo.api.routes.impact import router as impact_router
from halo.api.routes.resolution import router as resolution_router
from halo.api.routes.patterns import router as patterns_router
from halo.api.routes.lifecycle import router as lifecycle_router
from halo.api.routes.dashboard import router as dashboard_router
from halo.api.routes.sars import router as sars_router
from halo.api.routes.users import router as users_router

__all__ = [
    "entities_router",
    "search_router",
    "alerts_router",
    "cases_router",
    "audit_router",
    "documents_router",
    "auth_router",
    "graph_router",
    "intelligence_router",
    "referrals_router",
    "evidence_router",
    "impact_router",
    "resolution_router",
    "patterns_router",
    "lifecycle_router",
    "dashboard_router",
    "sars_router",
    "users_router",
]
