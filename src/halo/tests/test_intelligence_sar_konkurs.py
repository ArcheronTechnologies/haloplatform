"""
Tests for SAR Generator and Konkurs Prediction.
"""

import pytest
from datetime import date, datetime

from halo.intelligence.sar_generator import (
    SARGenerator,
    SAR,
    SARSection,
)
from halo.intelligence.konkurs import (
    KonkursPredictor,
    KonkursPrediction,
    KONKURS_FEATURES,
)
from halo.graph.client import GraphClient


class TestSARSection:
    """Tests for SARSection."""

    def test_section_creation(self):
        """Test SAR section creation."""
        section = SARSection(
            title="Subject Identification",
            content={"name": "Test AB", "orgnr": "5560125790"},
            section_type="table"
        )

        assert section.title == "Subject Identification"
        assert section.section_type == "table"


class TestSAR:
    """Tests for SAR document."""

    def test_sar_creation_defaults(self):
        """Test SAR creation with defaults."""
        sar = SAR()

        assert sar.id is not None
        assert sar.sar_type == "str"
        assert sar.status == "draft"
        assert sar.priority == "medium"
        assert sar.currency == "SEK"
        assert sar.sections == []

    def test_sar_creation_with_data(self):
        """Test SAR creation with data."""
        sar = SAR(
            subject_entity_id="company-123",
            subject_entity_type="Company",
            subject_name="Test AB",
            subject_identifier="5560125790",
            summary="Suspicious activity detected",
            trigger_reason="Pattern match",
            priority="high"
        )

        assert sar.subject_entity_id == "company-123"
        assert sar.subject_name == "Test AB"
        assert sar.priority == "high"

    def test_sar_add_section(self):
        """Test adding sections to SAR."""
        sar = SAR()

        sar.add_section(
            "Executive Summary",
            "This report concerns suspicious activity...",
            "text"
        )
        sar.add_section(
            "Entity Details",
            {"name": "Test", "id": "123"},
            "table"
        )

        assert len(sar.sections) == 2
        assert sar.sections[0].title == "Executive Summary"
        assert sar.sections[1].section_type == "table"

    def test_sar_to_dict(self):
        """Test SAR serialization."""
        sar = SAR(
            subject_entity_id="c-1",
            subject_name="Test AB",
            summary="Test summary"
        )
        sar.add_section("Test", "Content", "text")

        data = sar.to_dict()

        assert data["subject_entity_id"] == "c-1"
        assert data["summary"] == "Test summary"
        assert len(data["sections"]) == 1


class TestSARGenerator:
    """Tests for SARGenerator."""

    @pytest.fixture
    def generator(self):
        """Create a SAR generator."""
        return SARGenerator()

    @pytest.fixture
    def generator_with_graph(self):
        """Create generator with graph."""
        client = GraphClient()
        return SARGenerator(graph_client=client)

    @pytest.mark.asyncio
    async def test_generate_sar_no_graph(self, generator):
        """Test SAR generation without graph."""
        sar = await generator.generate_sar(
            entity_id="company-123",
            trigger_reason="Pattern match: Registration Mill",
            alert_ids=["alert-1", "alert-2"],
            created_by="test_user"
        )

        assert sar.subject_entity_id == "company-123"
        assert sar.trigger_reason == "Pattern match: Registration Mill"
        assert sar.created_by == "test_user"
        assert len(sar.sections) > 0
        assert sar.summary is not None

    @pytest.mark.asyncio
    async def test_generate_sar_with_graph(self, generator_with_graph):
        """Test SAR generation with graph data."""
        async with generator_with_graph.graph:
            from halo.graph.schema import Company

            company = Company(
                id="company-test",
                orgnr="5560125790",
                names=[{"name": "Suspicious AB"}],
                legal_form="AB",
                status={"code": "active", "text": "Aktiv"},
                employees={"count": 0},
                f_skatt={"registered": True},
            )
            await generator_with_graph.graph.add_company(company)

            sar = await generator_with_graph.generate_sar(
                entity_id="company-test",
                trigger_reason="High shell score"
            )

            assert sar.subject_entity_id == "company-test"
            # Subject name may not be directly extracted from graph data structure
            assert sar.subject_name is not None

    def test_format_entity_details_company(self, generator):
        """Test formatting company details."""
        entity = {
            "_type": "Company",
            "display_name": "Test AB",
            "orgnr": "5560125790",
            "legal_form": "AB",
            "status": {"text": "Aktiv"},
            "employees": {"count": 10},
            "f_skatt": {"registered": True},
            "vat": {"registered": True},
        }

        details = generator._format_entity_details(entity)

        assert details["Type"] == "Company (Företag)"
        assert details["Name"] == "Test AB"
        assert details["F-skatt"] == "Yes"

    def test_format_entity_details_person(self, generator):
        """Test formatting person details."""
        entity = {
            "_type": "Person",
            "display_name": "Johan Svensson",
            "personnummer": "PROTECTED",
            "nationality": "SE",
            "pep_status": {"is_pep": False},
        }

        details = generator._format_entity_details(entity)

        assert details["Type"] == "Person"
        assert details["Name"] == "Johan Svensson"

    def test_generate_summary(self, generator):
        """Test summary generation."""
        entity = {
            "_type": "Company",
            "display_name": "Test AB"
        }
        patterns = [
            {"typology": "shell_company_network"},
            {"typology": "tax_fraud"}
        ]
        risk = {"level": "high", "score": 0.8, "factors": ["factor1"]}

        summary = generator._generate_summary(entity, patterns, risk, "Pattern match")

        assert "Test AB" in summary
        assert "HIGH" in summary
        assert "2 fraud pattern" in summary

    def test_generate_recommendations(self, generator):
        """Test recommendation generation."""
        # Critical risk
        risk = {"level": "critical", "score": 0.95}
        patterns = [{"typology": "money_laundering"}]

        recs = generator._generate_recommendations(risk, patterns)

        assert len(recs) > 0
        assert any("IMMEDIATE" in r for r in recs)

        # Low risk
        risk = {"level": "low", "score": 0.2}
        recs = generator._generate_recommendations(risk, [])

        assert any("watchlist" in r.lower() for r in recs)

    def test_determine_priority(self, generator):
        """Test priority determination."""
        # Critical risk
        assert generator._determine_priority(
            {"level": "critical"},
            []
        ) == "urgent"

        # High risk
        assert generator._determine_priority(
            {"level": "high"},
            []
        ) == "high"

        # Critical pattern
        assert generator._determine_priority(
            {"level": "medium"},
            [{"severity": "critical"}]
        ) == "urgent"


class TestKonkursPrediction:
    """Tests for KonkursPrediction."""

    def test_prediction_creation(self):
        """Test konkurs prediction creation."""
        prediction = KonkursPrediction(
            company_id="company-123",
            konkurs_probability=0.65,
            horizon_months=12,
            risk_level="high",
            confidence=0.8,
            network_contagion_risk=0.4,
            director_risk_score=0.3,
            financial_health_score=0.5,
            distress_signals=["High debt", "Declining revenue"],
            survival_signals=["Long history"]
        )

        assert prediction.konkurs_probability == 0.65
        assert prediction.risk_level == "high"
        assert len(prediction.distress_signals) == 2

    def test_prediction_to_dict(self):
        """Test prediction serialization."""
        prediction = KonkursPrediction(
            company_id="c-1",
            konkurs_probability=0.3,
            horizon_months=12,
            risk_level="medium",
            confidence=0.7
        )

        data = prediction.to_dict()

        assert data["company_id"] == "c-1"
        assert data["konkurs_probability"] == 0.3
        assert "predicted_at" in data


class TestKonkursFeatures:
    """Tests for konkurs features."""

    def test_features_defined(self):
        """Test that feature categories are defined."""
        assert "network" in KONKURS_FEATURES
        assert "director" in KONKURS_FEATURES
        assert "trajectory" in KONKURS_FEATURES
        assert "industry" in KONKURS_FEATURES
        assert "lifecycle" in KONKURS_FEATURES

    def test_network_features(self):
        """Test network features."""
        network_features = KONKURS_FEATURES["network"]
        assert "pct_counterparties_in_distress" in network_features
        assert "avg_counterparty_risk_score" in network_features

    def test_director_features(self):
        """Test director features."""
        director_features = KONKURS_FEATURES["director"]
        assert "director_previous_konkurser" in director_features


class TestKonkursPredictor:
    """Tests for KonkursPredictor."""

    @pytest.fixture
    def predictor(self):
        """Create a konkurs predictor."""
        return KonkursPredictor()

    @pytest.fixture
    def predictor_with_graph(self):
        """Create predictor with graph."""
        client = GraphClient()
        return KonkursPredictor(graph_client=client)

    @pytest.mark.asyncio
    async def test_predict_no_graph(self, predictor):
        """Test prediction without graph."""
        prediction = await predictor.predict("company-123")

        # Without graph, company not found
        assert prediction.company_id == "company-123"
        assert prediction.confidence == 0.0

    @pytest.mark.asyncio
    async def test_predict_with_graph(self, predictor_with_graph):
        """Test prediction with graph data."""
        async with predictor_with_graph.graph:
            from halo.graph.schema import Company

            company = Company(
                id="healthy-company",
                orgnr="5560125790",
                status={"code": "active"},
                employees={"count": 50},
                formation={"date": "2010-01-01"},
            )
            await predictor_with_graph.graph.add_company(company)

            prediction = await predictor_with_graph.predict("healthy-company")

            assert prediction.company_id == "healthy-company"
            assert prediction.risk_level in ["low", "medium", "high", "critical"]
            assert 0 <= prediction.konkurs_probability <= 1

    @pytest.mark.asyncio
    async def test_predict_batch(self, predictor):
        """Test batch prediction."""
        predictions = await predictor.predict_batch(["c1", "c2", "c3"])

        assert len(predictions) == 3

    def test_calculate_network_contagion(self, predictor):
        """Test network contagion calculation."""
        features = {
            "pct_counterparties_in_distress": 0.3,
            "avg_counterparty_risk_score": 0.5
        }

        score = predictor._calculate_network_contagion(features)

        assert 0 <= score <= 1
        # Higher distress percentage should increase score
        assert score > 0

    def test_calculate_director_risk(self, predictor):
        """Test director risk calculation."""
        features = {
            "director_previous_konkurser": 2,
            "recent_director_changes": 3
        }

        score = predictor._calculate_director_risk(features)

        assert 0 <= score <= 1
        assert score > 0  # Has risk indicators

    def test_calculate_trajectory_risk(self, predictor):
        """Test trajectory risk calculation."""
        # Declining company
        features = {
            "employee_trend_12m": -0.3,
            "revenue_trend_12m": -0.25,
            "arsredovisning_delays": 2,
            "address_changes_12m": 1
        }

        score = predictor._calculate_trajectory_risk(features)

        assert 0 <= score <= 1
        assert score > 0.3  # Multiple risk indicators

    def test_calculate_financial_health(self, predictor):
        """Test financial health calculation."""
        # Healthy financials
        features = {
            "debt_to_equity": 0.3,
            "current_ratio": 2.0,
            "profit_margin": 0.1
        }

        score = predictor._calculate_financial_health(features)

        assert 0 <= score <= 1
        assert score > 0.5  # Healthy = higher score

        # Unhealthy financials
        features = {
            "debt_to_equity": 3.0,
            "current_ratio": 0.5,
            "profit_margin": -0.2
        }

        score = predictor._calculate_financial_health(features)
        assert score < 0.5  # Unhealthy = lower score

    def test_identify_distress_signals(self, predictor):
        """Test distress signal identification."""
        features = {
            "pct_counterparties_in_distress": 0.3,
            "director_previous_konkurser": 1,
            "employee_trend_12m": -0.4,
            "arsredovisning_delays": 1,
            "company_age_months": 18
        }
        company = {"status": {"code": "active"}}

        signals = predictor._identify_distress_signals(features, company)

        assert len(signals) >= 3

    def test_identify_survival_signals(self, predictor):
        """Test survival signal identification."""
        features = {
            "company_age_months": 100,
            "employee_trend_12m": 0.2,
            "revenue_trend_12m": 0.15,
            "pct_counterparties_in_distress": 0.02,
            "current_ratio": 2.0,
            "arsredovisning_delays": 0
        }
        company = {}

        signals = predictor._identify_survival_signals(features, company)

        assert len(signals) >= 3

    def test_get_industry_failure_rate(self, predictor):
        """Test industry failure rate lookup."""
        # High risk industry (hospitality)
        rate = predictor._get_industry_failure_rate("55")
        assert rate > 0.05

        # Medium risk
        rate = predictor._get_industry_failure_rate("70")
        assert rate > 0.03

        # Default
        rate = predictor._get_industry_failure_rate("99")
        assert rate == 0.03

    @pytest.mark.asyncio
    async def test_analyze_contagion_risk(self, predictor_with_graph):
        """Test contagion risk analysis."""
        async with predictor_with_graph.graph:
            from halo.graph.schema import Company
            from halo.graph.edges import OwnsEdge

            # Create network
            for i in range(3):
                company = Company(id=f"company-{i}", risk_score=0.3 * i)
                await predictor_with_graph.graph.add_company(company)

            await predictor_with_graph.graph.add_ownership(OwnsEdge(
                from_id="company-0", from_type="company", to_id="company-1"
            ))

            result = await predictor_with_graph.analyze_contagion_risk("company-0")

            assert result["source_company"] == "company-0"
            assert "contagion_risk" in result
            assert "affected_entities" in result
