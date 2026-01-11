"""
Load orgnrs from SCB/Bolagsverket API results into the allabolag scraper queue.

This connects the data pipeline:
  SCB Företagsregistret -> orgnrs -> allabolag scraper -> enriched company data

Only loads "real" companies - those that returned valid data from API lookups.
"""
import json
import asyncio
import logging
from pathlib import Path
from typing import List, Set

from .config import ScraperConfig
from .database import ScraperDatabase

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default data directory
DATA_DIR = Path(__file__).parent.parent / "data"


def load_orgnrs_from_json(filepath: Path) -> List[str]:
    """Load orgnrs from a JSON array file."""
    with open(filepath, 'r') as f:
        data = json.load(f)

    # Handle both list of strings and list of dicts
    orgnrs = []
    for item in data:
        if isinstance(item, str):
            orgnrs.append(item.replace('-', ''))
        elif isinstance(item, dict) and 'orgnr' in item:
            orgnrs.append(item['orgnr'].replace('-', ''))

    return orgnrs


def load_orgnrs_from_txt(filepath: Path) -> List[str]:
    """Load orgnrs from a text file (one per line)."""
    orgnrs = []
    with open(filepath, 'r') as f:
        for line in f:
            orgnr = line.strip().replace('-', '')
            if orgnr and len(orgnr) == 10 and orgnr.isdigit():
                orgnrs.append(orgnr)
    return orgnrs


def get_already_scraped(db: ScraperDatabase) -> Set[str]:
    """Get orgnrs that have already been successfully scraped."""
    conn = db._get_connection()
    try:
        rows = conn.execute(
            "SELECT orgnr FROM companies"
        ).fetchall()
        return {row['orgnr'] for row in rows}
    finally:
        conn.close()


def get_pending_or_failed(db: ScraperDatabase) -> Set[str]:
    """Get orgnrs already in the job queue."""
    conn = db._get_connection()
    try:
        rows = conn.execute(
            "SELECT orgnr FROM jobs"
        ).fetchall()
        return {row['orgnr'] for row in rows}
    finally:
        conn.close()


def load_all_scb_orgnrs() -> List[str]:
    """
    Load all orgnrs from SCB/Bolagsverket API result files.

    These are companies that successfully returned data from the APIs,
    not random orgnr probes that returned nothing.
    """
    all_orgnrs = set()

    # Priority order: most reliable sources first
    sources = [
        # SCB established - verified companies from SCB API
        ("orgnrs_scb_established.json", "SCB established"),
        # Combined - aggregated from multiple sources
        ("orgnrs_combined.json", "Combined"),
        # New batch - recent API pulls
        ("orgnrs_new_batch.json", "New batch"),
        # Demo set
        ("orgnrs_demo.json", "Demo"),
    ]

    for filename, source_name in sources:
        filepath = DATA_DIR / filename
        if filepath.exists():
            try:
                orgnrs = load_orgnrs_from_json(filepath)
                before = len(all_orgnrs)
                all_orgnrs.update(orgnrs)
                added = len(all_orgnrs) - before
                logger.info(f"Loaded {len(orgnrs)} orgnrs from {source_name} ({added} new)")
            except Exception as e:
                logger.warning(f"Failed to load {filename}: {e}")

    # Also check for txt files
    txt_files = list(DATA_DIR.glob("orgnrs*.txt"))
    for filepath in txt_files:
        try:
            orgnrs = load_orgnrs_from_txt(filepath)
            before = len(all_orgnrs)
            all_orgnrs.update(orgnrs)
            added = len(all_orgnrs) - before
            logger.info(f"Loaded {len(orgnrs)} orgnrs from {filepath.name} ({added} new)")
        except Exception as e:
            logger.warning(f"Failed to load {filepath.name}: {e}")

    return sorted(all_orgnrs)


def main():
    """Load SCB orgnrs into the allabolag scraper queue."""
    import argparse

    parser = argparse.ArgumentParser(description='Load SCB orgnrs into allabolag scraper')
    parser.add_argument('--source', choices=['scb', 'combined', 'all', 'file'],
                        default='all', help='Source of orgnrs to load')
    parser.add_argument('--file', help='Specific file to load (for --source file)')
    parser.add_argument('--priority', type=int, default=0, help='Job priority')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                        help='Skip orgnrs already scraped or in queue')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be loaded')

    args = parser.parse_args()

    # Load orgnrs based on source
    if args.source == 'file':
        if not args.file:
            print("--file required when using --source file")
            return
        filepath = Path(args.file)
        if filepath.suffix == '.json':
            orgnrs = load_orgnrs_from_json(filepath)
        else:
            orgnrs = load_orgnrs_from_txt(filepath)
        logger.info(f"Loaded {len(orgnrs)} orgnrs from {filepath}")

    elif args.source == 'scb':
        filepath = DATA_DIR / "orgnrs_scb_established.json"
        orgnrs = load_orgnrs_from_json(filepath)
        logger.info(f"Loaded {len(orgnrs)} orgnrs from SCB established")

    elif args.source == 'combined':
        filepath = DATA_DIR / "orgnrs_combined.json"
        orgnrs = load_orgnrs_from_json(filepath)
        logger.info(f"Loaded {len(orgnrs)} orgnrs from combined")

    else:  # all
        orgnrs = load_all_scb_orgnrs()
        logger.info(f"Loaded {len(orgnrs)} total unique orgnrs from all sources")

    # Initialize database
    config = ScraperConfig()
    db = ScraperDatabase(config.storage)

    # Filter out already scraped/queued if requested
    if args.skip_existing:
        already_scraped = get_already_scraped(db)
        in_queue = get_pending_or_failed(db)

        original_count = len(orgnrs)
        orgnrs = [o for o in orgnrs if o not in already_scraped and o not in in_queue]

        logger.info(f"Filtered: {original_count} -> {len(orgnrs)} "
                   f"(skipped {len(already_scraped)} scraped, "
                   f"{len(in_queue)} in queue)")

    if args.dry_run:
        print(f"\nDry run - would load {len(orgnrs)} orgnrs with priority {args.priority}")
        print(f"First 10: {orgnrs[:10]}")
        return

    # Add to queue
    if orgnrs:
        db.add_jobs(orgnrs, priority=args.priority)
        logger.info(f"Added {len(orgnrs)} orgnrs to scrape queue (priority={args.priority})")
    else:
        logger.info("No new orgnrs to add")

    # Show stats
    stats = db.get_job_stats()
    print(f"\nJob queue stats: {stats}")

    total = sum(stats.values())
    if total > 0:
        pending = stats.get('pending', 0)
        print(f"\nEstimated time at 150/day: {pending / 150:.1f} days ({pending / 150 / 30:.1f} months)")


if __name__ == '__main__':
    main()
