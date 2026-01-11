#!/usr/bin/env python3
"""
SCB Full Registry Pull - ALL ENTITY TYPES (SQLite version)

Pulls ALL active Swedish business entities from SCB Foretagsregistret.
Writes directly to SQLite to avoid memory issues.

Total: ~1.35 million entities
"""

import asyncio
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

REQUEST_DELAY = 1.5  # seconds between requests


def generate_prefixes():
    """
    Generate org number prefixes for COMPLETE coverage of all Swedish entities.

    Based on actual API counts (RaknaForetag endpoint):
    - Total entities: 1,352,781
    - API limit: 2000 per query

    Strategy:
    - 4-digit prefixes for most ranges (under 2000 entities each)
    - 5-digit for 3024x, 5020x, 8020x, 8025x
    - 6-digit for 556xxx, 559xxx (5-digit still exceeds 2000)
    """
    prefixes = []

    # Ranges needing 6-digit prefixes (5-digit exceeds 2000)
    dense_6digit_bases = set()
    for i in range(5560, 5570):  # 556x - Aktiebolag
        dense_6digit_bases.add(str(i))
    for i in range(5590, 5600):  # 559x - Aktiebolag
        dense_6digit_bases.add(str(i))
    # 5020 also needs 6-digit (50207, 50208, 50209 hit limit with 5-digit)
    dense_6digit_bases.add('5020')

    # Ranges needing 5-digit prefixes (4-digit exceeds 2000)
    # Discovered from last run's over-limit warnings
    dense_5digit_bases = {
        '3024',  # 7,335 entities
        '7164',  # Bostadsrättsföreningar
        '7179',  # Bostadsrättsföreningar
        '7696',  # Samfälligheter
        '8020',  # 2,489 entities
        '8024',  # Over 2000
        '8025',  # 2,151 entities
        '9165',  # Stiftelser
        '9340',  # Various
        '9696',  # Utländska filialer
        '9697',  # Utländska filialer
        '9698',  # Utländska filialer
    }

    # Generate 4-digit prefixes (0000-9999) except where we need finer granularity
    skip_4digit = dense_6digit_bases | dense_5digit_bases
    for i in range(10000):
        prefix = str(i).zfill(4)
        if prefix not in skip_4digit:
            prefixes.append(prefix)

    # Generate 5-digit prefixes for moderately dense ranges
    for base in dense_5digit_bases:
        for digit in range(10):
            prefixes.append(base + str(digit))

    # Generate 6-digit prefixes for very dense ranges
    for base in dense_6digit_bases:
        for d1 in range(10):
            for d2 in range(10):
                prefixes.append(base + str(d1) + str(d2))

    return prefixes


def init_database(db_path):
    """Initialize SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            orgnr TEXT PRIMARY KEY,
            name TEXT,
            legal_form TEXT,
            sni_code TEXT,
            municipality TEXT,
            status TEXT,
            f_skatt TEXT,
            moms TEXT,
            employer TEXT,
            post_address TEXT,
            post_nr TEXT,
            post_ort TEXT,
            raw_json TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pull_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    return conn


def get_completed_prefixes(conn):
    """Get set of completed prefixes from database."""
    cursor = conn.execute("SELECT value FROM pull_state WHERE key = 'completed_prefixes'")
    row = cursor.fetchone()
    if row:
        return set(json.loads(row[0]))
    return set()


def save_completed_prefixes(conn, prefixes):
    """Save completed prefixes to database."""
    conn.execute(
        "INSERT OR REPLACE INTO pull_state (key, value) VALUES (?, ?)",
        ('completed_prefixes', json.dumps(list(prefixes)))
    )
    conn.commit()


async def pull_all_entities():
    """Pull all active entities from SCB directly to SQLite."""

    data_dir = Path(__file__).parent.parent / "data"
    cert_path = data_dir / "scb_cert.pfx"
    db_path = data_dir / "scb_registry.db"

    if not cert_path.exists():
        logger.error(f"Certificate not found: {cert_path}")
        return

    from halo.ingestion.scb_foretag import SCBForetagAdapter
    adapter = SCBForetagAdapter(cert_path=cert_path, cert_password="[REDACTED_PASSWORD]")
    client = await adapter._get_client()

    # Initialize database
    conn = init_database(db_path)

    try:
        all_prefixes = generate_prefixes()
        logger.info(f"Total prefixes to query: {len(all_prefixes)}")

        # Load checkpoint from database
        completed_prefixes = get_completed_prefixes(conn)

        # Count existing records
        cursor = conn.execute("SELECT COUNT(*) FROM companies")
        existing_count = cursor.fetchone()[0]

        if completed_prefixes:
            logger.info(f"Resuming: {existing_count:,} entities, {len(completed_prefixes)} prefixes done")

        remaining_prefixes = [p for p in all_prefixes if p not in completed_prefixes]
        logger.info(f"Remaining prefixes: {len(remaining_prefixes)}")
        logger.info(f"Estimated time: {len(remaining_prefixes) * REQUEST_DELAY / 60:.1f} minutes")
        logger.info("=" * 60)

        last_request_time = 0
        request_count = 0
        over_limit_prefixes = []
        batch = []
        BATCH_SIZE = 500

        for prefix in remaining_prefixes:
            elapsed = time.time() - last_request_time
            if elapsed < REQUEST_DELAY:
                await asyncio.sleep(REQUEST_DELAY - elapsed)

            try:
                last_request_time = time.time()

                params = {
                    'Företagsstatus': '1',
                    'Registreringsstatus': '1',
                    'Variabler': [{
                        'Variabel': 'OrgNr (10 siffror)',
                        'Operator': 'BorjarPa',
                        'Varde1': prefix,
                        'Varde2': ''
                    }]
                }

                response = await client.post(
                    '[REDACTED_API_ENDPOINT]
                    json=params,
                    headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
                )
                response.raise_for_status()

                data = response.json()
                request_count += 1

                if isinstance(data, list) and len(data) >= 2000:
                    over_limit_prefixes.append(prefix)
                    logger.warning(f"Prefix {prefix} hit 2000 limit!")

                if isinstance(data, list):
                    for entity in data:
                        orgnr = entity.get("OrgNr", "")
                        if len(orgnr) == 12 and orgnr.startswith("16"):
                            orgnr = orgnr[2:]

                        batch.append((
                            orgnr,
                            entity.get("Företagsnamn", ""),
                            entity.get("JuridiskForm", ""),
                            entity.get("Bransch", ""),
                            entity.get("SätesKommun", ""),
                            entity.get("Företagsstatus", ""),
                            entity.get("FSkattsedel", ""),
                            entity.get("Momsregistrering", ""),
                            entity.get("Arbetsgivare", ""),
                            entity.get("PostAdress", ""),
                            entity.get("PostNr", ""),
                            entity.get("PostOrt", ""),
                            json.dumps(entity, ensure_ascii=False),
                        ))

                completed_prefixes.add(prefix)

                # Batch insert to reduce disk writes
                if len(batch) >= BATCH_SIZE:
                    conn.executemany(
                        "INSERT OR IGNORE INTO companies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        batch
                    )
                    conn.commit()
                    batch = []

                if request_count % 100 == 0:
                    # Save progress
                    if batch:
                        conn.executemany(
                            "INSERT OR IGNORE INTO companies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            batch
                        )
                        batch = []
                    save_completed_prefixes(conn, completed_prefixes)

                    cursor = conn.execute("SELECT COUNT(*) FROM companies")
                    total_count = cursor.fetchone()[0]
                    progress = len(completed_prefixes) / len(all_prefixes) * 100
                    logger.info(f"Progress: {len(completed_prefixes)}/{len(all_prefixes)} ({progress:.1f}%) - {total_count:,} entities")

            except Exception as e:
                logger.error(f"Error on prefix {prefix}: {e}")
                # Save progress before continuing
                if batch:
                    conn.executemany(
                        "INSERT OR IGNORE INTO companies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        batch
                    )
                    batch = []
                save_completed_prefixes(conn, completed_prefixes)
                await asyncio.sleep(5)

        # Final batch
        if batch:
            conn.executemany(
                "INSERT OR IGNORE INTO companies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                batch
            )
        save_completed_prefixes(conn, completed_prefixes)
        conn.commit()

        # Final count
        cursor = conn.execute("SELECT COUNT(*) FROM companies")
        total_count = cursor.fetchone()[0]

        logger.info("=" * 60)
        if over_limit_prefixes:
            logger.warning(f"{len(over_limit_prefixes)} prefixes hit limit: {over_limit_prefixes}")

        # Create index
        logger.info("Creating index...")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_form ON companies(legal_form)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON companies(status)")
        conn.commit()

        logger.info(f"COMPLETE: {total_count:,} entities in {db_path}")

    finally:
        await adapter.close()
        conn.close()


if __name__ == "__main__":
    asyncio.run(pull_all_entities())
