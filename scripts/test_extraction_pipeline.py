#!/usr/bin/env python3
"""
Test the director extraction pipeline on real data.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from halo.extraction import ExtractionPipeline, PipelineConfig

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    # Credentials from the roadmap
    config = PipelineConfig(
        bv_client_id="AnQ27kXW8z4sdOMJHJuFJGf5AFIa",
        bv_client_secret="L4bi0Wh_pDiMZ7GrKb9PYd1274oa",
        min_confidence=0.5,
    )

    # Test companies - we know 5592584386 (Avado AB) has documents
    test_companies = [
        "5592584386",  # Avado AB - has documents
        "5560360793",  # SAAB - large company, may not have docs in HVD
    ]

    async with ExtractionPipeline(config) as pipeline:
        for orgnr in test_companies:
            print(f"\n{'='*60}")
            print(f"Processing: {orgnr}")
            print("=" * 60)

            # Get company info
            company_info = await pipeline.get_company_info(orgnr)
            if company_info:
                print(f"Company: {company_info.name}")
                print(f"Legal form: {company_info.legal_form}")
                print(f"Status: {company_info.status}")
                print(f"Location: {company_info.postal_code} {company_info.postal_city}")
                print(f"SNI codes: {company_info.sni_codes}")
            else:
                print("Company not found")
                continue

            # Get document list
            documents = await pipeline.get_document_list(orgnr)
            print(f"\nDocuments available: {len(documents)}")

            if documents:
                for doc in documents[:3]:
                    print(f"  - {doc.document_id}")
                    print(f"    Period: {doc.reporting_period_end}")
                    print(f"    Format: {doc.file_format}")

                # Process the company
                print("\nExtracting directors...")
                results = await pipeline.process_company(orgnr, max_documents=1)

                for result in results:
                    print(f"\nDocument: {result.document_id}")
                    print(f"Method: {result.extraction_method}")
                    print(f"Confidence: {result.extraction_confidence:.2f}")
                    print(f"Signature date: {result.signature_date}")
                    print(f"Processing time: {result.processing_time_ms}ms")

                    if result.warnings:
                        print(f"Warnings: {result.warnings}")

                    print(f"\nDirectors ({len(result.directors)}):")
                    for d in sorted(result.directors, key=lambda x: -x.confidence):
                        print(f"  {d.full_name:30} {d.role_normalized:25} ({d.confidence:.2f})")
                        print(f"    Role: {d.role}")
                        print(f"    Source: {d.source_field}")

                    if result.auditors:
                        print(f"\nAuditors ({len(result.auditors)}):")
                        for a in result.auditors:
                            firm = f" - {a.firm}" if a.firm else ""
                            print(f"  {a.name}{firm} ({a.auditor_type})")

    print("\n" + "=" * 60)
    print("EXTRACTION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
