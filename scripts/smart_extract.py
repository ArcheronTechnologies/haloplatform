#!/usr/bin/env python3
"""
Smart company extraction using multiple strategies.

Strategies:
1. Sequential scan - Scan around known working org numbers
2. High-hit prefix scan - Focus on prefixes with high success rates
3. Checksum-valid generation - Generate valid org numbers in productive ranges

Goal: Get to 10,000+ companies with real data.

Rate limits respected: ~40 req/second with batching, 0.5s pause between batches.
"""

import asyncio
import json
import logging
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TARGET_COMPANIES = 10000
BATCH_SIZE = 20  # Concurrent requests per batch
BATCH_DELAY = 0.5  # Seconds between batches (rate limiting)
CHECKPOINT_INTERVAL = 500  # Save progress every N candidates


def luhn_checksum(digits: list[int]) -> int:
    """Calculate Luhn checksum digit."""
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - (total % 10)) % 10


def make_valid_orgnr(prefix_9: str) -> str:
    """Add valid checksum digit to 9-digit prefix."""
    digits = [int(d) for d in prefix_9]
    check = luhn_checksum(digits)
    return prefix_9 + str(check)


def generate_sequential_range(base_orgnr: str, range_size: int = 100) -> list[str]:
    """Generate org numbers around a known working one."""
    orgnrs = []
    base_num = int(base_orgnr[:9])  # Without checksum

    for offset in range(-range_size // 2, range_size // 2):
        candidate = str(base_num + offset).zfill(9)
        if len(candidate) == 9:
            valid_orgnr = make_valid_orgnr(candidate)
            orgnrs.append(valid_orgnr)

    return orgnrs


def generate_prefix_range(prefix: str, count: int = 500) -> list[str]:
    """Generate random valid org numbers with given prefix."""
    orgnrs = set()
    prefix_len = len(prefix)

    while len(orgnrs) < count:
        # Fill remaining digits randomly
        remaining = 9 - prefix_len
        suffix = ''.join(str(random.randint(0, 9)) for _ in range(remaining))
        candidate = prefix + suffix
        valid_orgnr = make_valid_orgnr(candidate)
        orgnrs.add(valid_orgnr)

    return list(orgnrs)


async def test_orgnr(adapter: BolagsverketHVDAdapter, orgnr: str) -> dict | None:
    """Test if an org number exists and has documents."""
    try:
        # Try to list documents (faster than full fetch)
        docs = await adapter.list_annual_reports(orgnr)
        if docs:
            return {
                "orgnr": orgnr,
                "document_count": len(docs),
                "latest_doc": docs[0].get("dokumentId") if docs else None
            }
        return None
    except Exception:
        return None


async def batch_test(
    adapter: BolagsverketHVDAdapter,
    orgnrs: list[str],
    batch_size: int = BATCH_SIZE,
    checkpoint_path: Path = None,
    already_found: list[dict] = None
) -> list[dict]:
    """Test many org numbers with rate limiting and checkpointing."""
    found = already_found or []
    total = len(orgnrs)

    for i in range(0, total, batch_size):
        batch = orgnrs[i:i + batch_size]

        # Test batch concurrently
        tasks = [test_orgnr(adapter, orgnr) for orgnr in batch]
        results = await asyncio.gather(*tasks)

        # Collect successes
        for result in results:
            if result:
                found.append(result)

        # Progress
        tested = min(i + batch_size, total)
        if tested % 100 == 0 or tested == total:
            logger.info(f"Progress: {tested}/{total} tested, {len(found)} found ({100*len(found)/tested:.1f}% hit rate)")

        # Checkpoint save
        if checkpoint_path and tested % CHECKPOINT_INTERVAL == 0:
            save_checkpoint(checkpoint_path, found, tested, total)

        # Rate limit pause
        await asyncio.sleep(BATCH_DELAY)

    return found


def save_checkpoint(path: Path, found: list[dict], tested: int, total: int):
    """Save progress checkpoint."""
    with open(path, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tested": tested,
            "total": total,
            "found": found,
            "hit_rate": len(found) / tested if tested > 0 else 0,
        }, f, indent=2)
    logger.info(f"Checkpoint saved: {len(found)} companies found")


async def main():
    print("=" * 70)
    print("SMART COMPANY EXTRACTION - SCALE TO 10,000")
    print("=" * 70)

    # Load existing data
    existing_path = Path("data/extraction_combined/results.json")
    if existing_path.exists():
        with open(existing_path) as f:
            existing = json.load(f)
        existing_orgnrs = {c["orgnr"] for c in existing}
        print(f"\nExisting companies in database: {len(existing_orgnrs)}")
    else:
        existing_orgnrs = set()
        existing = []

    # Load already-found org numbers from previous runs
    new_orgnrs_path = Path("data/orgnrs_new_batch.json")
    if new_orgnrs_path.exists():
        with open(new_orgnrs_path) as f:
            already_found_orgnrs = set(json.load(f))
        print(f"Already found in previous runs: {len(already_found_orgnrs)}")
    else:
        already_found_orgnrs = set()

    # Calculate how many more we need
    total_have = len(existing_orgnrs) + len(already_found_orgnrs)
    need_more = max(0, TARGET_COMPANIES - total_have)
    print(f"Total companies we have: {total_have}")
    print(f"Target: {TARGET_COMPANIES}")
    print(f"Need to find: {need_more} more")

    if need_more == 0:
        print("\n✓ Already have enough companies!")
        return

    # Combine known org numbers to exclude
    all_known = existing_orgnrs | already_found_orgnrs

    # Initialize adapter
    adapter = BolagsverketHVDAdapter()

    # Strategy 1: Analyze existing successful org numbers
    print("\n[1/4] Analyzing existing org numbers for patterns...")
    prefix_success = defaultdict(int)
    for orgnr in all_known:
        prefix_success[orgnr[:5]] += 1

    # Find high-success prefixes
    top_prefixes = sorted(prefix_success.items(), key=lambda x: x[1], reverse=True)[:30]
    print("Top prefixes by success count:")
    for prefix, count in top_prefixes[:10]:
        print(f"  {prefix}xxxxx: {count} companies")

    # Strategy 2: EXPANDED Sequential expansion around known companies
    print("\n[2/4] Generating sequential scan candidates (expanded)...")
    sequential_candidates = set()
    # Use more seeds and larger range
    sample_orgnrs = list(all_known)[:200]  # More seeds
    for seed_orgnr in sample_orgnrs:
        for orgnr in generate_sequential_range(seed_orgnr, range_size=100):  # Larger range
            if orgnr not in all_known:
                sequential_candidates.add(orgnr)

    print(f"  Sequential candidates: {len(sequential_candidates)}")

    # Strategy 3: EXPANDED High-success prefix expansion
    print("\n[3/4] Generating prefix-based candidates (expanded)...")
    prefix_candidates = set()
    for prefix, _ in top_prefixes[:20]:  # More prefixes
        for orgnr in generate_prefix_range(prefix, count=500):  # More per prefix
            if orgnr not in all_known and orgnr not in sequential_candidates:
                prefix_candidates.add(orgnr)

    print(f"  Prefix candidates: {len(prefix_candidates)}")

    # Combine and shuffle
    all_candidates = list(sequential_candidates) + list(prefix_candidates)
    random.shuffle(all_candidates)
    print(f"\nTotal new candidates to test: {len(all_candidates)}")

    # Calculate how many to test based on expected hit rate (~47%)
    expected_hit_rate = 0.45
    candidates_needed = int(need_more / expected_hit_rate) + 1000  # Buffer
    candidates_to_test = all_candidates[:min(candidates_needed, len(all_candidates))]
    print(f"Testing {len(candidates_to_test)} candidates (expecting ~{int(len(candidates_to_test) * expected_hit_rate)} hits)")

    # Estimate time
    batches = len(candidates_to_test) // BATCH_SIZE
    est_minutes = (batches * BATCH_DELAY) / 60
    print(f"Estimated time: {est_minutes:.0f} minutes")

    # Strategy 4: Test candidates with checkpointing
    print("\n[4/4] Testing candidates against Bolagsverket API...")
    checkpoint_path = Path("data/smart_extract_checkpoint.json")
    found = await batch_test(
        adapter,
        candidates_to_test,
        batch_size=BATCH_SIZE,
        checkpoint_path=checkpoint_path
    )

    print(f"\n{'=' * 70}")
    print(f"RESULTS")
    print(f"{'=' * 70}")
    print(f"Candidates tested: {len(candidates_to_test)}")
    print(f"New companies found: {len(found)}")
    if candidates_to_test:
        print(f"Hit rate: {100 * len(found) / len(candidates_to_test):.1f}%")

    # Merge with existing found org numbers
    if found:
        new_orgnrs = list(already_found_orgnrs) + [f["orgnr"] for f in found]
        new_orgnrs = list(set(new_orgnrs))  # Dedupe
        with open(new_orgnrs_path, "w") as f:
            json.dump(new_orgnrs, f, indent=2)
        print(f"\nTotal org numbers ready for extraction: {len(new_orgnrs)}")
        print(f"Saved to {new_orgnrs_path}")

        # Save detailed results
        found_details_path = Path("data/smart_extract_results.json")
        with open(found_details_path, "w") as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "candidates_tested": len(candidates_to_test),
                "found_this_run": len(found),
                "total_found": len(new_orgnrs),
                "hit_rate": len(found) / len(candidates_to_test) if candidates_to_test else 0,
            }, f, indent=2)
        print(f"Saved details to {found_details_path}")

    # Summary
    final_total = len(existing_orgnrs) + len(new_orgnrs) if found else total_have
    print(f"\n{'=' * 70}")
    print(f"SUMMARY")
    print(f"{'=' * 70}")
    print(f"Existing in database: {len(existing_orgnrs)}")
    print(f"New org numbers found: {len(new_orgnrs) if found else len(already_found_orgnrs)}")
    print(f"Total available: {final_total}")
    print(f"Target: {TARGET_COMPANIES}")

    if final_total >= TARGET_COMPANIES:
        print(f"\n✓ TARGET REACHED! Ready for batch extraction.")
    else:
        print(f"\nNeed {TARGET_COMPANIES - final_total} more. Run again to continue.")

    print(f"\n{'=' * 70}")
    print("Next steps:")
    print("1. Run batch_extract.py with the new org numbers")
    print("2. Run load_and_analyze.py to rebuild graph")
    print("3. Run enrich_with_scb.py for SCB data")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    import sys
    print("=" * 60)
    print("DEPRECATED: Direct smart extraction is disabled.")
    print("")
    print("Use the pipeline orchestrator instead:")
    print("  python -m halo.pipeline.orchestrator --stage bolagsverket")
    print("  python -m halo.pipeline.orchestrator --full")
    print("  python -m halo.pipeline.orchestrator --stats")
    print("=" * 60)
    sys.exit(1)
