#!/usr/bin/env python3
"""
Test HVD API coverage and XBRL schema consistency.
With proper rate limiting to avoid 429 errors.
"""

import asyncio
import logging
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from halo.extraction import ExtractionPipeline, PipelineConfig

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def test_coverage():
    config = PipelineConfig(
        bv_client_id="AnQ27kXW8z4sdOMJHJuFJGf5AFIa",
        bv_client_secret="L4bi0Wh_pDiMZ7GrKb9PYd1274oa",
        min_confidence=0.5,
        rate_limit_delay=1.0,  # 1 second between requests
    )

    # Use a curated list of known valid org numbers
    # Mix of company sizes and types
    test_orgnrs = [
        # Known to have docs
        "5592584386",  # Avado AB
        # Large public companies
        "5560360793",  # SAAB
        "5565475489",  # Mölnlycke Health Care
        "5560006538",  # Volvo AB (corrected)
        # Medium companies (random valid ones from earlier tests)
        "5564649860",  # (was Spotify lookup - actually different company)
        # Small/newer companies - these might have iXBRL
        "5590000001",  # Random newer range
        "5591000001",
        "5592000001",
        "5593000001",
        "5594000001",
        "5595000001",
        "5596000001",
        "5597000001",
        "5598000001",
        "5599000001",
    ]

    # Generate some valid org numbers in newer ranges (more likely to have iXBRL)
    # Companies registered after ~2019 should have iXBRL
    newer_orgnrs = []
    for prefix in ["5590", "5591", "5592", "5593", "5594", "5595"]:
        for i in range(5):
            # Generate with valid Luhn checksum
            base = prefix + f"{i:05d}"
            digits = [int(d) for d in base]
            total = 0
            for j, d in enumerate(digits):
                if j % 2 == 0:
                    d *= 2
                    if d > 9:
                        d -= 9
                total += d
            check = (10 - (total % 10)) % 10
            newer_orgnrs.append(base + str(check))

    all_orgnrs = test_orgnrs + newer_orgnrs[:20]
    # Remove duplicates
    all_orgnrs = list(dict.fromkeys(all_orgnrs))

    async with ExtractionPipeline(config) as pipeline:
        stats = {
            "total_tested": 0,
            "company_exists": 0,
            "company_not_found": 0,
            "has_documents": 0,
            "no_documents": 0,
            "document_counts": defaultdict(int),
            "years_history": [],
            "xbrl_fields_found": defaultdict(int),
            "companies_with_docs": [],
        }

        print(f"Testing {len(all_orgnrs)} org numbers with 1s delay...")
        print("-" * 60)

        for i, orgnr in enumerate(all_orgnrs):
            print(f"[{i+1}/{len(all_orgnrs)}] Testing {orgnr}...", end=" ", flush=True)

            stats["total_tested"] += 1

            # Rate limit before each request
            await asyncio.sleep(1.0)

            # Check if company exists
            company_info = await pipeline.get_company_info(orgnr)
            if not company_info:
                stats["company_not_found"] += 1
                print("Not found")
                continue

            stats["company_exists"] += 1
            print(f"{company_info.name[:30] if company_info.name else 'Unknown'}...", end=" ", flush=True)

            # Rate limit
            await asyncio.sleep(1.0)

            # Get document list
            documents = await pipeline.get_document_list(orgnr)

            if documents:
                stats["has_documents"] += 1
                stats["document_counts"][len(documents)] += 1
                stats["companies_with_docs"].append((orgnr, company_info.name, len(documents)))

                # Calculate years of history
                if len(documents) >= 2:
                    try:
                        years = [
                            int(d.reporting_period_end[:4])
                            for d in documents
                            if d.reporting_period_end
                        ]
                        if years:
                            history_years = max(years) - min(years) + 1
                            stats["years_history"].append(history_years)
                    except (ValueError, TypeError):
                        pass

                print(f"✓ {len(documents)} docs")

                # Extract from one document to check XBRL fields
                if len(stats["xbrl_fields_found"]) < 20:  # Only extract from first few
                    await asyncio.sleep(1.0)
                    try:
                        results = await pipeline.process_company(orgnr, max_documents=1)
                        for result in results:
                            for d in result.directors:
                                stats["xbrl_fields_found"][d.source_field] += 1
                    except Exception as e:
                        print(f"  Extraction error: {e}")

            else:
                stats["no_documents"] += 1
                print("No docs")

        # Print results
        print("\n" + "=" * 60)
        print("COVERAGE ANALYSIS")
        print("=" * 60)

        print(f"\nTotal tested: {stats['total_tested']}")
        print(f"Companies found in registry: {stats['company_exists']}")
        print(f"Companies not found (invalid orgnr): {stats['company_not_found']}")

        if stats["company_exists"] > 0:
            coverage = stats["has_documents"] / stats["company_exists"] * 100
            print(f"\n--- Document Coverage ---")
            print(f"Companies with documents: {stats['has_documents']}")
            print(f"Companies without documents: {stats['no_documents']}")
            print(f"Coverage rate: {coverage:.1f}%")

        print(f"\n--- Document Counts ---")
        for count, num_companies in sorted(stats["document_counts"].items()):
            print(f"  {count} documents: {num_companies} companies")

        if stats["years_history"]:
            avg_history = sum(stats["years_history"]) / len(stats["years_history"])
            print(f"\n--- Years of History ---")
            print(f"  Average: {avg_history:.1f} years")
            print(f"  Min: {min(stats['years_history'])} years")
            print(f"  Max: {max(stats['years_history'])} years")

        print(f"\n--- Companies with Documents ---")
        for orgnr, name, doc_count in stats["companies_with_docs"]:
            print(f"  {orgnr}: {name} ({doc_count} docs)")

        print(f"\n--- XBRL Fields Used ---")
        for field, count in sorted(stats["xbrl_fields_found"].items(), key=lambda x: -x[1]):
            print(f"  {field}: {count}")

        return stats


if __name__ == "__main__":
    asyncio.run(test_coverage())
