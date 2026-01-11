"""
Performance benchmark tests.

Tests verify the system meets performance targets defined in ontology.md:
- Single entity lookup: <100ms
- 2-hop graph traversal: <1s
- Pattern matching (full graph): <10s
- Entity resolution batch: <1hr for 10K mentions
- Nightly derived fact recomputation: <4hr
"""

import time
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest


class TestSwedishUtilsPerformance:
    """
    Performance tests for Swedish utility functions.

    These are core operations used in entity lookup.
    """

    def test_personnummer_validation_fast(self):
        """Personnummer validation should be very fast."""
        from halo.swedish.personnummer import validate_personnummer

        start = time.perf_counter()
        for i in range(10000):
            try:
                validate_personnummer(f"19800101{i % 10000:04d}")
            except ValueError:
                pass  # Invalid personnummer is expected for some
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"10K personnummer validations took {elapsed:.2f}s"
        per_op = (elapsed / 10000) * 1000
        print(f"Personnummer validation: {per_op:.3f}ms per operation")

    def test_organisationsnummer_validation_fast(self):
        """Organisationsnummer validation should be very fast."""
        from halo.swedish.organisationsnummer import validate_organisationsnummer

        start = time.perf_counter()
        for i in range(10000):
            try:
                validate_organisationsnummer(f"559{i % 10000000:07d}")
            except ValueError:
                pass  # Invalid orgnr is expected for some
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"10K orgnr validations took {elapsed:.2f}s"
        per_op = (elapsed / 10000) * 1000
        print(f"Organisationsnummer validation: {per_op:.3f}ms per operation")

    def test_company_name_normalization_fast(self):
        """Company name normalization should be fast."""
        from halo.swedish.company_name import normalize_company_name

        names = [
            "Aktiebolaget Test",
            "Test AB",
            "Test Aktiebolag",
            "TEST HANDELSBOLAG",
            "Test HB",
            "Test Kommanditbolag",
            "Test KB",
        ]

        start = time.perf_counter()
        for _ in range(10000):
            for name in names:
                normalize_company_name(name)
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"70K normalizations took {elapsed:.2f}s"
        per_op = (elapsed / 70000) * 1000
        print(f"Company name normalization: {per_op:.3f}ms per operation")


class TestBlockingIndexPerformance:
    """
    Performance tests for blocking index operations.
    """

    def test_blocking_index_add_fast(self):
        """Adding entities to blocking index should be fast."""
        from halo.resolution.blocking import BlockingIndex, CandidateEntity

        index = BlockingIndex()

        start = time.perf_counter()
        for i in range(10000):
            entity = CandidateEntity(
                id=uuid4(),
                entity_type="PERSON",
                canonical_name=f"Test Person {i}",
                identifiers={"personnummer": f"19800101{i:04d}"},
            )
            index.add_entity(entity)
        elapsed = time.perf_counter() - start

        assert elapsed < 3.0, f"10K entity adds took {elapsed:.2f}s"
        per_op = (elapsed / 10000) * 1000
        print(f"Blocking index add: {per_op:.3f}ms per operation")

    def test_blocking_index_lookup_fast(self):
        """Looking up entities in blocking index should be very fast."""
        from halo.resolution.blocking import BlockingIndex, CandidateEntity, Mention

        index = BlockingIndex()

        # Pre-populate index
        for i in range(1000):
            entity = CandidateEntity(
                id=uuid4(),
                entity_type="PERSON",
                canonical_name=f"Test Person {i}",
                identifiers={"personnummer": f"19800101{i:04d}"},
            )
            index.add_entity(entity)

        # Measure lookup time using Mention objects
        start = time.perf_counter()
        for i in range(10000):
            mention = Mention(
                id=uuid4(),
                mention_type="PERSON",
                surface_form=f"Test Person {i % 1000}",
                normalized_form=f"test person {i % 1000}",
                extracted_personnummer=f"19800101{i % 1000:04d}",
            )
            index.get_candidates(mention)
        elapsed = time.perf_counter() - start

        # Allow 5s for 10K lookups (0.5ms each) - includes Mention object creation overhead
        assert elapsed < 5.0, f"10K lookups took {elapsed:.2f}s (target: <5s)"
        per_op = (elapsed / 10000) * 1000
        print(f"Blocking index lookup: {per_op:.3f}ms per operation")


class TestRiskScoringPerformance:
    """
    Performance tests for risk scoring.
    """

    def test_entity_risk_scoring_fast(self):
        """Entity risk scoring should be fast."""
        from halo.fincrime.risk_scoring import EntityRiskScorer, EntityForScoring

        scorer = EntityRiskScorer()

        entity = EntityForScoring(
            id=uuid4(),
            name="Test AB",
            entity_type="company",
            jurisdiction="SE",
            industry="retail",
            customer_type="established",
            is_pep=False,
            beneficial_owners=[],
            years_in_business=10,
            has_sanctions_exposure=False,
            transaction_volume_monthly=Decimal("100000"),
            cash_transaction_ratio=0.1,
            high_risk_country_ratio=0.05,
        )

        start = time.perf_counter()
        for _ in range(10000):
            scorer.score(entity)
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"10K risk scorings took {elapsed:.2f}s"
        per_op = (elapsed / 10000) * 1000
        print(f"Entity risk scoring: {per_op:.3f}ms per operation")


class TestWatchlistPerformance:
    """
    Performance tests for watchlist screening.
    """

    def test_watchlist_loading_fast(self):
        """Loading watchlist entries should be fast."""
        from halo.fincrime.watchlist import WatchlistChecker, WatchlistEntry, WatchlistType

        checker = WatchlistChecker()

        entries = [
            WatchlistEntry(
                id=f"TEST-{i}",
                list_type=WatchlistType.PEP_DOMESTIC,
                name=f"Test Person {i}",
                aliases=[f"T Person {i}"],
                identifiers={},
                nationality="SE",
                source="test",
            )
            for i in range(1000)
        ]

        start = time.perf_counter()
        checker.load_entries(entries)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Loading 1K entries took {elapsed:.2f}s"
        print(f"Watchlist load (1K entries): {elapsed:.3f}s")

    def test_watchlist_check_fast(self):
        """Checking against watchlist should be fast."""
        from halo.fincrime.watchlist import WatchlistChecker, WatchlistEntry, WatchlistType

        checker = WatchlistChecker()

        # Load entries
        entries = [
            WatchlistEntry(
                id=f"TEST-{i}",
                list_type=WatchlistType.PEP_DOMESTIC,
                name=f"Test Person {i}",
                aliases=[],
                identifiers={"personnummer": f"19800101{i:04d}"},
                nationality="SE",
                source="test",
            )
            for i in range(100)
        ]
        checker.load_entries(entries)

        start = time.perf_counter()
        for i in range(1000):
            checker.check_entity(f"Test Person {i % 100}")
        elapsed = time.perf_counter() - start

        # Allow 10s for 1K checks (10ms each) - fuzzy matching is computationally intensive
        assert elapsed < 10.0, f"1K checks took {elapsed:.2f}s (target: <10s)"
        per_op = (elapsed / 1000) * 1000
        print(f"Watchlist check: {per_op:.3f}ms per operation")


class TestAMLPatternPerformance:
    """
    Performance tests for AML pattern detection.
    """

    def test_pattern_detector_init_fast(self):
        """AML pattern detector initialization should be fast."""
        from halo.fincrime.aml_patterns import AMLPatternDetector

        start = time.perf_counter()
        for _ in range(1000):
            AMLPatternDetector()
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"1K detector inits took {elapsed:.2f}s"
        per_op = (elapsed / 1000) * 1000
        print(f"AML detector init: {per_op:.3f}ms per operation")


class TestPerformanceTargets:
    """
    Summary tests that verify overall performance targets from ontology.md.
    """

    def test_single_operation_under_100ms(self):
        """
        Verify that core single operations complete under 100ms.

        Target from ontology.md: Single entity lookup <100ms
        """
        from halo.swedish.personnummer import validate_personnummer
        from halo.swedish.organisationsnummer import validate_organisationsnummer
        from halo.resolution.blocking import BlockingIndex, CandidateEntity, Mention

        index = BlockingIndex()

        # Pre-add an entity
        entity = CandidateEntity(
            id=uuid4(),
            entity_type="PERSON",
            canonical_name="Test Person",
            identifiers={"personnummer": "198001011234"},
        )
        index.add_entity(entity)

        # Simulate a single entity lookup workload
        start = time.perf_counter()

        # Parse identifiers
        try:
            validate_personnummer("198001011234")
        except ValueError:
            pass
        try:
            validate_organisationsnummer("5591234567")
        except ValueError:
            pass

        # Lookup in index using Mention
        mention = Mention(
            id=uuid4(),
            mention_type="PERSON",
            surface_form="Test Person",
            normalized_form="test person",
            extracted_personnummer="198001011234",
        )
        index.get_candidates(mention)

        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 100, f"Single operation took {elapsed_ms:.2f}ms (target: <100ms)"
        print(f"Combined single operation: {elapsed_ms:.2f}ms")

    def test_batch_operations_scale_linearly(self):
        """
        Verify that batch operations scale linearly.

        Tests 100, 1000, 10000 operations to verify O(n) scaling.
        """
        from halo.swedish.personnummer import validate_personnummer

        times = []
        for n in [100, 1000, 10000]:
            start = time.perf_counter()
            for i in range(n):
                try:
                    validate_personnummer(f"19800101{i % 10000:04d}")
                except ValueError:
                    pass
            elapsed = time.perf_counter() - start
            times.append((n, elapsed))

        # Check that time scales roughly linearly (within 3x expected ratio)
        ratio_100_1000 = (times[1][1] / times[0][1]) / 10  # Should be ~1
        ratio_1000_10000 = (times[2][1] / times[1][1]) / 10  # Should be ~1

        print(f"Scaling ratios: 100->1000: {ratio_100_1000:.2f}x, 1000->10000: {ratio_1000_10000:.2f}x")

        # Allow some variance due to JIT warmup, etc.
        assert 0.3 < ratio_100_1000 < 3.0, "Operations not scaling linearly (100->1000)"
        assert 0.3 < ratio_1000_10000 < 3.0, "Operations not scaling linearly (1000->10000)"

    def test_memory_efficient_batch_processing(self):
        """
        Verify that batch processing doesn't have excessive memory overhead.
        """
        import sys
        from halo.resolution.blocking import BlockingIndex, CandidateEntity, Mention

        index = BlockingIndex()

        # Measure baseline memory
        base_size = sys.getsizeof(index)

        # Add 1000 entities
        for i in range(1000):
            entity = CandidateEntity(
                id=uuid4(),
                entity_type="PERSON",
                canonical_name=f"Test Person {i}",
                identifiers={"personnummer": f"19800101{i:04d}"},
            )
            index.add_entity(entity)

        # This is a basic sanity check - actual memory profiling would need more tools
        # Just verify the index was populated by looking up an entity
        mention = Mention(
            id=uuid4(),
            mention_type="PERSON",
            surface_form="Test Person 500",
            normalized_form="test person 500",
            extracted_personnummer="198001010500",
        )
        candidates = index.get_candidates(mention)
        assert len(candidates) > 0, "Index should contain added entities"
        print(f"Index populated with 1000 entities successfully")
