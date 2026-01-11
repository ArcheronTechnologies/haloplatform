"""
Pytest configuration and shared fixtures for Halo tests.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Generator
from uuid import uuid4

import pytest

from halo.entities.schemas import Entity
from halo.fincrime.watchlist import WatchlistChecker, WatchlistEntry, WatchlistType
from halo.fincrime.aml_patterns import AMLPatternDetector, TransactionForAnalysis
from halo.fincrime.risk_scoring import (
    EntityRiskScorer,
    TransactionRiskScorer,
    EntityForScoring,
    TransactionForScoring,
    RiskLevel,
)
from halo.investigation.case_manager import CaseManager


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_entity() -> Entity:
    """Create a sample entity for testing."""
    return Entity(
        id=uuid4(),
        name="Test AB",
        entity_type="company",
        identifier="5591234567",
        status="active",
        risk_score=0.5,
        risk_level="medium",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_person() -> Entity:
    """Create a sample person entity for testing."""
    return Entity(
        id=uuid4(),
        name="Anna Andersson",
        entity_type="person",
        identifier="198001011234",
        status="active",
        risk_score=0.3,
        risk_level="low",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def aml_detector() -> AMLPatternDetector:
    """Create an AML pattern detector for testing."""
    return AMLPatternDetector()


@pytest.fixture
def entity_risk_scorer() -> EntityRiskScorer:
    """Create an entity risk scorer for testing."""
    return EntityRiskScorer()


@pytest.fixture
def transaction_risk_scorer() -> TransactionRiskScorer:
    """Create a transaction risk scorer for testing."""
    return TransactionRiskScorer()


@pytest.fixture
def case_manager() -> CaseManager:
    """Create a case manager for testing."""
    return CaseManager()


@pytest.fixture
def watchlist_checker() -> WatchlistChecker:
    """Create a watchlist checker with sample entries."""
    checker = WatchlistChecker()

    # Add sample entries
    sample_entries = [
        WatchlistEntry(
            id="SE-PEP-001",
            list_type=WatchlistType.PEP_DOMESTIC,
            name="Test Testsson",
            aliases=["T. Testsson"],
            identifiers={"personnummer": "19800101-1234"},
            nationality="SE",
            description="Sample PEP entry for testing",
            source="test_data",
        ),
        WatchlistEntry(
            id="EU-SANC-001",
            list_type=WatchlistType.SANCTIONS_EU,
            name="Sanctioned Person",
            aliases=["S. Person", "Sanctioned P."],
            identifiers={"passport": "AB123456"},
            nationality="RU",
            description="Sample sanctions entry",
            source="test_data",
        ),
        WatchlistEntry(
            id="SE-SANC-001",
            list_type=WatchlistType.SANCTIONS_SE,
            name="Svensk Sanktionerad",
            identifiers={"personnummer": "19700515-5678"},
            nationality="SE",
            source="test_data",
        ),
    ]

    checker.load_entries(sample_entries)
    return checker


@pytest.fixture
def sample_transactions() -> list[TransactionForAnalysis]:
    """Create sample transactions for AML testing."""
    base_time = datetime.utcnow()
    entity_id = uuid4()

    return [
        TransactionForAnalysis(
            id=uuid4(),
            entity_id=entity_id,
            amount=Decimal("145000"),  # Just under 150k threshold
            currency="SEK",
            timestamp=base_time - timedelta(hours=1),
            transaction_type="deposit",
            counterparty_id=None,
            counterparty_name="Cash deposit",
        ),
        TransactionForAnalysis(
            id=uuid4(),
            entity_id=entity_id,
            amount=Decimal("148000"),  # Just under 150k threshold
            currency="SEK",
            timestamp=base_time - timedelta(hours=2),
            transaction_type="deposit",
            counterparty_id=None,
            counterparty_name="Cash deposit",
        ),
        TransactionForAnalysis(
            id=uuid4(),
            entity_id=entity_id,
            amount=Decimal("140000"),  # Just under 150k threshold
            currency="SEK",
            timestamp=base_time - timedelta(hours=3),
            transaction_type="deposit",
            counterparty_id=None,
            counterparty_name="Cash deposit",
        ),
    ]


@pytest.fixture
def structuring_transactions() -> list[TransactionForAnalysis]:
    """Create transactions that exhibit structuring pattern."""
    base_time = datetime.utcnow()
    entity_id = uuid4()

    # Multiple deposits just under the 150,000 SEK threshold
    return [
        TransactionForAnalysis(
            id=uuid4(),
            entity_id=entity_id,
            amount=Decimal("149000"),
            currency="SEK",
            timestamp=base_time - timedelta(hours=i),
            transaction_type="deposit",
            counterparty_id=None,
            counterparty_name="Cash deposit",
        )
        for i in range(5)  # 5 deposits in 5 hours
    ]


@pytest.fixture
def high_risk_entity() -> EntityForScoring:
    """Create a high-risk entity for scoring tests."""
    return EntityForScoring(
        id=uuid4(),
        name="Offshore Holdings Ltd",
        entity_type="company",
        jurisdiction="CY",  # Cyprus - high risk
        industry="cryptocurrency",  # High risk industry
        customer_type="non_face_to_face",
        is_pep=True,
        beneficial_owners=[
            {"name": "Unknown", "country": "RU", "ownership_percent": 100}
        ],
        years_in_business=1,
        has_sanctions_exposure=True,
        transaction_volume_monthly=Decimal("5000000"),
        cash_transaction_ratio=0.4,
        high_risk_country_ratio=0.8,
    )


@pytest.fixture
def low_risk_entity() -> EntityForScoring:
    """Create a low-risk entity for scoring tests."""
    return EntityForScoring(
        id=uuid4(),
        name="Svenska Försäkringar AB",
        entity_type="company",
        jurisdiction="SE",  # Sweden - low risk
        industry="insurance",  # Low risk, regulated
        customer_type="established",
        is_pep=False,
        beneficial_owners=[
            {"name": "Erik Eriksson", "country": "SE", "ownership_percent": 100}
        ],
        years_in_business=25,
        has_sanctions_exposure=False,
        transaction_volume_monthly=Decimal("1000000"),
        cash_transaction_ratio=0.01,
        high_risk_country_ratio=0.05,
    )
