#!/usr/bin/env python3
"""
Merge SCB and Bolagsverket bulk data into a unified company database.

Combines:
- SCB: Company name, legal form, SNI codes, addresses, status
- Bolagsverket: Business description (verksamhetsbeskrivning)
"""

import logging
import sqlite3
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


def merge_databases():
    """Merge SCB and Bolagsverket bulk data into unified database."""

    scb_db = DATA_DIR / "scb_bulk.db"
    bv_db = DATA_DIR / "bolagsverket_bulk.db"
    merged_db = DATA_DIR / "companies_merged.db"

    logger.info(f"Merging {scb_db} and {bv_db}")

    # Create merged database
    conn = sqlite3.connect(merged_db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Create merged table schema
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            orgnr TEXT PRIMARY KEY,
            name TEXT,
            company_name TEXT,
            legal_form_code TEXT,
            legal_form TEXT,
            sni_code1 TEXT,
            sni_code2 TEXT,
            sni_code3 TEXT,
            sni_code4 TEXT,
            sni_code5 TEXT,
            street_address TEXT,
            co_address TEXT,
            postal_code TEXT,
            city TEXT,
            company_status TEXT,
            registration_date TEXT,
            business_description TEXT,
            source TEXT
        )
    """)
    conn.commit()

    # Attach source databases
    conn.execute(f"ATTACH '{scb_db}' AS scb")
    conn.execute(f"ATTACH '{bv_db}' AS bv")

    # Insert merged data - LEFT JOIN to get all SCB companies + Bolagsverket descriptions
    logger.info("Merging active companies from both sources...")
    conn.execute("""
        INSERT OR REPLACE INTO companies
        SELECT
            s.orgnr,
            s.name,
            s.company_name,
            s.legal_form_code,
            s.legal_form,
            s.sni_code1,
            s.sni_code2,
            s.sni_code3,
            s.sni_code4,
            s.sni_code5,
            s.street_address,
            s.co_address,
            s.postal_code,
            s.city,
            s.company_status,
            COALESCE(b.registration_date, s.registration_date) as registration_date,
            b.business_description,
            CASE
                WHEN b.orgnr IS NOT NULL THEN 'scb+bv'
                ELSE 'scb'
            END as source
        FROM scb.scb_companies s
        LEFT JOIN bv.bolagsverket_companies b ON s.orgnr = b.orgnr
        WHERE s.company_status = '1'
    """)
    conn.commit()

    # Also add Bolagsverket-only companies (registered with BV but not in SCB)
    logger.info("Adding Bolagsverket-only companies...")
    conn.execute("""
        INSERT OR IGNORE INTO companies
        SELECT
            b.orgnr,
            b.name,
            b.name as company_name,
            b.legal_form as legal_form_code,
            b.legal_form,
            NULL as sni_code1,
            NULL as sni_code2,
            NULL as sni_code3,
            NULL as sni_code4,
            NULL as sni_code5,
            b.postal_address as street_address,
            NULL as co_address,
            b.postal_code,
            b.city,
            '1' as company_status,
            b.registration_date,
            b.business_description,
            'bv' as source
        FROM bv.bolagsverket_companies b
        WHERE (b.deregistration_date IS NULL OR b.deregistration_date = '')
          AND NOT EXISTS (
            SELECT 1 FROM scb.scb_companies s
            WHERE s.orgnr = b.orgnr AND s.company_status = '1'
          )
    """)
    conn.commit()

    # Create indexes
    logger.info("Creating indexes...")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_form ON companies(legal_form_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sni ON companies(sni_code1)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_city ON companies(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON companies(source)")
    conn.commit()

    # Get stats
    cursor = conn.execute("SELECT COUNT(*) FROM companies")
    total = cursor.fetchone()[0]

    cursor = conn.execute("SELECT source, COUNT(*) FROM companies GROUP BY source")
    sources = cursor.fetchall()

    cursor = conn.execute("SELECT COUNT(*) FROM companies WHERE business_description IS NOT NULL AND business_description != ''")
    with_desc = cursor.fetchone()[0]

    logger.info("=" * 60)
    logger.info(f"MERGED DATABASE: {merged_db}")
    logger.info(f"Total companies: {total:,}")
    for source, count in sources:
        logger.info(f"  Source '{source}': {count:,}")
    logger.info(f"With business description: {with_desc:,} ({with_desc/total*100:.1f}%)")

    conn.close()


if __name__ == "__main__":
    merge_databases()
