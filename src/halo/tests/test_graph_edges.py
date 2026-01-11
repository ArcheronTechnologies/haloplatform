"""
Tests for the graph edges module.
"""

import pytest
from datetime import date, datetime

from halo.graph.edges import (
    DirectsEdge,
    OwnsEdge,
    BeneficialOwnerEdge,
    RegisteredAtEdge,
    LivesAtEdge,
    CoDirectorEdge,
    CoRegisteredEdge,
    TransactsEdge,
    SameAsEdge,
    OwnsPropertyEdge,
)


class TestDirectsEdge:
    """Tests for DirectsEdge."""

    def test_directs_edge_creation(self):
        """Test directorship edge creation."""
        edge = DirectsEdge(
            from_id="person-123",
            to_id="company-456",
            role="styrelseledamot",
            signing_rights="ensam",
            from_date=date(2020, 1, 1)
        )

        assert edge.from_id == "person-123"
        assert edge.to_id == "company-456"
        assert edge.role == "styrelseledamot"
        assert edge.is_active is True

    def test_directs_edge_inactive(self):
        """Test inactive directorship."""
        edge = DirectsEdge(
            from_id="person-123",
            to_id="company-456",
            role="vd",
            from_date=date(2020, 1, 1),
            to_date=date(2023, 12, 31)
        )

        assert edge.is_active is False


class TestOwnsEdge:
    """Tests for OwnsEdge."""

    def test_owns_edge_creation(self):
        """Test ownership edge creation."""
        edge = OwnsEdge(
            from_id="person-123",
            from_type="person",
            to_id="company-456",
            share=75.0,
            direct=True,
            from_date=date(2020, 1, 1)
        )

        assert edge.share == 75.0
        assert edge.is_majority is True
        assert edge.is_active is True

    def test_owns_edge_minority(self):
        """Test minority ownership."""
        edge = OwnsEdge(
            from_id="company-123",
            from_type="company",
            to_id="company-456",
            share=25.0,
            direct=True
        )

        assert edge.is_majority is False


class TestBeneficialOwnerEdge:
    """Tests for BeneficialOwnerEdge."""

    def test_beneficial_owner_edge(self):
        """Test beneficial owner edge."""
        edge = BeneficialOwnerEdge(
            from_id="person-123",
            to_id="company-456",
            share=60.0,
            control_type="ownership",
            layers=3,
            path=["company-a", "company-b", "company-456"]
        )

        assert edge.share == 60.0
        assert edge.layers == 3
        assert edge.is_layered is True

    def test_direct_beneficial_owner(self):
        """Test direct beneficial owner."""
        edge = BeneficialOwnerEdge(
            from_id="person-123",
            to_id="company-456",
            share=100.0,
            control_type="ownership",
            layers=1,
            path=["company-456"]
        )

        assert edge.is_layered is False


class TestRegisteredAtEdge:
    """Tests for RegisteredAtEdge."""

    def test_registered_at_edge(self):
        """Test registration edge."""
        edge = RegisteredAtEdge(
            from_id="company-123",
            to_id="address-456",
            type="registered",
            from_date=date(2020, 1, 1)
        )

        assert edge.type == "registered"
        assert edge.is_current is True

    def test_historical_registration(self):
        """Test historical registration."""
        edge = RegisteredAtEdge(
            from_id="company-123",
            to_id="address-456",
            type="registered",
            from_date=date(2020, 1, 1),
            to_date=date(2023, 1, 1)
        )

        assert edge.is_current is False


class TestLivesAtEdge:
    """Tests for LivesAtEdge."""

    def test_lives_at_edge(self):
        """Test residence edge."""
        edge = LivesAtEdge(
            from_id="person-123",
            to_id="address-456",
            from_date=date(2020, 1, 1)
        )

        assert edge.is_current is True


class TestCoDirectorEdge:
    """Tests for CoDirectorEdge."""

    def test_co_director_edge(self):
        """Test co-director relationship."""
        edge = CoDirectorEdge(
            from_id="person-123",
            to_id="person-456",
            shared_companies=[
                {"company_id": "company-a", "overlap_period": "2020-2024"},
                {"company_id": "company-b", "overlap_period": "2021-2024"}
            ],
            co_occurrence=2,
            strength=0.8
        )

        assert edge.co_occurrence == 2
        assert edge.is_strong_connection is True

    def test_weak_co_director(self):
        """Test weak co-director relationship."""
        edge = CoDirectorEdge(
            from_id="person-123",
            to_id="person-456",
            shared_companies=[{"company_id": "company-a"}],
            co_occurrence=1,
            strength=0.3
        )

        assert edge.is_strong_connection is False


class TestCoRegisteredEdge:
    """Tests for CoRegisteredEdge."""

    def test_co_registered_edge(self):
        """Test co-registered companies."""
        edge = CoRegisteredEdge(
            from_id="company-123",
            to_id="company-456",
            shared_addresses=[{"address_id": "addr-1"}],
            shared_directors=["person-1", "person-2"],
            formation_gap_days=15,
            strength=0.9
        )

        assert edge.is_suspicious_gap is True

    def test_non_suspicious_gap(self):
        """Test non-suspicious formation gap."""
        edge = CoRegisteredEdge(
            from_id="company-123",
            to_id="company-456",
            formation_gap_days=365,
            strength=0.3
        )

        assert edge.is_suspicious_gap is False


class TestTransactsEdge:
    """Tests for TransactsEdge."""

    def test_transacts_edge(self):
        """Test transaction edge."""
        edge = TransactsEdge(
            from_id="account-123",
            to_id="account-456",
            amount=200000.0,
            currency="SEK",
            date=datetime(2024, 1, 15, 10, 30),
            pattern_flags=["large_round_amount"]
        )

        assert edge.amount == 200000.0
        assert edge.is_large is True
        assert edge.is_flagged is True

    def test_small_transaction(self):
        """Test small transaction."""
        edge = TransactsEdge(
            from_id="account-123",
            to_id="account-456",
            amount=5000.0,
            currency="SEK"
        )

        assert edge.is_large is False
        assert edge.is_flagged is False


class TestSameAsEdge:
    """Tests for SameAsEdge."""

    def test_same_as_edge(self):
        """Test entity resolution edge."""
        edge = SameAsEdge(
            from_id="person-123",
            from_type="Person",
            to_id="person-456",
            to_type="Person",
            confidence=0.95,
            method="fuzzy_match",
            evidence=["same_personnummer", "similar_name"]
        )

        assert edge.confidence == 0.95
        assert edge.is_high_confidence is True

    def test_low_confidence_match(self):
        """Test low confidence match."""
        edge = SameAsEdge(
            from_id="person-123",
            from_type="Person",
            to_id="person-456",
            to_type="Person",
            confidence=0.7,
            method="name_similarity"
        )

        assert edge.is_high_confidence is False


class TestOwnsPropertyEdge:
    """Tests for OwnsPropertyEdge."""

    def test_owns_property_edge(self):
        """Test property ownership edge."""
        edge = OwnsPropertyEdge(
            from_id="person-123",
            from_type="person",
            to_id="property-456",
            share=50.0,
            from_date=date(2020, 1, 1),
            purchase_price=5000000.0
        )

        assert edge.share == 50.0
        assert edge.purchase_price == 5000000.0
        assert edge.is_current is True
