"""
Tests for the pattern matching module (Layer 2).
"""

import pytest
from datetime import datetime

from halo.intelligence.patterns import (
    PatternMatcher,
    PatternMatch,
    FraudPattern,
    FRAUD_PATTERNS,
)
from halo.graph.client import GraphClient


class TestFraudPattern:
    """Tests for FraudPattern dataclass."""

    def test_fraud_pattern_creation(self):
        """Test fraud pattern creation."""
        pattern = FraudPattern(
            id="test_pattern",
            name="Test Pattern",
            description="A test pattern for testing",
            severity="high",
            typology="test",
            query="MATCH (n) RETURN n",
            extractor=lambda row: {"node": row.get("n")}
        )

        assert pattern.id == "test_pattern"
        assert pattern.severity == "high"
        assert pattern.enabled is True

    def test_fraud_pattern_disabled(self):
        """Test disabled fraud pattern."""
        pattern = FraudPattern(
            id="disabled_pattern",
            name="Disabled",
            description="Disabled pattern",
            severity="low",
            typology="test",
            query="",
            extractor=lambda x: x,
            enabled=False
        )

        assert pattern.enabled is False


class TestFraudPatterns:
    """Tests for built-in fraud patterns."""

    def test_patterns_defined(self):
        """Test that fraud patterns are defined."""
        assert len(FRAUD_PATTERNS) >= 5

        # Check key patterns exist
        assert "registration_mill" in FRAUD_PATTERNS
        assert "phoenix" in FRAUD_PATTERNS
        assert "circular_ownership" in FRAUD_PATTERNS
        assert "invoice_factory" in FRAUD_PATTERNS
        assert "layered_ownership" in FRAUD_PATTERNS

    def test_pattern_properties(self):
        """Test pattern properties are valid."""
        valid_severities = {"low", "medium", "high", "critical"}

        for pattern_id, pattern in FRAUD_PATTERNS.items():
            assert pattern.id == pattern_id
            assert pattern.name
            assert pattern.description
            assert pattern.severity in valid_severities
            assert pattern.typology
            assert pattern.query
            assert callable(pattern.extractor)

    def test_registration_mill_pattern(self):
        """Test registration mill pattern definition."""
        pattern = FRAUD_PATTERNS["registration_mill"]

        assert pattern.severity == "high"
        assert pattern.typology == "shell_company_network"
        assert "Address" in pattern.query
        assert "REGISTERED_AT" in pattern.query
        assert "DIRECTS" in pattern.query

    def test_phoenix_pattern(self):
        """Test phoenix pattern definition."""
        pattern = FRAUD_PATTERNS["phoenix"]

        assert pattern.severity == "medium"
        assert pattern.typology == "corporate_fraud"
        assert "dissolved" in pattern.query.lower() or "konkurs" in pattern.query.lower()

    def test_circular_ownership_pattern(self):
        """Test circular ownership pattern."""
        pattern = FRAUD_PATTERNS["circular_ownership"]

        assert pattern.severity == "high"
        assert pattern.typology == "money_laundering"
        assert "OWNS" in pattern.query
        assert "*" in pattern.query  # Variable path length


class TestPatternMatch:
    """Tests for PatternMatch."""

    def test_pattern_match_creation(self):
        """Test pattern match creation."""
        match = PatternMatch(
            pattern_id="test",
            pattern_name="Test Pattern",
            severity="high",
            typology="test",
            match_data={"company": {"id": "123"}},
            entity_ids=["123", "456"]
        )

        assert match.pattern_id == "test"
        assert match.severity == "high"
        assert len(match.entity_ids) == 2
        assert match.detected_at is not None

    def test_pattern_match_to_alert(self):
        """Test converting match to alert format."""
        match = PatternMatch(
            pattern_id="registration_mill",
            pattern_name="Registration Mill",
            severity="high",
            typology="shell_company_network",
            match_data={"address": "addr-1"},
            entity_ids=["company-1", "company-2"]
        )

        alert = match.to_alert()

        assert alert["alert_type"] == "pattern_match"
        assert alert["pattern_type"] == "registration_mill"
        assert alert["severity"] == "high"
        assert "Registration Mill" in alert["title"]
        assert alert["entity_ids"] == ["company-1", "company-2"]


class TestPatternMatcher:
    """Tests for PatternMatcher."""

    @pytest.fixture
    def matcher(self):
        """Create a pattern matcher with graph client."""
        client = GraphClient()
        return PatternMatcher(client)

    def test_matcher_creation(self, matcher):
        """Test matcher creation."""
        assert matcher.graph is not None
        assert len(matcher.patterns) > 0

    def test_add_pattern(self, matcher):
        """Test adding custom pattern."""
        custom = FraudPattern(
            id="custom_pattern",
            name="Custom",
            description="Custom pattern",
            severity="low",
            typology="custom",
            query="MATCH (n) RETURN n",
            extractor=lambda x: x
        )

        matcher.add_pattern(custom)
        assert "custom_pattern" in matcher.patterns

    def test_disable_enable_pattern(self, matcher):
        """Test disabling and enabling patterns."""
        pattern_id = list(matcher.patterns.keys())[0]

        matcher.disable_pattern(pattern_id)
        assert matcher.patterns[pattern_id].enabled is False

        matcher.enable_pattern(pattern_id)
        assert matcher.patterns[pattern_id].enabled is True

    def test_get_patterns_by_typology(self, matcher):
        """Test getting patterns by typology."""
        ml_patterns = matcher.get_patterns_by_typology("money_laundering")
        assert len(ml_patterns) >= 1
        assert all(p.typology == "money_laundering" for p in ml_patterns)

        shell_patterns = matcher.get_patterns_by_typology("shell_company_network")
        assert len(shell_patterns) >= 1

    def test_add_entity_filter(self, matcher):
        """Test adding entity filter to query."""
        original_query = """
            MATCH (c:Company)-[:REGISTERED_AT]->(a:Address)
            WHERE c.status = 'active'
            RETURN c, a
        """

        filtered = matcher._add_entity_filter(original_query, "company-123", "Company")

        assert "company-123" in filtered

    def test_extract_entity_ids(self, matcher):
        """Test extracting entity IDs from match data."""
        match_data = {
            "company": {"id": "company-1", "name": "Test AB"},
            "address": {"id": "address-1"},
            "directors": [
                {"id": "person-1"},
                {"id": "person-2"}
            ]
        }

        entity_ids = matcher._extract_entity_ids(match_data)

        assert "company-1" in entity_ids
        assert "address-1" in entity_ids
        assert "person-1" in entity_ids
        assert "person-2" in entity_ids


class TestPatternExtractors:
    """Tests for pattern extractors."""

    def test_registration_mill_extractor(self):
        """Test registration mill extractor."""
        pattern = FRAUD_PATTERNS["registration_mill"]
        row = {
            "address": {"id": "addr-1"},
            "company_count": 10,
            "companies": [{"id": "c1"}, {"id": "c2"}],
            "shared_directors": [{"id": "p1"}]
        }

        result = pattern.extractor(row)

        assert "address" in result
        assert "company_count" in result
        assert result["company_count"] == 10

    def test_phoenix_extractor(self):
        """Test phoenix extractor."""
        pattern = FRAUD_PATTERNS["phoenix"]
        row = {
            "old_company": {"id": "old-1", "name": "Old AB"},
            "new_company": {"id": "new-1", "name": "New AB"},
            "director": {"id": "person-1"}
        }

        result = pattern.extractor(row)

        assert "old_company" in result
        assert "new_company" in result
        assert "director" in result

    def test_circular_ownership_extractor(self):
        """Test circular ownership extractor."""
        pattern = FRAUD_PATTERNS["circular_ownership"]
        row = {
            "company": {"id": "company-1"},
            "path": ["c1", "c2", "c3", "c1"],
            "loop_length": 3
        }

        result = pattern.extractor(row)

        assert "company" in result
        assert "loop_path" in result
        assert result["loop_length"] == 3
