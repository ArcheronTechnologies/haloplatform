#!/usr/bin/env python3
"""
Batch extraction pipeline: Org numbers → Bolagsverket → Directors → JSON output.

Respects rate limits:
- Bolagsverket: 1 req/sec (conservative)
- Processes in batches with progress saving
"""

import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from halo.extraction import ExtractionPipeline, PipelineConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def batch_extract(
    orgnrs: list[str],
    output_dir: Path,
    batch_size: int = 50,
    delay_between_companies: float = 2.0,  # Conservative rate limiting
):
    """
    Extract directors from companies in batches.

    Args:
        orgnrs: List of org numbers to process
        output_dir: Directory for output files
        batch_size: Companies per batch (for progress saving)
        delay_between_companies: Seconds between API calls
    """
    config = PipelineConfig(
        bv_client_id="[REDACTED_CLIENT_ID]",
        bv_client_secret="[REDACTED_CLIENT_SECRET]",
        min_confidence=0.5,
        rate_limit_delay=delay_between_companies,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load progress if exists
    progress_file = output_dir / "progress.json"
    results_file = output_dir / "results.json"

    processed = set()
    all_results = []

    if progress_file.exists():
        with open(progress_file) as f:
            progress = json.load(f)
            processed = set(progress.get("processed", []))
            logger.info(f"Resuming from checkpoint: {len(processed)} already processed")

    if results_file.exists():
        with open(results_file) as f:
            all_results = json.load(f)

    # Filter to unprocessed
    remaining = [o for o in orgnrs if o not in processed]
    logger.info(f"Processing {len(remaining)} companies ({len(processed)} already done)")

    stats = {
        "total": len(orgnrs),
        "processed": len(processed),
        "found": 0,
        "has_docs": 0,
        "extracted": 0,
        "directors_found": 0,
        "errors": 0,
        "start_time": datetime.now().isoformat(),
    }

    async with ExtractionPipeline(config) as pipeline:
        for i, orgnr in enumerate(remaining):
            try:
                logger.info(f"[{i+1}/{len(remaining)}] Processing {orgnr}...")

                # Get company info first
                company_info = await pipeline.get_company_info(orgnr)

                if not company_info:
                    logger.debug(f"  Company not found: {orgnr}")
                    processed.add(orgnr)
                    continue

                stats["found"] += 1
                logger.info(f"  Found: {company_info.name}")

                # Check for documents
                await asyncio.sleep(delay_between_companies)
                documents = await pipeline.get_document_list(orgnr)

                if not documents:
                    logger.debug(f"  No documents for {orgnr}")
                    processed.add(orgnr)
                    continue

                stats["has_docs"] += 1
                logger.info(f"  {len(documents)} documents available")

                # Extract from most recent document
                await asyncio.sleep(delay_between_companies)
                results = await pipeline.process_company(orgnr, max_documents=1)

                for result in results:
                    if result.directors:
                        stats["extracted"] += 1
                        stats["directors_found"] += len(result.directors)

                        # Convert to serializable format
                        result_dict = {
                            "orgnr": result.orgnr,
                            "document_id": result.document_id,
                            "company_name": result.company_name,
                            "extraction_method": result.extraction_method,
                            "extraction_confidence": result.extraction_confidence,
                            "signature_date": str(result.signature_date) if result.signature_date else None,
                            "processing_time_ms": result.processing_time_ms,
                            "directors": [
                                {
                                    "first_name": d.first_name,
                                    "last_name": d.last_name,
                                    "full_name": d.full_name,
                                    "role": d.role,
                                    "role_normalized": d.role_normalized,
                                    "confidence": d.confidence,
                                    "source_field": d.source_field,
                                }
                                for d in result.directors
                            ],
                            "auditors": [
                                {
                                    "name": a.name,
                                    "firm": a.firm,
                                    "auditor_type": a.auditor_type,
                                }
                                for a in result.auditors
                            ] if result.auditors else [],
                            "warnings": result.warnings,
                        }
                        all_results.append(result_dict)

                        logger.info(f"  ✓ Extracted {len(result.directors)} directors")

                processed.add(orgnr)
                stats["processed"] = len(processed)

                # Save progress every batch_size companies
                if len(processed) % batch_size == 0:
                    _save_progress(progress_file, results_file, processed, all_results, stats)
                    logger.info(f"  Checkpoint saved ({len(processed)} processed)")

            except Exception as e:
                logger.error(f"  Error processing {orgnr}: {e}")
                stats["errors"] += 1
                processed.add(orgnr)

            # Rate limiting
            await asyncio.sleep(delay_between_companies)

    # Final save
    stats["end_time"] = datetime.now().isoformat()
    _save_progress(progress_file, results_file, processed, all_results, stats)

    # Save final stats
    stats_file = output_dir / "stats.json"
    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2)

    logger.info("\n" + "=" * 60)
    logger.info("EXTRACTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total processed: {stats['processed']}")
    logger.info(f"Companies found: {stats['found']}")
    logger.info(f"Companies with docs: {stats['has_docs']}")
    logger.info(f"Successfully extracted: {stats['extracted']}")
    logger.info(f"Total directors: {stats['directors_found']}")
    logger.info(f"Errors: {stats['errors']}")
    logger.info(f"Results saved to: {results_file}")

    return all_results


def _save_progress(progress_file, results_file, processed, results, stats):
    """Save checkpoint files."""
    with open(progress_file, "w") as f:
        json.dump({"processed": list(processed), "stats": stats}, f)

    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Batch extract directors from Swedish companies")
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=Path("data/orgnrs_demo.json"),
        help="Input file with org numbers (JSON array)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("data/extraction_results"),
        help="Output directory for results"
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Limit number of companies to process"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between API calls (seconds)"
    )
    args = parser.parse_args()

    # Load org numbers
    with open(args.input) as f:
        orgnrs = json.load(f)

    if args.limit:
        orgnrs = orgnrs[:args.limit]

    logger.info(f"Loaded {len(orgnrs)} org numbers from {args.input}")

    await batch_extract(
        orgnrs=orgnrs,
        output_dir=args.output,
        delay_between_companies=args.delay,
    )


if __name__ == "__main__":
    import sys
    print("=" * 60)
    print("DEPRECATED: Direct batch extraction is disabled.")
    print("")
    print("Use the pipeline orchestrator instead:")
    print("  python -m halo.pipeline.orchestrator --stage bolagsverket")
    print("  python -m halo.pipeline.orchestrator --full")
    print("  python -m halo.pipeline.orchestrator --stats")
    print("=" * 60)
    sys.exit(1)
