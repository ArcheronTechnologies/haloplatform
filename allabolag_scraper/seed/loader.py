"""
Seed loader for populating the company scrape queue.

Loads org numbers from:
1. Existing companies_merged.db (preferred - 1.6M active Swedish companies)
2. SCB bulk database
3. JSON files with org numbers
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


def load_from_merged_db(
    source_db: str,
    target_conn: sqlite3.Connection,
    limit: Optional[int] = None,
    company_types: Optional[List[str]] = None
) -> int:
    """
    Load org numbers from companies_merged.db into the scrape queue.

    Args:
        source_db: Path to companies_merged.db
        target_conn: Connection to scraper database
        limit: Optional limit on number of companies to load
        company_types: Optional list of company type prefixes (e.g., ['556', '559'] for AB)

    Returns:
        Number of org numbers added to queue
    """
    if not Path(source_db).exists():
        raise FileNotFoundError(f"Source database not found: {source_db}")

    source_conn = sqlite3.connect(source_db)

    # Build query
    query = "SELECT orgnr FROM companies WHERE 1=1"
    params = []

    if company_types:
        type_conditions = " OR ".join(["orgnr LIKE ?" for _ in company_types])
        query += f" AND ({type_conditions})"
        params.extend([f"{t}%" for t in company_types])

    if limit:
        query += " LIMIT ?"
        params.append(limit)

    cursor = source_conn.execute(query, params)

    now = datetime.utcnow().isoformat()
    count = 0
    batch = []
    batch_size = 1000

    for row in cursor:
        org_nr = row[0]
        if org_nr:
            # Normalize: remove dashes
            org_nr = org_nr.replace('-', '').replace(' ', '')
            batch.append((org_nr, now))

            if len(batch) >= batch_size:
                target_conn.executemany(
                    "INSERT OR IGNORE INTO company_scrape_queue (org_nr, created_at) VALUES (?, ?)",
                    batch
                )
                target_conn.commit()
                count += len(batch)
                batch = []
                logger.info(f"Loaded {count} org numbers...")

    # Final batch
    if batch:
        target_conn.executemany(
            "INSERT OR IGNORE INTO company_scrape_queue (org_nr, created_at) VALUES (?, ?)",
            batch
        )
        target_conn.commit()
        count += len(batch)

    source_conn.close()
    logger.info(f"Total: {count} org numbers loaded from merged database")
    return count


def load_from_json(
    json_path: str,
    target_conn: sqlite3.Connection,
    org_nr_field: str = "orgnr"
) -> int:
    """
    Load org numbers from a JSON file.

    Args:
        json_path: Path to JSON file (array of objects or array of strings)
        target_conn: Connection to scraper database
        org_nr_field: Field name containing org number (if objects)

    Returns:
        Number of org numbers added
    """
    with open(json_path) as f:
        data = json.load(f)

    now = datetime.utcnow().isoformat()
    count = 0

    for item in data:
        if isinstance(item, str):
            org_nr = item
        elif isinstance(item, dict):
            org_nr = item.get(org_nr_field)
        else:
            continue

        if org_nr:
            org_nr = str(org_nr).replace('-', '').replace(' ', '')
            target_conn.execute(
                "INSERT OR IGNORE INTO company_scrape_queue (org_nr, created_at) VALUES (?, ?)",
                (org_nr, now)
            )
            count += 1

    target_conn.commit()
    logger.info(f"Loaded {count} org numbers from JSON")
    return count


def load_from_list(
    org_numbers: List[str],
    target_conn: sqlite3.Connection
) -> int:
    """
    Load a list of org numbers directly.

    Args:
        org_numbers: List of org numbers
        target_conn: Connection to scraper database

    Returns:
        Number added
    """
    now = datetime.utcnow().isoformat()

    normalized = [
        (org_nr.replace('-', '').replace(' ', ''), now)
        for org_nr in org_numbers
        if org_nr
    ]

    target_conn.executemany(
        "INSERT OR IGNORE INTO company_scrape_queue (org_nr, created_at) VALUES (?, ?)",
        normalized
    )
    target_conn.commit()

    logger.info(f"Loaded {len(normalized)} org numbers from list")
    return len(normalized)


def get_queue_stats(conn: sqlite3.Connection) -> dict:
    """Get statistics about the current queue."""
    cursor = conn.execute("""
        SELECT
            status,
            COUNT(*) as count
        FROM company_scrape_queue
        GROUP BY status
    """)

    stats = {row[0]: row[1] for row in cursor.fetchall()}

    cursor = conn.execute("SELECT COUNT(*) FROM person_scrape_queue")
    stats['persons_queued'] = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM companies")
    stats['companies_scraped'] = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM persons")
    stats['persons_total'] = cursor.fetchone()[0]

    return stats
