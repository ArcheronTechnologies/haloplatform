"""
Tests for the anomaly detection module (Layer 1).
"""

import pytest
from datetime import date, datetime

from halo.intelligence.anomaly import (
    AnomalyDetector,
    AnomalyScore,
    BaselineStats,
    ANOMALY_THRESHOLDS,
)
from halo.graph.client import GraphClient
from halo.graph.schema import Company, Address, Person
from halo.graph.edges import RegisteredAtEdge, DirectsEdge


class TestBaselineStats:
    """Tests for BaselineStats."""

    def test_default_baselines(self):
        """Test default baseline values."""
        baselines = BaselineStats()

        assert baselines.addr_density_mean == 1.02
        assert baselines.director_roles_mean == 1.12
        assert baselines.company_lifespan_months_median == 84.0

    def test_custom_baselines(self):
        """Test custom baseline values."""
        baselines = BaselineStats(
            addr_density_mean=2.0,
            director_roles_mean=1.5
        )

        assert baselines.addr_density_mean == 2.0
        assert baselines.director_roles_mean == 1.5


class TestAnomalyScore:
    """Tests for AnomalyScore."""

    def test_anomaly_score_creation(self):
        """Test anomaly score creation."""
        score = AnomalyScore(
            entity_id="test-123",
            entity_type="company",
            z_scores={"density": 2.5, "velocity": 1.2},
            composite_score=2.5,
            flags=[{"type": "high_density", "severity": "high"}]
        )

        assert score.entity_id == "test-123"
        assert score.is_anomalous is True  # z-score > 2
        assert score.severity == "high"

    def test_non_anomalous_score(self):
        """Test non-anomalous score."""
        score = AnomalyScore(
            entity_id="test-123",
            entity_type="company",
            z_scores={"density": 0.5, "velocity": 0.3},
            composite_score=0.5
        )

        assert score.is_anomalous is False
        assert score.severity == "low"

    def test_severity_levels(self):
        """Test severity level determination."""
        # Critical
        score = AnomalyScore(entity_id="1", entity_type="x", composite_score=3.5)
        assert score.severity == "critical"

        # High
        score = AnomalyScore(entity_id="1", entity_type="x", composite_score=2.5)
        assert score.severity == "high"

        # Medium
        score = AnomalyScore(entity_id="1", entity_type="x", composite_score=1.7)
        assert score.severity == "medium"

        # Low
        score = AnomalyScore(entity_id="1", entity_type="x", composite_score=1.0)
        assert score.severity == "low"


class TestAnomalyDetector:
    """Tests for AnomalyDetector."""

    @pytest.fixture
    def detector(self):
        """Create a detector without graph client."""
        return AnomalyDetector()

    @pytest.fixture
    def detector_with_graph(self):
        """Create a detector with graph client."""
        client = GraphClient()
        return AnomalyDetector(graph_client=client)

    def test_detector_creation(self, detector):
        """Test detector creation."""
        assert detector.baselines is not None
        assert isinstance(detector.baselines, BaselineStats)

    def test_custom_baselines(self):
        """Test detector with custom baselines."""
        custom = BaselineStats(addr_density_mean=5.0)
        detector = AnomalyDetector(baselines=custom)
        assert detector.baselines.addr_density_mean == 5.0

    @pytest.mark.asyncio
    async def test_score_address_no_graph(self, detector):
        """Test address scoring without graph."""
        score = await detector.score_address("address-123")

        assert score.entity_id == "address-123"
        assert score.entity_type == "address"
        # Without graph, counts will be 0

    @pytest.mark.asyncio
    async def test_score_company_no_graph(self, detector):
        """Test company scoring without graph."""
        score = await detector.score_company("company-123")

        # Without graph, company not found
        assert score.entity_id == "company-123"
        assert score.entity_type == "company"

    @pytest.mark.asyncio
    async def test_score_person_no_graph(self, detector):
        """Test person scoring without graph."""
        score = await detector.score_person("person-123")

        assert score.entity_id == "person-123"
        assert score.entity_type == "person"

    @pytest.mark.asyncio
    async def test_score_address_with_graph(self, detector_with_graph):
        """Test address scoring with graph."""
        async with detector_with_graph.graph:
            # Create address with multiple companies
            address = Address(id="addr-1", type="commercial")
            await detector_with_graph.graph.add_address(address)

            for i in range(10):
                company = Company(id=f"company-{i}")
                await detector_with_graph.graph.add_company(company)
                await detector_with_graph.graph.add_registration(
                    RegisteredAtEdge(from_id=f"company-{i}", to_id="addr-1", type="registered")
                )

            score = await detector_with_graph.score_address("addr-1")

            assert score.entity_id == "addr-1"
            # Should flag high density
            assert any(f["type"] == "high_registration_density" for f in score.flags)

    @pytest.mark.asyncio
    async def test_score_company_shell_indicators(self, detector_with_graph):
        """Test company shell company scoring."""
        async with detector_with_graph.graph:
            # Create company with shell indicators
            company = Company(
                id="shell-company",
                orgnr="5560001234",
                formation={"date": date.today().isoformat()},  # Recently formed
                employees={"count": 0},  # No employees
                f_skatt={"registered": True},  # F-skatt
                vat={"registered": False},  # No VAT
                sni_codes=[{"code": "70100"}],  # Generic SNI (holding)
            )
            await detector_with_graph.graph.add_company(company)

            score = await detector_with_graph.score_company("shell-company")

            assert score.entity_id == "shell-company"
            # Should have shell indicators
            shell_flags = [f for f in score.flags if "shell_indicator" in f["type"]]
            assert len(shell_flags) >= 3  # Multiple indicators

    @pytest.mark.asyncio
    async def test_score_person_high_directorships(self, detector_with_graph):
        """Test person scoring with many directorships."""
        async with detector_with_graph.graph:
            person = Person(id="nominee-director")
            await detector_with_graph.graph.add_person(person)

            # Create many directorships
            for i in range(10):
                company = Company(id=f"company-{i}")
                await detector_with_graph.graph.add_company(company)
                await detector_with_graph.graph.add_directorship(
                    DirectsEdge(from_id="nominee-director", to_id=f"company-{i}", role="styrelseledamot")
                )

            score = await detector_with_graph.score_person("nominee-director")

            assert score.entity_id == "nominee-director"
            # Should flag high directorship count
            assert any(f["type"] == "high_directorship_count" for f in score.flags)

    def test_check_no_employees(self, detector):
        """Test no employees check."""
        assert detector._check_no_employees({}) is True
        assert detector._check_no_employees({"employees": None}) is True
        assert detector._check_no_employees({"employees": {"count": 0}}) is True
        assert detector._check_no_employees({"employees": {"count": 5}}) is False

    def test_check_f_skatt_no_vat(self, detector):
        """Test F-skatt without VAT check."""
        assert detector._check_f_skatt_no_vat({}) is False
        assert detector._check_f_skatt_no_vat({
            "f_skatt": {"registered": True},
            "vat": {"registered": False}
        }) is True
        assert detector._check_f_skatt_no_vat({
            "f_skatt": {"registered": True},
            "vat": {"registered": True}
        }) is False

    def test_check_generic_sni(self, detector):
        """Test generic SNI code check."""
        assert detector._check_generic_sni({}) is False
        assert detector._check_generic_sni({"sni_codes": []}) is False
        assert detector._check_generic_sni({"sni_codes": [{"code": "70100"}]}) is True  # Holding
        assert detector._check_generic_sni({"sni_codes": [{"code": "82110"}]}) is True  # Consulting
        assert detector._check_generic_sni({"sni_codes": [{"code": "43210"}]}) is False  # Construction

    def test_check_recently_formed(self, detector):
        """Test recently formed check."""
        from datetime import timedelta

        # No formation date
        assert detector._check_recently_formed({}) is False

        # Recent formation
        recent_date = (datetime.utcnow().date() - timedelta(days=30)).isoformat()
        assert detector._check_recently_formed({"formation": {"date": recent_date}}) is True

        # Old formation
        old_date = (datetime.utcnow().date() - timedelta(days=500)).isoformat()
        assert detector._check_recently_formed({"formation": {"date": old_date}}) is False


class TestAnomalyThresholds:
    """Tests for anomaly thresholds."""

    def test_threshold_values(self):
        """Test threshold values are sensible."""
        assert ANOMALY_THRESHOLDS["companies_at_address"] > 0
        assert ANOMALY_THRESHOLDS["director_roles"] > 0
        assert ANOMALY_THRESHOLDS["same_day_formations"] > 0
        assert 0 < ANOMALY_THRESHOLDS["shell_score"] < 1
