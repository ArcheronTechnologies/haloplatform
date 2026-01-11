#!/usr/bin/env python3
"""
Allabolag Scraper - Main CLI Entry Point

Two-phase scraper for allabolag.se:
- Phase 1: Company pages -> companies, persons (partial), roles
- Phase 2: Person pages -> full DOB, connections, network discovery

Usage:
    python -m allabolag_scraper seed --source /path/to/companies_merged.db --limit 1000
    python -m allabolag_scraper run --phase companies
    python -m allabolag_scraper run --phase persons
    python -m allabolag_scraper run --phase all
    python -m allabolag_scraper status
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from allabolag_scraper.config import ScraperConfig
from allabolag_scraper.db.connection import init_db
from allabolag_scraper.scraper.orchestrator import Orchestrator
from allabolag_scraper.seed.loader import (
    load_from_merged_db,
    load_from_json,
    load_from_list,
    get_queue_stats
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def cmd_seed(args, config: ScraperConfig):
    """Seed the company scrape queue."""
    conn = init_db(config)

    if args.source:
        source_path = Path(args.source)
        if source_path.suffix == '.db':
            # SQLite database
            company_types = args.types.split(',') if args.types else None
            count = load_from_merged_db(
                str(source_path),
                conn,
                limit=args.limit,
                company_types=company_types
            )
        elif source_path.suffix == '.json':
            count = load_from_json(str(source_path), conn)
        else:
            logger.error(f"Unsupported source format: {source_path.suffix}")
            return 1

        logger.info(f"Seeded {count} companies to queue")

    elif args.orgnr:
        # Single or comma-separated org numbers
        org_numbers = [o.strip() for o in args.orgnr.split(',')]
        count = load_from_list(org_numbers, conn)
        logger.info(f"Added {count} org numbers to queue")

    # Show stats
    stats = get_queue_stats(conn)
    logger.info(f"Queue status: {stats}")

    conn.close()
    return 0


def cmd_run(args, config: ScraperConfig):
    """Run the scraper."""
    # Apply config overrides
    if args.delay:
        config.min_delay = args.delay
        config.max_delay = args.delay + 2.0

    if args.batch_size:
        config.batch_size = args.batch_size

    orchestrator = Orchestrator(config)

    try:
        asyncio.run(orchestrator.run(phase=args.phase))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        orchestrator.close()

    return 0


def cmd_status(args, config: ScraperConfig):
    """Show scraper status."""
    conn = init_db(config)
    stats = get_queue_stats(conn)

    print("\n=== Allabolag Scraper Status ===\n")

    # Company queue
    pending = stats.get('pending', 0)
    completed = stats.get('completed', 0)
    in_progress = stats.get('in_progress', 0)
    total_companies = pending + completed + in_progress

    print(f"Company Queue:")
    print(f"  Pending:     {pending:,}")
    print(f"  In Progress: {in_progress:,}")
    print(f"  Completed:   {completed:,}")
    print(f"  Total:       {total_companies:,}")

    # Person queue
    print(f"\nPerson Queue:")
    print(f"  Queued:      {stats.get('persons_queued', 0):,}")

    # Scraped data
    print(f"\nScraped Data:")
    print(f"  Companies:   {stats.get('companies_scraped', 0):,}")
    print(f"  Persons:     {stats.get('persons_total', 0):,}")

    # Progress
    if total_companies > 0:
        progress = (completed / total_companies) * 100
        print(f"\nProgress: {progress:.1f}%")

    conn.close()
    return 0


def cmd_export(args, config: ScraperConfig):
    """Export scraped data."""
    import json
    import sqlite3

    conn = init_db(config)

    output_path = Path(args.output)

    if args.format == 'json':
        # Export companies with persons
        cursor = conn.execute("""
            SELECT c.org_nr, c.name, c.legal_name, c.status, c.company_type,
                   c.municipality, c.county, c.revenue, c.employees
            FROM companies c
            ORDER BY c.org_nr
        """)

        companies = []
        for row in cursor:
            company = {
                'org_nr': row[0],
                'name': row[1],
                'legal_name': row[2],
                'status': row[3],
                'company_type': row[4],
                'municipality': row[5],
                'county': row[6],
                'revenue': row[7],
                'employees': row[8],
            }

            # Get persons for this company
            persons_cursor = conn.execute("""
                SELECT p.name, p.birth_date, p.gender, r.role_type, r.role_group
                FROM persons p
                JOIN roles r ON r.person_id = p.id
                WHERE r.company_org_nr = ?
            """, (row[0],))

            company['persons'] = [
                {
                    'name': p[0],
                    'birth_date': p[1],
                    'gender': p[2],
                    'role': p[3],
                    'role_group': p[4]
                }
                for p in persons_cursor
            ]

            companies.append(company)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(companies, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported {len(companies)} companies to {output_path}")

    elif args.format == 'csv':
        import csv

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'org_nr', 'company_name', 'person_name', 'birth_date',
                'gender', 'role', 'role_group'
            ])

            cursor = conn.execute("""
                SELECT c.org_nr, c.name, p.name, p.birth_date, p.gender,
                       r.role_type, r.role_group
                FROM companies c
                JOIN roles r ON r.company_org_nr = c.org_nr
                JOIN persons p ON p.id = r.person_id
                ORDER BY c.org_nr, p.name
            """)

            count = 0
            for row in cursor:
                writer.writerow(row)
                count += 1

        logger.info(f"Exported {count} company-person records to {output_path}")

    conn.close()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Allabolag.se Scraper - Extract company and person data'
    )

    parser.add_argument(
        '--db',
        type=str,
        help='Database path (default: data/allabolag.db)'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Seed command
    seed_parser = subparsers.add_parser('seed', help='Seed the scrape queue')
    seed_parser.add_argument(
        '--source',
        type=str,
        help='Source database (.db) or JSON file'
    )
    seed_parser.add_argument(
        '--orgnr',
        type=str,
        help='Single or comma-separated org numbers'
    )
    seed_parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of companies to seed'
    )
    seed_parser.add_argument(
        '--types',
        type=str,
        help='Company type prefixes (e.g., "556,559" for AB only)'
    )

    # Run command
    run_parser = subparsers.add_parser('run', help='Run the scraper')
    run_parser.add_argument(
        '--phase',
        type=str,
        choices=['companies', 'persons', 'interleaved', 'all'],
        default='interleaved',
        help='Which phase to run (interleaved runs both concurrently)'
    )
    run_parser.add_argument(
        '--delay',
        type=float,
        help='Minimum delay between requests (seconds)'
    )
    run_parser.add_argument(
        '--batch-size',
        type=int,
        help='Batch size'
    )

    # Status command
    subparsers.add_parser('status', help='Show scraper status')

    # Export command
    export_parser = subparsers.add_parser('export', help='Export scraped data')
    export_parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output file path'
    )
    export_parser.add_argument(
        '--format',
        type=str,
        choices=['json', 'csv'],
        default='json',
        help='Export format'
    )

    args = parser.parse_args()

    # Build config
    config = ScraperConfig()
    if args.db:
        config.database_path = Path(args.db)

    # Route commands
    if args.command == 'seed':
        return cmd_seed(args, config)
    elif args.command == 'run':
        return cmd_run(args, config)
    elif args.command == 'status':
        return cmd_status(args, config)
    elif args.command == 'export':
        return cmd_export(args, config)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
