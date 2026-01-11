"""
Tests for investigation case management.

Tests:
- Case creation and lifecycle
- Evidence management
- Timeline reconstruction
- Workflow execution
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from halo.investigation.case_manager import (
    CaseManager,
    CaseType,
    CasePriority,
    CaseStatus,
    Case,
)
from halo.investigation.evidence import (
    EvidenceCollector,
    EvidenceType,
    Evidence,
)
from halo.investigation.timeline import TimelineBuilder, TimelineEvent
from halo.investigation.workflow import WorkflowEngine, WorkflowTemplate


class TestCaseManager:
    """Tests for case lifecycle management."""

    def test_create_case(self, case_manager):
        """Should create a new case with proper defaults."""
        case = case_manager.create_case(
            title="Test AML Investigation",
            case_type=CaseType.AML,
            priority=CasePriority.HIGH,
            description="Testing case creation",
        )

        assert case.id is not None
        assert case.case_number.startswith("AML-")
        assert case.status == CaseStatus.OPEN
        assert case.priority == CasePriority.HIGH

    def test_case_number_format(self, case_manager):
        """Case numbers should follow the format TYPE-YEAR-SEQUENCE."""
        case = case_manager.create_case(
            title="Test Case",
            case_type=CaseType.SANCTIONS,
            priority=CasePriority.MEDIUM,
        )

        # Format: SANCTIONS-2025-00001
        parts = case.case_number.split("-")
        assert len(parts) == 3
        assert parts[0] == "SANCTIONS"
        assert parts[1] == str(datetime.utcnow().year)
        assert len(parts[2]) == 5  # Zero-padded sequence

    def test_case_number_increments(self, case_manager):
        """Sequential cases should have incrementing numbers."""
        case1 = case_manager.create_case(
            title="Case 1",
            case_type=CaseType.FRAUD,
            priority=CasePriority.LOW,
        )
        case2 = case_manager.create_case(
            title="Case 2",
            case_type=CaseType.FRAUD,
            priority=CasePriority.LOW,
        )

        num1 = int(case1.case_number.split("-")[-1])
        num2 = int(case2.case_number.split("-")[-1])

        assert num2 == num1 + 1

    def test_assign_case(self, case_manager):
        """Should assign case to analyst."""
        case = case_manager.create_case(
            title="Assignment Test",
            case_type=CaseType.AML,
            priority=CasePriority.MEDIUM,
        )

        user_id = uuid4()
        case_manager.assign_case(case.id, user_id)

        updated = case_manager.get_case(case.id)
        assert updated.assigned_to == user_id

    def test_status_transitions(self, case_manager):
        """Should track status transitions."""
        case = case_manager.create_case(
            title="Status Test",
            case_type=CaseType.PEP,
            priority=CasePriority.HIGH,
        )

        assert case.status == CaseStatus.OPEN

        case_manager.update_status(case.id, CaseStatus.IN_PROGRESS)
        updated = case_manager.get_case(case.id)
        assert updated.status == CaseStatus.IN_PROGRESS

        case_manager.update_status(case.id, CaseStatus.PENDING_REVIEW)
        updated = case_manager.get_case(case.id)
        assert updated.status == CaseStatus.PENDING_REVIEW

    def test_add_note(self, case_manager):
        """Should add investigation notes."""
        case = case_manager.create_case(
            title="Notes Test",
            case_type=CaseType.AML,
            priority=CasePriority.LOW,
        )

        author_id = uuid4()
        case_manager.add_note(
            case.id,
            content="Initial investigation findings",
            author_id=author_id,
        )

        updated = case_manager.get_case(case.id)
        assert len(updated.notes) == 1
        assert updated.notes[0].content == "Initial investigation findings"

    def test_link_entities(self, case_manager, sample_entity):
        """Should link entities to case."""
        case = case_manager.create_case(
            title="Entity Link Test",
            case_type=CaseType.AML,
            priority=CasePriority.MEDIUM,
        )

        case_manager.link_entity(case.id, sample_entity.id)

        updated = case_manager.get_case(case.id)
        assert sample_entity.id in updated.entity_ids

    def test_link_alerts(self, case_manager):
        """Should link alerts to case."""
        case = case_manager.create_case(
            title="Alert Link Test",
            case_type=CaseType.AML,
            priority=CasePriority.HIGH,
        )

        alert_id = uuid4()
        case_manager.link_alert(case.id, alert_id)

        updated = case_manager.get_case(case.id)
        assert alert_id in updated.alert_ids

    def test_close_case(self, case_manager):
        """Should close case with outcome."""
        case = case_manager.create_case(
            title="Close Test",
            case_type=CaseType.FRAUD,
            priority=CasePriority.MEDIUM,
        )

        case_manager.close_case(
            case.id,
            outcome="confirmed",
            findings="Fraudulent activity confirmed",
            recommendations="File SAR and block accounts",
        )

        updated = case_manager.get_case(case.id)
        assert updated.status == CaseStatus.CLOSED
        assert updated.outcome == "confirmed"
        assert updated.closed_at is not None


class TestEvidenceCollector:
    """Tests for evidence collection and management."""

    def test_add_evidence(self):
        """Should add evidence with metadata."""
        collector = EvidenceCollector()

        evidence = collector.add_evidence(
            case_id=uuid4(),
            title="Bank Statement",
            evidence_type=EvidenceType.DOCUMENT,
            source="Bank API",
            content=b"PDF content here",
            collected_by=uuid4(),
        )

        assert evidence.id is not None
        assert evidence.hash is not None  # SHA-256 hash
        assert evidence.chain_of_custody is not None

    def test_evidence_hash_integrity(self):
        """Should verify evidence hash for integrity."""
        collector = EvidenceCollector()

        content = b"Important document content"
        evidence = collector.add_evidence(
            case_id=uuid4(),
            title="Test Document",
            evidence_type=EvidenceType.DOCUMENT,
            source="Test",
            content=content,
            collected_by=uuid4(),
        )

        # Verify hash
        assert collector.verify_integrity(evidence, content)

        # Tampered content should fail
        assert not collector.verify_integrity(evidence, b"Modified content")

    def test_chain_of_custody(self):
        """Should track chain of custody."""
        collector = EvidenceCollector()
        case_id = uuid4()
        user1 = uuid4()
        user2 = uuid4()

        evidence = collector.add_evidence(
            case_id=case_id,
            title="Custody Test",
            evidence_type=EvidenceType.SCREENSHOT,
            source="System",
            content=b"screenshot data",
            collected_by=user1,
        )

        # Record access
        collector.record_access(evidence.id, user2, "reviewed")

        updated = collector.get_evidence(evidence.id)
        assert len(updated.chain_of_custody) >= 2

    def test_evidence_types(self):
        """Should support different evidence types."""
        collector = EvidenceCollector()
        case_id = uuid4()
        user_id = uuid4()

        types_to_test = [
            EvidenceType.DOCUMENT,
            EvidenceType.SCREENSHOT,
            EvidenceType.TRANSACTION_RECORD,
            EvidenceType.COMMUNICATION,
            EvidenceType.API_RESPONSE,
        ]

        for etype in types_to_test:
            evidence = collector.add_evidence(
                case_id=case_id,
                title=f"Test {etype.value}",
                evidence_type=etype,
                source="Test",
                content=b"content",
                collected_by=user_id,
            )
            assert evidence.evidence_type == etype


class TestTimelineBuilder:
    """Tests for timeline reconstruction."""

    def test_add_events(self):
        """Should add and order events chronologically."""
        builder = TimelineBuilder(case_id=uuid4())

        now = datetime.utcnow()
        builder.add_event(
            timestamp=now - timedelta(days=2),
            description="Initial deposit",
            event_type="transaction",
        )
        builder.add_event(
            timestamp=now - timedelta(days=1),
            description="Funds transferred",
            event_type="transaction",
        )
        builder.add_event(
            timestamp=now,
            description="Alert triggered",
            event_type="alert",
        )

        timeline = builder.build()

        assert len(timeline.events) == 3
        # Should be chronological
        for i in range(len(timeline.events) - 1):
            assert timeline.events[i].timestamp <= timeline.events[i + 1].timestamp

    def test_event_grouping(self):
        """Should group related events."""
        builder = TimelineBuilder(case_id=uuid4())
        entity_id = uuid4()

        builder.add_event(
            timestamp=datetime.utcnow(),
            description="Event 1",
            event_type="transaction",
            entity_id=entity_id,
        )
        builder.add_event(
            timestamp=datetime.utcnow(),
            description="Event 2",
            event_type="transaction",
            entity_id=entity_id,
        )

        timeline = builder.build()
        entity_events = timeline.get_events_for_entity(entity_id)

        assert len(entity_events) == 2

    def test_event_metadata(self):
        """Should preserve event metadata."""
        builder = TimelineBuilder(case_id=uuid4())

        builder.add_event(
            timestamp=datetime.utcnow(),
            description="Transaction",
            event_type="transaction",
            metadata={"amount": 100000, "currency": "SEK"},
        )

        timeline = builder.build()
        assert timeline.events[0].metadata["amount"] == 100000


class TestWorkflowEngine:
    """Tests for investigation workflow execution."""

    def test_aml_workflow_template(self):
        """AML workflow should have required steps."""
        engine = WorkflowEngine()
        template = engine.get_template(WorkflowTemplate.AML_INVESTIGATION)

        # Check that template has steps with required step types
        step_names = [step.name.lower() for step in template.steps]

        # Verify core AML workflow steps exist (checking name contains keywords)
        assert any("review" in name for name in step_names), "Should have review step"
        assert any("analysis" in name for name in step_names), "Should have analysis step"
        assert any("assessment" in name or "decision" in name for name in step_names), "Should have assessment/decision step"
        assert len(template.steps) >= 5, "Should have at least 5 steps for AML workflow"

    def test_workflow_execution(self):
        """Should execute workflow steps in order."""
        engine = WorkflowEngine()
        case_id = uuid4()
        user_id = uuid4()

        workflow = engine.start_workflow(
            case_id=case_id,
            template=WorkflowTemplate.AML_INVESTIGATION,
            started_by=user_id,
        )

        assert workflow.current_step_index == 0
        assert workflow.status == "in_progress"

        # Complete first step
        engine.complete_step(
            workflow.id,
            notes="Initial review completed",
            completed_by=user_id,
        )

        updated = engine.get_workflow(workflow.id)
        assert updated.current_step_index == 1

    def test_workflow_completion(self):
        """Should mark workflow complete when all steps done."""
        engine = WorkflowEngine()
        case_id = uuid4()
        user_id = uuid4()

        workflow = engine.start_workflow(
            case_id=case_id,
            template=WorkflowTemplate.SANCTIONS_SCREENING,
            started_by=user_id,
        )

        # Complete all steps
        while not engine.is_complete(workflow.id):
            engine.complete_step(
                workflow.id,
                notes="Step completed",
                completed_by=user_id,
            )
            workflow = engine.get_workflow(workflow.id)

        assert workflow.status == "completed"

    def test_workflow_step_requirements(self):
        """Should enforce step requirements."""
        engine = WorkflowEngine()
        case_id = uuid4()
        user_id = uuid4()

        workflow = engine.start_workflow(
            case_id=case_id,
            template=WorkflowTemplate.FRAUD_INVESTIGATION,
            started_by=user_id,
        )

        # Get current step - should have role requirement
        current_step = engine.get_current_step(workflow.id)
        assert current_step is not None
        # Steps have role_required attribute for role-based requirements
        assert current_step.role_required is not None or current_step.step_type is not None

    def test_workflow_audit_trail(self):
        """Should maintain audit trail of workflow execution."""
        engine = WorkflowEngine()
        case_id = uuid4()
        user_id = uuid4()

        workflow = engine.start_workflow(
            case_id=case_id,
            template=WorkflowTemplate.PEP_REVIEW,
            started_by=user_id,
        )

        engine.complete_step(workflow.id, notes="Done", completed_by=user_id)

        updated = engine.get_workflow(workflow.id)

        # Should have audit entries
        assert len(updated.audit_trail) >= 2  # Start + completion
