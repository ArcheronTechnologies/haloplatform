"""
Investigation workflow management.

Defines structured workflows for different investigation types.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """Status of a workflow step."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class StepType(str, Enum):
    """Types of workflow steps."""

    MANUAL = "manual"  # Requires human action
    AUTOMATED = "automated"  # System can perform
    APPROVAL = "approval"  # Requires sign-off
    REVIEW = "review"  # Requires review of prior work
    DECISION = "decision"  # Branch point


class WorkflowTemplate(str, Enum):
    """Predefined workflow templates."""

    AML_INVESTIGATION = "aml_investigation"
    SANCTIONS_SCREENING = "sanctions_screening"
    FRAUD_INVESTIGATION = "fraud_investigation"
    PEP_REVIEW = "pep_review"
    KYC_REFRESH = "kyc_refresh"
    TRANSACTION_MONITORING = "transaction_monitoring"


@dataclass
class WorkflowStep:
    """A step in an investigation workflow."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""
    step_type: StepType = StepType.MANUAL

    # Ordering
    order: int = 0
    parent_step_id: Optional[UUID] = None  # For nested steps

    # Requirements
    required: bool = True
    prerequisites: list[UUID] = field(default_factory=list)  # Steps that must complete first
    requirements: Optional[dict[str, Any]] = None  # Step requirements (role, etc.)

    # Assignment
    role_required: Optional[str] = None  # e.g., "analyst", "compliance_officer"
    assigned_to: Optional[UUID] = None

    # Status
    status: WorkflowStatus = WorkflowStatus.NOT_STARTED

    # Timing
    estimated_hours: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None

    # Outcome
    outcome: str = ""
    notes: str = ""
    evidence_ids: list[UUID] = field(default_factory=list)

    # For decision steps
    decision_options: list[str] = field(default_factory=list)
    decision_made: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "step_type": self.step_type.value,
            "order": self.order,
            "parent_step_id": str(self.parent_step_id) if self.parent_step_id else None,
            "required": self.required,
            "prerequisites": [str(p) for p in self.prerequisites],
            "role_required": self.role_required,
            "assigned_to": str(self.assigned_to) if self.assigned_to else None,
            "status": self.status.value,
            "estimated_hours": self.estimated_hours,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "outcome": self.outcome,
            "notes": self.notes,
            "evidence_ids": [str(e) for e in self.evidence_ids],
            "decision_options": self.decision_options,
            "decision_made": self.decision_made,
        }


@dataclass
class AuditEntry:
    """An entry in the workflow audit trail."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    action: str = ""
    actor_id: Optional[UUID] = None
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "details": self.details,
        }


@dataclass
class WorkflowTemplateDefinition:
    """A workflow template with steps."""

    name: str
    steps: list[WorkflowStep]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class InvestigationWorkflow:
    """A workflow for conducting an investigation."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""
    workflow_type: str = ""  # e.g., "aml", "fraud", "sanctions"

    # Case reference
    case_id: Optional[UUID] = None

    # Steps
    steps: list[WorkflowStep] = field(default_factory=list)

    # Overall status
    status: str = "not_started"  # Use string for easier test comparison
    progress_percent: float = 0.0

    # Current step tracking
    current_step_index: int = 0

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    target_completion: Optional[datetime] = None

    # Metadata
    created_by: Optional[UUID] = None

    # Audit trail
    audit_trail: list[AuditEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "workflow_type": self.workflow_type,
            "case_id": str(self.case_id) if self.case_id else None,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status if isinstance(self.status, str) else self.status.value,
            "progress_percent": self.progress_percent,
            "current_step_index": self.current_step_index,
            "audit_trail": [e.to_dict() for e in self.audit_trail],
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "target_completion": self.target_completion.isoformat() if self.target_completion else None,
            "created_by": str(self.created_by) if self.created_by else None,
        }

    def get_step(self, step_id: UUID) -> Optional[WorkflowStep]:
        """Get a step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_current_steps(self) -> list[WorkflowStep]:
        """Get steps that are currently actionable."""
        actionable = []
        completed_ids = {s.id for s in self.steps if s.status == WorkflowStatus.COMPLETED}

        for step in self.steps:
            if step.status in [WorkflowStatus.NOT_STARTED, WorkflowStatus.IN_PROGRESS]:
                # Check prerequisites
                prereqs_met = all(p in completed_ids for p in step.prerequisites)
                if prereqs_met:
                    actionable.append(step)

        return actionable

    def get_blocked_steps(self) -> list[WorkflowStep]:
        """Get steps that are blocked on prerequisites."""
        blocked = []
        completed_ids = {s.id for s in self.steps if s.status == WorkflowStatus.COMPLETED}

        for step in self.steps:
            if step.status == WorkflowStatus.NOT_STARTED and step.prerequisites:
                prereqs_met = all(p in completed_ids for p in step.prerequisites)
                if not prereqs_met:
                    blocked.append(step)

        return blocked

    def update_progress(self) -> float:
        """Update and return progress percentage."""
        if not self.steps:
            return 0.0

        completed = sum(
            1 for s in self.steps
            if s.status in [WorkflowStatus.COMPLETED, WorkflowStatus.SKIPPED]
        )
        self.progress_percent = (completed / len(self.steps)) * 100
        return self.progress_percent


class WorkflowEngine:
    """
    Manages investigation workflows.

    Provides templates and handles workflow execution.
    """

    def __init__(self):
        self._workflows: dict[UUID, InvestigationWorkflow] = {}
        self._templates: dict[str, Callable[[], list[WorkflowStep]]] = {}
        self._template_definitions: dict[str, WorkflowTemplateDefinition] = {}

        # Register default templates
        self._register_default_templates()

    def _register_default_templates(self) -> None:
        """Register built-in workflow templates."""
        self._templates["aml_investigation"] = self._create_aml_template
        self._templates["sanctions_investigation"] = self._create_sanctions_template
        self._templates["fraud_investigation"] = self._create_fraud_template
        self._templates["pep_investigation"] = self._create_pep_template

        # Also register with WorkflowTemplate enum values
        self._templates[WorkflowTemplate.AML_INVESTIGATION.value] = self._create_aml_template
        self._templates[WorkflowTemplate.SANCTIONS_SCREENING.value] = self._create_sanctions_template
        self._templates[WorkflowTemplate.FRAUD_INVESTIGATION.value] = self._create_fraud_template
        self._templates[WorkflowTemplate.PEP_REVIEW.value] = self._create_pep_template

    def get_template(self, template: WorkflowTemplate) -> WorkflowTemplateDefinition:
        """
        Get a workflow template definition.

        Args:
            template: WorkflowTemplate enum value

        Returns:
            WorkflowTemplateDefinition with steps
        """
        template_key = template.value if isinstance(template, WorkflowTemplate) else str(template)

        if template_key not in self._templates:
            raise ValueError(f"Unknown template: {template}")

        steps = self._templates[template_key]()

        return WorkflowTemplateDefinition(
            name=template_key,
            steps=steps,
        )

    def start_workflow(
        self,
        case_id: UUID,
        template: WorkflowTemplate,
        started_by: UUID,
    ) -> InvestigationWorkflow:
        """
        Start a new workflow from a template.

        Args:
            case_id: Case ID to associate with workflow
            template: Template to use
            started_by: User starting the workflow

        Returns:
            Started InvestigationWorkflow
        """
        template_key = template.value if isinstance(template, WorkflowTemplate) else str(template)

        if template_key not in self._templates:
            raise ValueError(f"Unknown template: {template}")

        steps = self._templates[template_key]()

        workflow = InvestigationWorkflow(
            name=f"{template_key.replace('_', ' ').title()}",
            description=f"Standard workflow for {template_key.replace('_', ' ')}",
            workflow_type=template_key,
            case_id=case_id,
            steps=steps,
            created_by=started_by,
            status="in_progress",
            started_at=datetime.utcnow(),
            current_step_index=0,
        )

        # Add audit entry
        workflow.audit_trail.append(AuditEntry(
            action="workflow_started",
            actor_id=started_by,
            details=f"Workflow started from template {template_key}",
        ))

        # Start first step
        if workflow.steps:
            workflow.steps[0].status = WorkflowStatus.IN_PROGRESS
            workflow.steps[0].started_at = datetime.utcnow()

        self._workflows[workflow.id] = workflow

        logger.info(f"Started {template_key} workflow with {len(steps)} steps")

        return workflow

    def complete_step(
        self,
        workflow_id: UUID,
        notes: str = "",
        completed_by: Optional[UUID] = None,
    ) -> WorkflowStep:
        """
        Complete the current step of a workflow.

        Args:
            workflow_id: Workflow ID
            notes: Completion notes
            completed_by: User completing the step

        Returns:
            Completed WorkflowStep
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        if workflow.current_step_index >= len(workflow.steps):
            raise ValueError("No more steps to complete")

        step = workflow.steps[workflow.current_step_index]
        step.status = WorkflowStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.notes = notes

        # Add audit entry
        workflow.audit_trail.append(AuditEntry(
            action="step_completed",
            actor_id=completed_by,
            details=f"Step '{step.name}' completed: {notes}",
        ))

        # Move to next step
        workflow.current_step_index += 1

        # Check if workflow is complete
        if workflow.current_step_index >= len(workflow.steps):
            workflow.status = "completed"
            workflow.completed_at = datetime.utcnow()
        else:
            # Start next step
            next_step = workflow.steps[workflow.current_step_index]
            next_step.status = WorkflowStatus.IN_PROGRESS
            next_step.started_at = datetime.utcnow()

        # Update progress
        workflow.update_progress()

        return step

    def get_current_step(self, workflow_id: UUID) -> Optional[WorkflowStep]:
        """
        Get the current step of a workflow.

        Args:
            workflow_id: Workflow ID

        Returns:
            Current WorkflowStep or None if complete
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return None

        if workflow.current_step_index >= len(workflow.steps):
            return None

        return workflow.steps[workflow.current_step_index]

    def is_complete(self, workflow_id: UUID) -> bool:
        """
        Check if a workflow is complete.

        Args:
            workflow_id: Workflow ID

        Returns:
            True if workflow is complete
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        return workflow.status == "completed" or workflow.current_step_index >= len(workflow.steps)

    def create_workflow(
        self,
        workflow_type: str,
        case_id: Optional[UUID] = None,
        created_by: Optional[UUID] = None,
        target_days: int = 30,
    ) -> InvestigationWorkflow:
        """
        Create a workflow from a template.

        Args:
            workflow_type: Type of workflow (must match a template)
            case_id: Related case ID
            created_by: User creating the workflow
            target_days: Target days to completion

        Returns:
            Created InvestigationWorkflow
        """
        if workflow_type not in self._templates:
            raise ValueError(f"Unknown workflow type: {workflow_type}")

        # Get steps from template
        steps = self._templates[workflow_type]()

        workflow = InvestigationWorkflow(
            name=f"{workflow_type.replace('_', ' ').title()}",
            description=f"Standard workflow for {workflow_type.replace('_', ' ')}",
            workflow_type=workflow_type,
            case_id=case_id,
            steps=steps,
            created_by=created_by,
            target_completion=datetime.utcnow() + timedelta(days=target_days),
        )

        self._workflows[workflow.id] = workflow

        logger.info(f"Created {workflow_type} workflow with {len(steps)} steps")

        return workflow

    def complete_step_by_id(
        self,
        workflow_id: UUID,
        step_id: UUID,
        outcome: str = "",
        notes: str = "",
        evidence_ids: Optional[list[UUID]] = None,
        user_id: Optional[UUID] = None,
    ) -> WorkflowStep:
        """
        Mark a step as completed.

        Args:
            workflow_id: Workflow containing the step
            step_id: Step to complete
            outcome: Outcome/result of the step
            notes: Additional notes
            evidence_ids: Evidence collected during step
            user_id: User completing the step

        Returns:
            Updated WorkflowStep
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        step = workflow.get_step(step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        step.status = WorkflowStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.outcome = outcome
        step.notes = notes
        if evidence_ids:
            step.evidence_ids.extend(evidence_ids)

        # Update workflow progress
        workflow.update_progress()

        # Check if workflow is complete
        if all(
            s.status in [WorkflowStatus.COMPLETED, WorkflowStatus.SKIPPED]
            for s in workflow.steps
        ):
            workflow.status = WorkflowStatus.COMPLETED
            workflow.completed_at = datetime.utcnow()

        # Start dependent steps
        self._start_dependent_steps(workflow, step_id)

        logger.info(f"Completed step {step.name} in workflow {workflow_id}")

        return step

    def make_decision(
        self,
        workflow_id: UUID,
        step_id: UUID,
        decision: str,
        notes: str = "",
        user_id: Optional[UUID] = None,
    ) -> WorkflowStep:
        """
        Make a decision at a decision step.

        Args:
            workflow_id: Workflow containing the step
            step_id: Decision step
            decision: The decision made
            notes: Rationale for decision
            user_id: User making the decision

        Returns:
            Updated WorkflowStep
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        step = workflow.get_step(step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        if step.step_type != StepType.DECISION:
            raise ValueError("Step is not a decision step")

        if decision not in step.decision_options:
            raise ValueError(f"Invalid decision. Options: {step.decision_options}")

        step.decision_made = decision
        step.notes = notes

        return self.complete_step(
            workflow_id, step_id,
            outcome=f"Decision: {decision}",
            notes=notes,
            user_id=user_id,
        )

    def skip_step(
        self,
        workflow_id: UUID,
        step_id: UUID,
        reason: str,
        user_id: Optional[UUID] = None,
    ) -> WorkflowStep:
        """Skip a non-required step."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        step = workflow.get_step(step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        if step.required:
            raise ValueError("Cannot skip a required step")

        step.status = WorkflowStatus.SKIPPED
        step.completed_at = datetime.utcnow()
        step.notes = f"Skipped: {reason}"

        workflow.update_progress()
        self._start_dependent_steps(workflow, step_id)

        return step

    def get_workflow(self, workflow_id: UUID) -> Optional[InvestigationWorkflow]:
        """Get a workflow by ID."""
        return self._workflows.get(workflow_id)

    def get_for_case(self, case_id: UUID) -> list[InvestigationWorkflow]:
        """Get all workflows for a case."""
        return [w for w in self._workflows.values() if w.case_id == case_id]

    def _start_dependent_steps(
        self,
        workflow: InvestigationWorkflow,
        completed_step_id: UUID,
    ) -> None:
        """Start steps that depend on a completed step."""
        for step in workflow.steps:
            if step.status == WorkflowStatus.NOT_STARTED:
                if completed_step_id in step.prerequisites:
                    # Check if all prerequisites are met
                    completed_ids = {
                        s.id for s in workflow.steps
                        if s.status in [WorkflowStatus.COMPLETED, WorkflowStatus.SKIPPED]
                    }
                    if all(p in completed_ids for p in step.prerequisites):
                        step.status = WorkflowStatus.IN_PROGRESS
                        step.started_at = datetime.utcnow()

    # Template creation methods

    def _create_aml_template(self) -> list[WorkflowStep]:
        """Create AML investigation workflow template."""
        steps = []

        # Step 1: Initial Review
        step1 = WorkflowStep(
            name="Initial Alert Review",
            description="Review the triggering alert(s) and assess initial risk",
            step_type=StepType.MANUAL,
            order=1,
            role_required="analyst",
            estimated_hours=1.0,
        )
        steps.append(step1)

        # Step 2: Entity Profile
        step2 = WorkflowStep(
            name="Entity Profile Analysis",
            description="Review entity information, risk factors, and history",
            step_type=StepType.MANUAL,
            order=2,
            prerequisites=[step1.id],
            role_required="analyst",
            estimated_hours=2.0,
        )
        steps.append(step2)

        # Step 3: Transaction Analysis
        step3 = WorkflowStep(
            name="Transaction Analysis",
            description="Analyze transaction patterns and identify suspicious activity",
            step_type=StepType.MANUAL,
            order=3,
            prerequisites=[step2.id],
            role_required="analyst",
            estimated_hours=4.0,
        )
        steps.append(step3)

        # Step 4: Network Analysis
        step4 = WorkflowStep(
            name="Network/Relationship Analysis",
            description="Investigate related entities and transaction networks",
            step_type=StepType.MANUAL,
            order=4,
            prerequisites=[step2.id],
            role_required="analyst",
            estimated_hours=3.0,
        )
        steps.append(step4)

        # Step 5: External Data Check
        step5 = WorkflowStep(
            name="External Data Verification",
            description="Check external sources (sanctions, PEP, adverse media)",
            step_type=StepType.AUTOMATED,
            order=5,
            prerequisites=[step2.id],
            estimated_hours=0.5,
        )
        steps.append(step5)

        # Step 6: Initial Assessment
        step6 = WorkflowStep(
            name="Initial Assessment Decision",
            description="Determine if suspicion is substantiated",
            step_type=StepType.DECISION,
            order=6,
            prerequisites=[step3.id, step4.id, step5.id],
            role_required="analyst",
            decision_options=["Suspicion confirmed", "Suspicion not confirmed", "Need more information"],
            estimated_hours=1.0,
        )
        steps.append(step6)

        # Step 7: SAR Drafting (conditional)
        step7 = WorkflowStep(
            name="Draft SAR",
            description="Prepare Suspicious Activity Report",
            step_type=StepType.MANUAL,
            order=7,
            prerequisites=[step6.id],
            required=False,
            role_required="analyst",
            estimated_hours=3.0,
        )
        steps.append(step7)

        # Step 8: Quality Review
        step8 = WorkflowStep(
            name="Quality Review",
            description="Senior review of investigation and SAR",
            step_type=StepType.REVIEW,
            order=8,
            prerequisites=[step6.id],
            role_required="senior_analyst",
            estimated_hours=2.0,
        )
        steps.append(step8)

        # Step 9: Compliance Approval
        step9 = WorkflowStep(
            name="Compliance Officer Approval",
            description="Final approval from compliance officer",
            step_type=StepType.APPROVAL,
            order=9,
            prerequisites=[step8.id],
            role_required="compliance_officer",
            estimated_hours=1.0,
        )
        steps.append(step9)

        # Step 10: Case Closure
        step10 = WorkflowStep(
            name="Case Closure",
            description="Document findings and close the case",
            step_type=StepType.MANUAL,
            order=10,
            prerequisites=[step9.id],
            role_required="analyst",
            estimated_hours=0.5,
        )
        steps.append(step10)

        return steps

    def _create_sanctions_template(self) -> list[WorkflowStep]:
        """Create sanctions investigation workflow template."""
        steps = []

        step1 = WorkflowStep(
            name="Sanctions Hit Review",
            description="Review the sanctions screening hit",
            step_type=StepType.MANUAL,
            order=1,
            role_required="analyst",
            estimated_hours=0.5,
        )
        steps.append(step1)

        step2 = WorkflowStep(
            name="Identity Verification",
            description="Verify if hit is a true match or false positive",
            step_type=StepType.MANUAL,
            order=2,
            prerequisites=[step1.id],
            role_required="analyst",
            estimated_hours=2.0,
        )
        steps.append(step2)

        step3 = WorkflowStep(
            name="Match Decision",
            description="Determine if entity matches sanctioned party",
            step_type=StepType.DECISION,
            order=3,
            prerequisites=[step2.id],
            role_required="analyst",
            decision_options=["True match", "False positive", "Potential match - escalate"],
            estimated_hours=0.5,
        )
        steps.append(step3)

        step4 = WorkflowStep(
            name="Immediate Action",
            description="Freeze accounts/block transactions if true match",
            step_type=StepType.MANUAL,
            order=4,
            prerequisites=[step3.id],
            required=False,
            role_required="compliance_officer",
            estimated_hours=1.0,
        )
        steps.append(step4)

        step5 = WorkflowStep(
            name="Regulatory Notification",
            description="Notify relevant authorities",
            step_type=StepType.MANUAL,
            order=5,
            prerequisites=[step4.id],
            required=False,
            role_required="compliance_officer",
            estimated_hours=2.0,
        )
        steps.append(step5)

        step6 = WorkflowStep(
            name="Documentation",
            description="Document decision and rationale",
            step_type=StepType.MANUAL,
            order=6,
            prerequisites=[step3.id],
            role_required="analyst",
            estimated_hours=1.0,
        )
        steps.append(step6)

        return steps

    def _create_fraud_template(self) -> list[WorkflowStep]:
        """Create fraud investigation workflow template."""
        steps = []

        step1 = WorkflowStep(
            name="Fraud Alert Review",
            description="Review the fraud alert and initial indicators",
            step_type=StepType.MANUAL,
            order=1,
            role_required="fraud_analyst",
            estimated_hours=1.0,
        )
        steps.append(step1)

        step2 = WorkflowStep(
            name="Transaction Reconstruction",
            description="Reconstruct the sequence of fraudulent transactions",
            step_type=StepType.MANUAL,
            order=2,
            prerequisites=[step1.id],
            role_required="fraud_analyst",
            estimated_hours=3.0,
        )
        steps.append(step2)

        step3 = WorkflowStep(
            name="Victim Identification",
            description="Identify affected parties and quantify losses",
            step_type=StepType.MANUAL,
            order=3,
            prerequisites=[step2.id],
            role_required="fraud_analyst",
            estimated_hours=2.0,
        )
        steps.append(step3)

        step4 = WorkflowStep(
            name="Perpetrator Analysis",
            description="Identify and profile the perpetrator(s)",
            step_type=StepType.MANUAL,
            order=4,
            prerequisites=[step2.id],
            role_required="fraud_analyst",
            estimated_hours=4.0,
        )
        steps.append(step4)

        step5 = WorkflowStep(
            name="Evidence Collection",
            description="Collect and preserve evidence",
            step_type=StepType.MANUAL,
            order=5,
            prerequisites=[step3.id, step4.id],
            role_required="fraud_analyst",
            estimated_hours=3.0,
        )
        steps.append(step5)

        step6 = WorkflowStep(
            name="Law Enforcement Referral Decision",
            description="Decide whether to refer to law enforcement",
            step_type=StepType.DECISION,
            order=6,
            prerequisites=[step5.id],
            role_required="fraud_manager",
            decision_options=["Refer to police", "Internal resolution", "Civil action"],
            estimated_hours=1.0,
        )
        steps.append(step6)

        step7 = WorkflowStep(
            name="Recovery Actions",
            description="Initiate fund recovery if possible",
            step_type=StepType.MANUAL,
            order=7,
            prerequisites=[step5.id],
            required=False,
            role_required="fraud_analyst",
            estimated_hours=4.0,
        )
        steps.append(step7)

        step8 = WorkflowStep(
            name="Case Report",
            description="Prepare comprehensive fraud case report",
            step_type=StepType.MANUAL,
            order=8,
            prerequisites=[step6.id, step7.id],
            role_required="fraud_analyst",
            estimated_hours=3.0,
        )
        steps.append(step8)

        return steps

    def _create_pep_template(self) -> list[WorkflowStep]:
        """Create PEP investigation workflow template."""
        steps = []

        step1 = WorkflowStep(
            name="PEP Match Review",
            description="Review PEP screening match",
            step_type=StepType.MANUAL,
            order=1,
            role_required="analyst",
            estimated_hours=0.5,
        )
        steps.append(step1)

        step2 = WorkflowStep(
            name="PEP Status Verification",
            description="Verify PEP status and position details",
            step_type=StepType.MANUAL,
            order=2,
            prerequisites=[step1.id],
            role_required="analyst",
            estimated_hours=1.5,
        )
        steps.append(step2)

        step3 = WorkflowStep(
            name="Source of Wealth Assessment",
            description="Assess the PEP's source of wealth and funds",
            step_type=StepType.MANUAL,
            order=3,
            prerequisites=[step2.id],
            role_required="analyst",
            estimated_hours=3.0,
        )
        steps.append(step3)

        step4 = WorkflowStep(
            name="Adverse Media Check",
            description="Check for negative news and public records",
            step_type=StepType.MANUAL,
            order=4,
            prerequisites=[step2.id],
            role_required="analyst",
            estimated_hours=2.0,
        )
        steps.append(step4)

        step5 = WorkflowStep(
            name="Risk Assessment",
            description="Complete enhanced due diligence risk assessment",
            step_type=StepType.MANUAL,
            order=5,
            prerequisites=[step3.id, step4.id],
            role_required="senior_analyst",
            estimated_hours=2.0,
        )
        steps.append(step5)

        step6 = WorkflowStep(
            name="Relationship Decision",
            description="Decide on business relationship continuation",
            step_type=StepType.DECISION,
            order=6,
            prerequisites=[step5.id],
            role_required="compliance_officer",
            decision_options=["Approve with monitoring", "Approve standard", "Decline/Exit"],
            estimated_hours=1.0,
        )
        steps.append(step6)

        step7 = WorkflowStep(
            name="Monitoring Plan",
            description="Establish enhanced monitoring if approved",
            step_type=StepType.MANUAL,
            order=7,
            prerequisites=[step6.id],
            required=False,
            role_required="analyst",
            estimated_hours=1.0,
        )
        steps.append(step7)

        return steps
