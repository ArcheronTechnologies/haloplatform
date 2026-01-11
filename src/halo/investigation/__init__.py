"""
Investigation management module for Halo platform.

Provides:
- Case management (create, assign, track)
- Evidence collection and linking
- Timeline reconstruction
- Investigation workflows
- Report generation
"""

from halo.investigation.case_manager import (
    CaseManager,
    Case,
    CaseStatus,
    CasePriority,
    CaseType,
)
from halo.investigation.evidence import (
    Evidence,
    EvidenceType,
    EvidenceChain,
    EvidenceCollector,
)
from halo.investigation.timeline import (
    TimelineEvent,
    Timeline,
    TimelineBuilder,
)
from halo.investigation.workflow import (
    InvestigationWorkflow,
    WorkflowStep,
    WorkflowStatus,
)

__all__ = [
    # Case Management
    "CaseManager",
    "Case",
    "CaseStatus",
    "CasePriority",
    "CaseType",
    # Evidence
    "Evidence",
    "EvidenceType",
    "EvidenceChain",
    "EvidenceCollector",
    # Timeline
    "TimelineEvent",
    "Timeline",
    "TimelineBuilder",
    # Workflow
    "InvestigationWorkflow",
    "WorkflowStep",
    "WorkflowStatus",
]
