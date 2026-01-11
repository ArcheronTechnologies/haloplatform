"""
Tests for the impact tracking module.

Tests:
- Impact record creation
- Impact metrics calculation
- Authority-specific metrics
- Effectiveness tracking
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from halo.impact import (
    ImpactTracker,
    ImpactRecord,
    ImpactType,
    ImpactMetrics,
    AuthorityMetrics,
    MetricsCalculator,
)


class TestImpactType:
    """Tests for ImpactType enum."""

    def test_investigation_types(self):
        """Test investigation lifecycle types."""
        assert ImpactType.INVESTIGATION_OPENED.value == "investigation_opened"
        assert ImpactType.INVESTIGATION_CLOSED.value == "investigation_closed"

    def test_legal_types(self):
        """Test legal action types."""
        assert ImpactType.CHARGES_FILED.value == "charges_filed"
        assert ImpactType.CONVICTION.value == "conviction"
        assert ImpactType.ACQUITTAL.value == "acquittal"
        assert ImpactType.SETTLEMENT.value == "settlement"

    def test_financial_types(self):
        """Test financial impact types."""
        assert ImpactType.ASSETS_SEIZED.value == "assets_seized"
        assert ImpactType.TAX_RECOVERED.value == "tax_recovered"
        assert ImpactType.FINES_IMPOSED.value == "fines_imposed"

    def test_prevention_types(self):
        """Test prevention impact types."""
        assert ImpactType.FRAUD_PREVENTED.value == "fraud_prevented"
        assert ImpactType.ACTIVITY_DISRUPTED.value == "activity_disrupted"


class TestImpactRecord:
    """Tests for ImpactRecord dataclass."""

    def test_record_creation(self):
        """Test creating an impact record."""
        record = ImpactRecord(
            id=uuid4(),
            referral_id=uuid4(),
            case_id=uuid4(),
            impact_type=ImpactType.CONVICTION,
            occurred_at=datetime.utcnow(),
            recorded_at=datetime.utcnow(),
            recorded_by="analyst_1",
            authority="EBM",
            description="Conviction for economic crime",
            value_sek=0.0,
            metadata={},
        )

        assert record.impact_type == ImpactType.CONVICTION
        assert record.authority == "EBM"

    def test_record_with_value(self):
        """Test record with financial value."""
        record = ImpactRecord(
            id=uuid4(),
            referral_id=uuid4(),
            case_id=None,
            impact_type=ImpactType.ASSETS_SEIZED,
            occurred_at=datetime.utcnow(),
            recorded_at=datetime.utcnow(),
            recorded_by="analyst_1",
            authority="Kronofogden",
            description="Assets seized in fraud case",
            value_sek=5_000_000.0,
            metadata={"asset_type": "real_estate"},
        )

        assert record.value_sek == 5_000_000.0
        assert record.metadata["asset_type"] == "real_estate"

    def test_record_to_dict(self):
        """Test serializing record to dict."""
        record = ImpactRecord(
            id=uuid4(),
            referral_id=uuid4(),
            case_id=uuid4(),
            impact_type=ImpactType.TAX_RECOVERED,
            occurred_at=datetime.utcnow(),
            recorded_at=datetime.utcnow(),
            recorded_by="analyst_1",
            authority="SKV",
            description="Tax recovered from audit",
            value_sek=200_000.0,
            metadata={},
        )

        data = record.to_dict()

        assert "id" in data
        assert data["impact_type"] == "tax_recovered"
        assert data["authority"] == "SKV"
        assert data["value_sek"] == 200_000.0


class TestImpactTracker:
    """Tests for ImpactTracker class."""

    def test_tracker_initialization(self):
        """Test tracker initializes correctly."""
        tracker = ImpactTracker()

        assert len(tracker.records) == 0

    def test_record_impact(self):
        """Test recording an impact."""
        tracker = ImpactTracker()
        referral_id = uuid4()

        record = tracker.record(
            impact_type=ImpactType.INVESTIGATION_OPENED,
            authority="Polisen",
            description="Investigation opened based on referral",
            recorded_by="analyst_1",
            referral_id=referral_id,
        )

        assert record.impact_type == ImpactType.INVESTIGATION_OPENED
        assert record.referral_id == referral_id
        assert len(tracker.records) == 1

    def test_record_with_value(self):
        """Test recording impact with financial value."""
        tracker = ImpactTracker()

        record = tracker.record(
            impact_type=ImpactType.FINES_IMPOSED,
            authority="Tingsrätten",
            description="Court fines imposed",
            recorded_by="analyst_1",
            value_sek=500_000.0,
        )

        assert record.value_sek == 500_000.0

    def test_get_by_referral(self):
        """Test getting records by referral."""
        tracker = ImpactTracker()
        referral_id = uuid4()

        # Add records for same referral
        tracker.record(
            impact_type=ImpactType.INVESTIGATION_OPENED,
            authority="EBM",
            description="Investigation opened",
            recorded_by="analyst_1",
            referral_id=referral_id,
        )

        tracker.record(
            impact_type=ImpactType.CHARGES_FILED,
            authority="EBM",
            description="Charges filed",
            recorded_by="analyst_1",
            referral_id=referral_id,
        )

        # Add record for different referral
        tracker.record(
            impact_type=ImpactType.INVESTIGATION_OPENED,
            authority="SKV",
            description="Different investigation",
            recorded_by="analyst_1",
            referral_id=uuid4(),
        )

        records = tracker.get_by_referral(referral_id)

        assert len(records) == 2

    def test_get_by_case(self):
        """Test getting records by case."""
        tracker = ImpactTracker()
        case_id = uuid4()

        tracker.record(
            impact_type=ImpactType.CONVICTION,
            authority="Tingsrätten",
            description="Conviction",
            recorded_by="analyst_1",
            case_id=case_id,
        )

        records = tracker.get_by_case(case_id)

        assert len(records) == 1

    def test_get_by_type(self):
        """Test getting records by impact type."""
        tracker = ImpactTracker()

        tracker.record(
            impact_type=ImpactType.CONVICTION,
            authority="Court A",
            description="Conviction 1",
            recorded_by="analyst_1",
        )

        tracker.record(
            impact_type=ImpactType.CONVICTION,
            authority="Court B",
            description="Conviction 2",
            recorded_by="analyst_1",
        )

        tracker.record(
            impact_type=ImpactType.ACQUITTAL,
            authority="Court C",
            description="Acquittal",
            recorded_by="analyst_1",
        )

        convictions = tracker.get_by_type(ImpactType.CONVICTION)

        assert len(convictions) == 2

    def test_get_by_authority(self):
        """Test getting records by authority."""
        tracker = ImpactTracker()

        tracker.record(
            impact_type=ImpactType.TAX_RECOVERED,
            authority="SKV",
            description="Tax 1",
            recorded_by="analyst_1",
            value_sek=100_000,
        )

        tracker.record(
            impact_type=ImpactType.FINES_IMPOSED,
            authority="SKV",
            description="Fine 1",
            recorded_by="analyst_1",
            value_sek=50_000,
        )

        tracker.record(
            impact_type=ImpactType.ASSETS_SEIZED,
            authority="Kronofogden",
            description="Assets",
            recorded_by="analyst_1",
            value_sek=500_000,
        )

        skv_records = tracker.get_by_authority("SKV")

        assert len(skv_records) == 2

    def test_total_value(self):
        """Test calculating total value."""
        tracker = ImpactTracker()

        tracker.record(
            impact_type=ImpactType.ASSETS_SEIZED,
            authority="Kronofogden",
            description="Assets 1",
            recorded_by="analyst_1",
            value_sek=1_000_000,
        )

        tracker.record(
            impact_type=ImpactType.TAX_RECOVERED,
            authority="SKV",
            description="Tax",
            recorded_by="analyst_1",
            value_sek=500_000,
        )

        total = tracker.total_value()

        assert total == 1_500_000

    def test_total_value_filtered(self):
        """Test calculating filtered total value."""
        tracker = ImpactTracker()

        tracker.record(
            impact_type=ImpactType.TAX_RECOVERED,
            authority="SKV",
            description="Tax 1",
            recorded_by="analyst_1",
            value_sek=200_000,
        )

        tracker.record(
            impact_type=ImpactType.TAX_RECOVERED,
            authority="SKV",
            description="Tax 2",
            recorded_by="analyst_1",
            value_sek=300_000,
        )

        tracker.record(
            impact_type=ImpactType.FINES_IMPOSED,
            authority="Court",
            description="Fine",
            recorded_by="analyst_1",
            value_sek=100_000,
        )

        tax_total = tracker.total_value(impact_type=ImpactType.TAX_RECOVERED)

        assert tax_total == 500_000


class TestImpactMetrics:
    """Tests for ImpactMetrics dataclass."""

    def test_metrics_creation(self):
        """Test creating metrics."""
        metrics = ImpactMetrics(
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            investigations_opened=10,
            investigations_closed=8,
            charges_filed=5,
            convictions=3,
            acquittals=1,
        )

        assert metrics.investigations_opened == 10
        assert metrics.convictions == 3

    def test_conviction_rate(self):
        """Test conviction rate calculation."""
        metrics = ImpactMetrics(
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            convictions=8,
            acquittals=2,
            conviction_rate=0.8,
        )

        assert metrics.conviction_rate == 0.8

    def test_financial_totals(self):
        """Test financial metric totals."""
        metrics = ImpactMetrics(
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            assets_seized_sek=5_000_000,
            tax_recovered_sek=2_000_000,
            fines_imposed_sek=500_000,
            fraud_prevented_sek=10_000_000,
            total_financial_impact_sek=17_500_000,
        )

        assert metrics.total_financial_impact_sek == 17_500_000

    def test_metrics_to_dict(self):
        """Test serializing metrics to dict."""
        metrics = ImpactMetrics(
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            convictions=5,
            total_financial_impact_sek=1_000_000,
        )

        data = metrics.to_dict()

        assert "period" in data
        assert "legal_outcomes" in data
        assert "financial_impact" in data


class TestMetricsCalculator:
    """Tests for MetricsCalculator class."""

    def test_calculator_initialization(self):
        """Test calculator initializes with tracker."""
        tracker = ImpactTracker()
        calculator = MetricsCalculator(tracker)

        assert calculator.tracker is tracker

    def test_calculate_period_metrics(self):
        """Test calculating metrics for a period."""
        tracker = ImpactTracker()

        # Add some records
        tracker.record(
            impact_type=ImpactType.INVESTIGATION_OPENED,
            authority="EBM",
            description="Investigation 1",
            recorded_by="analyst_1",
        )

        tracker.record(
            impact_type=ImpactType.CONVICTION,
            authority="Court",
            description="Conviction 1",
            recorded_by="analyst_1",
        )

        tracker.record(
            impact_type=ImpactType.ASSETS_SEIZED,
            authority="Kronofogden",
            description="Assets",
            recorded_by="analyst_1",
            value_sek=1_000_000,
        )

        calculator = MetricsCalculator(tracker)

        metrics = calculator.calculate_period_metrics(
            start=datetime.utcnow() - timedelta(days=1),
            end=datetime.utcnow() + timedelta(days=1),
        )

        assert metrics.investigations_opened == 1
        assert metrics.convictions == 1
        assert metrics.assets_seized_sek == 1_000_000

    def test_calculate_authority_metrics(self):
        """Test calculating metrics by authority."""
        tracker = ImpactTracker()

        tracker.record(
            impact_type=ImpactType.CONVICTION,
            authority="EBM",
            description="EBM conviction",
            recorded_by="analyst_1",
        )

        tracker.record(
            impact_type=ImpactType.TAX_RECOVERED,
            authority="SKV",
            description="SKV recovery",
            recorded_by="analyst_1",
            value_sek=500_000,
        )

        tracker.record(
            impact_type=ImpactType.CONVICTION,
            authority="EBM",
            description="EBM conviction 2",
            recorded_by="analyst_1",
        )

        calculator = MetricsCalculator(tracker)

        authority_metrics = calculator.calculate_authority_metrics()

        assert len(authority_metrics) == 2

        ebm_metrics = next(m for m in authority_metrics if m.authority == "EBM")
        assert ebm_metrics.convictions == 2

    def test_referral_effectiveness(self):
        """Test calculating referral effectiveness."""
        tracker = ImpactTracker()
        referral_id = uuid4()

        # Referral with positive outcome
        tracker.record(
            impact_type=ImpactType.INVESTIGATION_OPENED,
            authority="EBM",
            description="Investigation",
            recorded_by="analyst_1",
            referral_id=referral_id,
        )

        tracker.record(
            impact_type=ImpactType.CONVICTION,
            authority="Court",
            description="Conviction",
            recorded_by="analyst_1",
            referral_id=referral_id,
        )

        calculator = MetricsCalculator(tracker)

        effectiveness = calculator.get_referral_effectiveness()

        assert "total_referrals" in effectiveness
        assert "positive_outcomes" in effectiveness


class TestAuthorityMetrics:
    """Tests for AuthorityMetrics dataclass."""

    def test_authority_metrics_creation(self):
        """Test creating authority metrics."""
        metrics = AuthorityMetrics(
            authority="EBM",
            total_referrals=50,
            outcomes_recorded=45,
            convictions=30,
            total_value_sek=10_000_000,
        )

        assert metrics.authority == "EBM"
        assert metrics.convictions == 30

    def test_authority_metrics_to_dict(self):
        """Test serializing authority metrics."""
        metrics = AuthorityMetrics(
            authority="SKV",
            outcomes_recorded=20,
            convictions=5,
            total_value_sek=2_000_000,
        )

        data = metrics.to_dict()

        assert data["authority"] == "SKV"
        assert data["total_value_sek"] == 2_000_000


class TestImpactWorkflow:
    """Tests for complete impact tracking workflow."""

    def test_full_impact_workflow(self):
        """Test complete impact tracking workflow."""
        tracker = ImpactTracker()
        calculator = MetricsCalculator(tracker)

        referral_id = uuid4()
        case_id = uuid4()

        # 1. Record investigation opened
        tracker.record(
            impact_type=ImpactType.INVESTIGATION_OPENED,
            authority="EBM",
            description="Investigation opened based on referral",
            recorded_by="analyst_1",
            referral_id=referral_id,
            case_id=case_id,
        )

        # 2. Record charges filed
        tracker.record(
            impact_type=ImpactType.CHARGES_FILED,
            authority="Åklagarmyndigheten",
            description="Charges filed for economic crime",
            recorded_by="analyst_1",
            referral_id=referral_id,
            case_id=case_id,
        )

        # 3. Record conviction
        tracker.record(
            impact_type=ImpactType.CONVICTION,
            authority="Tingsrätten",
            description="Defendant convicted",
            recorded_by="analyst_1",
            referral_id=referral_id,
            case_id=case_id,
        )

        # 4. Record assets seized
        tracker.record(
            impact_type=ImpactType.ASSETS_SEIZED,
            authority="Kronofogden",
            description="Assets seized following conviction",
            recorded_by="analyst_1",
            referral_id=referral_id,
            case_id=case_id,
            value_sek=2_500_000,
        )

        # 5. Record investigation closed
        tracker.record(
            impact_type=ImpactType.INVESTIGATION_CLOSED,
            authority="EBM",
            description="Investigation closed - successful",
            recorded_by="analyst_1",
            referral_id=referral_id,
            case_id=case_id,
        )

        # Verify tracking
        assert len(tracker.records) == 5

        # Verify referral tracking
        referral_records = tracker.get_by_referral(referral_id)
        assert len(referral_records) == 5

        # Verify case tracking
        case_records = tracker.get_by_case(case_id)
        assert len(case_records) == 5

        # Verify metrics
        metrics = calculator.calculate_period_metrics(
            start=datetime.utcnow() - timedelta(hours=1),
        )

        assert metrics.investigations_opened == 1
        assert metrics.investigations_closed == 1
        assert metrics.charges_filed == 1
        assert metrics.convictions == 1
        assert metrics.assets_seized_sek == 2_500_000

        # Verify effectiveness
        effectiveness = calculator.get_referral_effectiveness()
        assert effectiveness["total_referrals"] >= 1
        assert effectiveness["positive_outcomes"] >= 1
