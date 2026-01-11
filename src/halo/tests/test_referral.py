"""
Tests for the referral pipeline module.

Tests:
- Authority routing
- Referral pipeline
"""

from datetime import datetime
from uuid import uuid4

import pytest

from halo.referral import (
    Authority,
    AuthorityRouter,
    RoutingDecision,
    ReferralPipeline,
    ReferralRequest,
    ReferralResult,
    ReferralStatus,
)


class TestAuthority:
    """Tests for Authority enum."""

    def test_authority_values(self):
        """Test all authority values exist."""
        assert Authority.EBM.value == "EBM"
        assert Authority.SKV.value == "SKV"
        assert Authority.FK.value == "FK"
        assert Authority.FIU.value == "FIU"
        assert Authority.IVO.value == "IVO"
        assert Authority.POL.value == "POL"

    def test_authority_from_string(self):
        """Test creating authority from string."""
        assert Authority("EBM") == Authority.EBM
        assert Authority("SKV") == Authority.SKV

    def test_invalid_authority_raises(self):
        """Test invalid authority raises ValueError."""
        with pytest.raises(ValueError):
            Authority("invalid")


class TestReferralStatus:
    """Tests for ReferralStatus enum."""

    def test_status_values(self):
        """Test status values exist."""
        assert ReferralStatus.DRAFT.value == "draft"
        assert ReferralStatus.PENDING_REVIEW.value == "pending_review"
        assert ReferralStatus.SUBMITTED.value == "submitted"
        assert ReferralStatus.APPROVED.value == "approved"


class TestRoutingDecision:
    """Tests for RoutingDecision dataclass."""

    def test_decision_creation(self):
        """Test creating a routing decision."""
        decision = RoutingDecision(
            primary_authority=Authority.EBM,
            confidence=0.85,
            rationale="High-value economic crime indicators",
        )

        assert decision.primary_authority == Authority.EBM
        assert decision.confidence == 0.85
        assert decision.rationale == "High-value economic crime indicators"

    def test_decision_with_secondary_authorities(self):
        """Test decision with secondary authorities."""
        decision = RoutingDecision(
            primary_authority=Authority.EBM,
            secondary_authorities=[Authority.SKV, Authority.FIU],
            confidence=0.9,
            rationale="Economic crime with tax implications",
        )

        assert len(decision.secondary_authorities) == 2
        assert Authority.SKV in decision.secondary_authorities

    def test_decision_defaults(self):
        """Test default values for decision."""
        decision = RoutingDecision(primary_authority=Authority.POL)

        assert decision.secondary_authorities == []
        assert decision.confidence == 0.0
        assert decision.rationale == ""
        assert decision.value_threshold_met is False
        assert decision.requires_fiu_report is False


class TestAuthorityRouter:
    """Tests for AuthorityRouter class."""

    def test_router_initialization(self):
        """Test router initializes correctly."""
        router = AuthorityRouter()
        assert router is not None
        assert router.thresholds is not None

    def test_router_with_custom_thresholds(self):
        """Test router with custom thresholds."""
        router = AuthorityRouter(custom_thresholds={})
        assert router is not None

    def test_route_economic_crime(self):
        """Test routing economic crime case."""
        router = AuthorityRouter()

        decision = router.route(
            crime_type="economic_crime",
            estimated_value_sek=1_000_000,
            confidence=0.85,
        )

        assert isinstance(decision, RoutingDecision)
        assert decision.primary_authority == Authority.EBM

    def test_route_tax_fraud(self):
        """Test routing tax fraud case."""
        router = AuthorityRouter()

        decision = router.route(
            crime_type="tax_fraud",
            estimated_value_sek=100_000,
            confidence=0.75,
        )

        assert decision.primary_authority in [Authority.SKV, Authority.EBM]

    def test_route_welfare_fraud(self):
        """Test routing welfare fraud case."""
        router = AuthorityRouter()

        decision = router.route(
            crime_type="welfare_fraud",
            estimated_value_sek=50_000,
            confidence=0.7,
        )

        assert decision.primary_authority == Authority.FK

    def test_route_money_laundering(self):
        """Test routing money laundering case."""
        router = AuthorityRouter()

        decision = router.route(
            crime_type="money_laundering",
            estimated_value_sek=500_000,
            confidence=0.6,
        )

        assert decision.primary_authority == Authority.FIU
        assert decision.requires_fiu_report is True

    def test_route_unknown_defaults_to_police(self):
        """Test unknown crime types default to Polisen."""
        router = AuthorityRouter()

        decision = router.route(
            crime_type="unknown_crime_type",
            estimated_value_sek=100_000,
            confidence=0.9,
        )

        assert decision.primary_authority == Authority.POL

    def test_route_with_metadata(self):
        """Test routing with additional metadata."""
        router = AuthorityRouter()

        decision = router.route(
            crime_type="economic_crime",
            estimated_value_sek=2_000_000,
            confidence=0.9,
            metadata={"entities": 5, "cross_border": True},
        )

        assert isinstance(decision, RoutingDecision)

    def test_rationale_generated(self):
        """Test that rationale is generated."""
        router = AuthorityRouter()

        decision = router.route(
            crime_type="economic_crime",
            estimated_value_sek=1_000_000,
            confidence=0.8,
        )

        assert decision.rationale != ""
        assert "economic_crime" in decision.rationale


class TestReferralRequest:
    """Tests for ReferralRequest dataclass."""

    def test_request_creation(self):
        """Test creating a referral request."""
        case_id = uuid4()
        detection_id = uuid4()

        request = ReferralRequest(
            case_id=case_id,
            detection_ids=[detection_id],
            target_authority="EBM",
            priority="high",
            summary="Economic crime investigation",
        )

        assert request.case_id == case_id
        assert request.target_authority == "EBM"
        assert request.priority == "high"

    def test_request_defaults(self):
        """Test request default values."""
        request = ReferralRequest(
            case_id=uuid4(),
            detection_ids=[uuid4()],
            target_authority="SKV",
        )

        assert request.priority == "normal"
        assert request.summary == ""
        assert request.evidence_ids == []
        assert request.metadata == {}


class TestReferralResult:
    """Tests for ReferralResult dataclass."""

    def test_result_creation(self):
        """Test creating a referral result."""
        result = ReferralResult(
            referral_id=uuid4(),
            status=ReferralStatus.DRAFT,
            authority="EBM",
            confidence=0.85,
        )

        assert result.status == ReferralStatus.DRAFT
        assert result.authority == "EBM"

    def test_result_with_submission(self):
        """Test result with submission details."""
        result = ReferralResult(
            referral_id=uuid4(),
            status=ReferralStatus.SUBMITTED,
            authority="SKV",
            confidence=0.9,
            submitted_at=datetime.utcnow(),
            tracking_reference="HALO-SKV-20240101120000",
        )

        assert result.submitted_at is not None
        assert result.tracking_reference.startswith("HALO-SKV")


class TestReferralPipeline:
    """Tests for the ReferralPipeline class."""

    @pytest.fixture
    def pipeline(self):
        """Create a pipeline instance."""
        return ReferralPipeline()

    def test_pipeline_initialization(self, pipeline):
        """Test pipeline initializes correctly."""
        assert pipeline is not None
        assert pipeline.pending_referrals == {}

    @pytest.mark.asyncio
    async def test_create_referral(self, pipeline):
        """Test creating a referral."""
        request = ReferralRequest(
            case_id=uuid4(),
            detection_ids=[uuid4()],
            target_authority="EBM",
            priority="normal",
            summary="Test referral",
        )

        result = await pipeline.create_referral(request)

        assert result.authority == "EBM"
        assert result.status in [
            ReferralStatus.DRAFT,
            ReferralStatus.PENDING_REVIEW,
        ]

    @pytest.mark.asyncio
    async def test_create_referral_with_evidence(self, pipeline):
        """Test creating a referral with evidence."""
        request = ReferralRequest(
            case_id=uuid4(),
            detection_ids=[uuid4(), uuid4()],
            target_authority="SKV",
            priority="high",
            summary="Tax fraud case",
            evidence_ids=[uuid4(), uuid4()],
        )

        result = await pipeline.create_referral(request)

        # More evidence should increase confidence
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_submit_referral(self, pipeline):
        """Test submitting a referral."""
        request = ReferralRequest(
            case_id=uuid4(),
            detection_ids=[uuid4()],
            target_authority="FIU",
            priority="urgent",
            summary="Suspicious activity",
        )

        created = await pipeline.create_referral(request)
        submitted = await pipeline.submit_referral(created.referral_id)

        assert submitted.status == ReferralStatus.SUBMITTED
        assert submitted.tracking_reference is not None
        assert submitted.submitted_at is not None

    @pytest.mark.asyncio
    async def test_submit_nonexistent_referral(self, pipeline):
        """Test submitting a nonexistent referral raises error."""
        with pytest.raises(ValueError):
            await pipeline.submit_referral(uuid4())

    @pytest.mark.asyncio
    async def test_get_referral_status(self, pipeline):
        """Test getting referral status."""
        request = ReferralRequest(
            case_id=uuid4(),
            detection_ids=[uuid4()],
            target_authority="EBM",
            summary="Economic crime",
        )

        created = await pipeline.create_referral(request)
        status = await pipeline.get_referral_status(created.referral_id)

        assert status is not None
        assert status.referral_id == created.referral_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_status(self, pipeline):
        """Test getting status for nonexistent referral."""
        status = await pipeline.get_referral_status(uuid4())
        assert status is None


class TestReferralWorkflow:
    """Tests for complete referral workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete referral workflow."""
        router = AuthorityRouter()
        pipeline = ReferralPipeline()

        case_id = uuid4()

        # 1. Route to get recommended authority
        decision = router.route(
            crime_type="economic_crime",
            estimated_value_sek=3_000_000,
            confidence=0.85,
        )

        assert decision.primary_authority == Authority.EBM

        # 2. Create referral
        request = ReferralRequest(
            case_id=case_id,
            detection_ids=[uuid4(), uuid4()],
            target_authority=decision.primary_authority.value,
            priority="high",
            summary="Comprehensive fraud investigation",
        )

        result = await pipeline.create_referral(request)
        assert result.status in [ReferralStatus.DRAFT, ReferralStatus.PENDING_REVIEW]

        # 3. Submit referral
        submitted = await pipeline.submit_referral(result.referral_id)
        assert submitted.status == ReferralStatus.SUBMITTED
        assert submitted.tracking_reference is not None

    @pytest.mark.asyncio
    async def test_multi_authority_routing(self):
        """Test routing that suggests multiple authorities."""
        router = AuthorityRouter()

        # Tax fraud with high value could go to EBM or SKV
        decision = router.route(
            crime_type="tax_fraud",
            estimated_value_sek=600_000,
            confidence=0.8,
        )

        # Should have primary and possibly secondary authorities
        assert decision.primary_authority is not None
        assert isinstance(decision.secondary_authorities, list)
