#!/usr/bin/env python3
"""
Create unified source-of-truth database merging:
1. companies_merged.db - 1.6M companies from SCB/Bolagsverket bulk
2. directors.db - 307K directors from annual reports
3. allabolag.db - Persons with full birth dates + connections

The unified database enables:
- Entity resolution via birth dates
- Network analysis via person connections
- Complete company + director coverage
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

# Source databases
COMPANIES_MERGED_DB = DATA_DIR / "companies_merged.db"
DIRECTORS_DB = DATA_DIR / "directors.db"
ALLABOLAG_DB = DATA_DIR / "allabolag.db"

# Output
UNIFIED_DB = DATA_DIR / "unified.db"


UNIFIED_SCHEMA = """
-- Unified Source of Truth Database
-- Merges: SCB/Bolagsverket bulk + Bolagsverket directors + Allabolag persons

-- Companies (from all sources)
CREATE TABLE IF NOT EXISTS companies (
    org_nr TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    legal_name TEXT,

    -- From bulk data
    legal_form_code TEXT,
    legal_form TEXT,
    sni_code TEXT,
    sni_code2 TEXT,
    sni_code3 TEXT,
    street_address TEXT,
    postal_code TEXT,
    city TEXT,
    business_description TEXT,

    -- From allabolag
    status TEXT,
    status_date TEXT,
    registration_date TEXT,
    company_type TEXT,
    municipality TEXT,
    county TEXT,
    parent_org_nr TEXT,
    parent_name TEXT,
    revenue_ksek INTEGER,
    profit_ksek INTEGER,
    employees INTEGER,

    -- Metadata
    source TEXT,  -- 'bulk', 'allabolag', 'both'
    allabolag_company_id TEXT,
    bulk_scraped_at TEXT,
    allabolag_scraped_at TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Persons (deduplicated by allabolag_person_id or name+birth_date)
CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    allabolag_person_id TEXT UNIQUE,
    name TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,

    -- For entity resolution
    birth_date TEXT,          -- YYYY-MM-DD (from allabolag)
    year_of_birth INTEGER,
    gender TEXT,              -- 'M' or 'F'

    -- Metadata
    source TEXT,              -- 'allabolag', 'bolagsverket', 'both'
    allabolag_scraped_at TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Roles (person <-> company relationships)
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_org_nr TEXT NOT NULL,
    person_id INTEGER NOT NULL,

    role_type TEXT NOT NULL,
    role_group TEXT,

    -- From Bolagsverket annual reports
    report_year INTEGER,

    -- Source tracking
    source TEXT,              -- 'allabolag', 'bolagsverket', 'both'
    discovered_at TEXT,

    UNIQUE(company_org_nr, person_id, role_type),
    FOREIGN KEY (company_org_nr) REFERENCES companies(org_nr),
    FOREIGN KEY (person_id) REFERENCES persons(id)
);

-- Person connections (network from allabolag)
CREATE TABLE IF NOT EXISTS person_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    connected_person_id INTEGER NOT NULL,
    num_shared_companies INTEGER,
    discovered_at TEXT,

    UNIQUE(person_id, connected_person_id),
    FOREIGN KEY (person_id) REFERENCES persons(id),
    FOREIGN KEY (connected_person_id) REFERENCES persons(id)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_companies_sni ON companies(sni_code);
CREATE INDEX IF NOT EXISTS idx_companies_city ON companies(city);
CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(status);
CREATE INDEX IF NOT EXISTS idx_companies_parent ON companies(parent_org_nr);

CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);
CREATE INDEX IF NOT EXISTS idx_persons_birth ON persons(birth_date);
CREATE INDEX IF NOT EXISTS idx_persons_allabolag_id ON persons(allabolag_person_id);

CREATE INDEX IF NOT EXISTS idx_roles_company ON roles(company_org_nr);
CREATE INDEX IF NOT EXISTS idx_roles_person ON roles(person_id);
CREATE INDEX IF NOT EXISTS idx_roles_type ON roles(role_type);
"""


def create_unified_db():
    """Create the unified database with schema."""
    if UNIFIED_DB.exists():
        logger.info(f"Removing existing {UNIFIED_DB}")
        UNIFIED_DB.unlink()

    conn = sqlite3.connect(UNIFIED_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(UNIFIED_SCHEMA)
    conn.commit()
    logger.info(f"Created unified database: {UNIFIED_DB}")
    return conn


def import_bulk_companies(unified_conn):
    """Import companies from companies_merged.db."""
    if not COMPANIES_MERGED_DB.exists():
        logger.warning(f"Bulk companies not found: {COMPANIES_MERGED_DB}")
        return 0

    logger.info("Importing bulk companies...")
    bulk_conn = sqlite3.connect(COMPANIES_MERGED_DB)

    cursor = bulk_conn.execute("""
        SELECT orgnr, name, company_name, legal_form_code, legal_form,
               sni_code1, sni_code2, sni_code3, street_address,
               postal_code, city, business_description, source, registration_date
        FROM companies
    """)

    now = datetime.utcnow().isoformat()
    count = 0
    batch = []

    for row in cursor:
        org_nr = row[0].replace('-', '') if row[0] else None
        if not org_nr:
            continue

        batch.append((
            org_nr,
            row[1] or row[2],  # name or company_name
            row[2],            # legal_name (company_name)
            row[3],            # legal_form_code
            row[4],            # legal_form
            row[5],            # sni_code
            row[6],            # sni_code2
            row[7],            # sni_code3
            row[8],            # street_address
            row[9],            # postal_code
            row[10],           # city
            row[11],           # business_description
            row[13],           # registration_date
            'bulk',            # source
            now,               # bulk_scraped_at
        ))

        if len(batch) >= 10000:
            unified_conn.executemany("""
                INSERT OR IGNORE INTO companies
                (org_nr, name, legal_name, legal_form_code, legal_form,
                 sni_code, sni_code2, sni_code3, street_address,
                 postal_code, city, business_description, registration_date,
                 source, bulk_scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            unified_conn.commit()
            count += len(batch)
            batch = []
            if count % 100000 == 0:
                logger.info(f"  Imported {count:,} companies...")

    if batch:
        unified_conn.executemany("""
            INSERT OR IGNORE INTO companies
            (org_nr, name, legal_name, legal_form_code, legal_form,
             sni_code, sni_code2, sni_code3, street_address,
             postal_code, city, business_description, registration_date,
             source, bulk_scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)
        unified_conn.commit()
        count += len(batch)

    bulk_conn.close()
    logger.info(f"Imported {count:,} companies from bulk data")
    return count


def import_allabolag_companies(unified_conn):
    """Import/update companies from allabolag.db."""
    if not ALLABOLAG_DB.exists():
        logger.warning(f"Allabolag database not found: {ALLABOLAG_DB}")
        return 0

    logger.info("Importing allabolag companies...")
    aa_conn = sqlite3.connect(ALLABOLAG_DB)

    cursor = aa_conn.execute("""
        SELECT org_nr, name, legal_name, status, status_date, registration_date,
               company_type, sni_code, municipality, county,
               parent_org_nr, parent_name, revenue, profit, employees,
               allabolag_company_id, scraped_at
        FROM companies
        WHERE name != 'Unknown'
    """)

    count = 0
    for row in cursor:
        org_nr = row[0]

        # Check if exists from bulk
        existing = unified_conn.execute(
            "SELECT source FROM companies WHERE org_nr = ?", (org_nr,)
        ).fetchone()

        if existing:
            # Update with allabolag data
            unified_conn.execute("""
                UPDATE companies SET
                    status = COALESCE(?, status),
                    status_date = COALESCE(?, status_date),
                    company_type = COALESCE(?, company_type),
                    municipality = COALESCE(?, municipality),
                    county = COALESCE(?, county),
                    parent_org_nr = COALESCE(?, parent_org_nr),
                    parent_name = COALESCE(?, parent_name),
                    revenue_ksek = COALESCE(?, revenue_ksek),
                    profit_ksek = COALESCE(?, profit_ksek),
                    employees = COALESCE(?, employees),
                    allabolag_company_id = ?,
                    allabolag_scraped_at = ?,
                    source = 'both',
                    updated_at = CURRENT_TIMESTAMP
                WHERE org_nr = ?
            """, (
                row[3], row[4], row[6], row[7], row[8], row[9], row[10],
                row[11], row[12], row[13], row[14], row[15], org_nr
            ))
        else:
            # Insert new
            unified_conn.execute("""
                INSERT INTO companies
                (org_nr, name, legal_name, status, status_date, registration_date,
                 company_type, sni_code, municipality, county,
                 parent_org_nr, parent_name, revenue_ksek, profit_ksek, employees,
                 allabolag_company_id, allabolag_scraped_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'allabolag')
            """, row)

        count += 1

    unified_conn.commit()
    aa_conn.close()
    logger.info(f"Imported/updated {count:,} companies from allabolag")
    return count


def import_allabolag_persons(unified_conn):
    """Import persons from allabolag.db (with birth dates)."""
    if not ALLABOLAG_DB.exists():
        return 0

    logger.info("Importing allabolag persons...")
    aa_conn = sqlite3.connect(ALLABOLAG_DB)

    cursor = aa_conn.execute("""
        SELECT allabolag_person_id, name, birth_date, year_of_birth, gender,
               person_page_scraped_at
        FROM persons
    """)

    count = 0
    for row in cursor:
        # Split name into first/last
        name = row[1]
        parts = name.split() if name else []
        first_name = parts[0] if parts else None
        last_name = ' '.join(parts[1:]) if len(parts) > 1 else None

        unified_conn.execute("""
            INSERT OR REPLACE INTO persons
            (allabolag_person_id, name, first_name, last_name,
             birth_date, year_of_birth, gender, source, allabolag_scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'allabolag', ?)
        """, (row[0], name, first_name, last_name, row[2], row[3], row[4], row[5]))
        count += 1

    unified_conn.commit()
    aa_conn.close()
    logger.info(f"Imported {count:,} persons from allabolag (with birth dates)")
    return count


def import_bolagsverket_directors(unified_conn):
    """Import directors from directors.db, matching to allabolag persons where possible."""
    if not DIRECTORS_DB.exists():
        logger.warning(f"Directors database not found: {DIRECTORS_DB}")
        return 0

    logger.info("Importing Bolagsverket directors...")
    dir_conn = sqlite3.connect(DIRECTORS_DB)

    cursor = dir_conn.execute("""
        SELECT orgnr, first_name, last_name, role, report_year
        FROM directors
    """)

    count = 0
    matched = 0
    new_persons = 0

    for row in cursor:
        org_nr = row[0].replace('-', '') if row[0] else None
        if not org_nr:
            continue

        first_name = row[1]
        last_name = row[2]
        full_name = f"{first_name} {last_name}".strip()
        role = row[3] or 'Unknown'
        report_year = row[4]

        # Try to find matching allabolag person by name
        # This is fuzzy - better matching would use birth year + company
        person_row = unified_conn.execute("""
            SELECT id FROM persons
            WHERE name LIKE ? OR (first_name = ? AND last_name = ?)
            LIMIT 1
        """, (f"%{full_name}%", first_name, last_name)).fetchone()

        if person_row:
            person_id = person_row[0]
            matched += 1
        else:
            # Create new person without birth date
            cursor2 = unified_conn.execute("""
                INSERT INTO persons (name, first_name, last_name, source)
                VALUES (?, ?, ?, 'bolagsverket')
            """, (full_name, first_name, last_name))
            person_id = cursor2.lastrowid
            new_persons += 1

        # Ensure company exists (placeholder if not)
        existing = unified_conn.execute(
            "SELECT org_nr FROM companies WHERE org_nr = ?", (org_nr,)
        ).fetchone()
        if not existing:
            unified_conn.execute("""
                INSERT INTO companies (org_nr, name, source)
                VALUES (?, 'Unknown', 'bolagsverket')
            """, (org_nr,))

        # Insert role
        unified_conn.execute("""
            INSERT OR IGNORE INTO roles
            (company_org_nr, person_id, role_type, report_year, source, discovered_at)
            VALUES (?, ?, ?, ?, 'bolagsverket', CURRENT_TIMESTAMP)
        """, (org_nr, person_id, role, report_year))

        count += 1
        if count % 50000 == 0:
            unified_conn.commit()
            logger.info(f"  Processed {count:,} directors ({matched:,} matched, {new_persons:,} new)...")

    unified_conn.commit()
    dir_conn.close()
    logger.info(f"Imported {count:,} directors ({matched:,} matched to allabolag, {new_persons:,} new persons)")
    return count


def import_allabolag_roles(unified_conn):
    """Import roles from allabolag.db."""
    if not ALLABOLAG_DB.exists():
        return 0

    logger.info("Importing allabolag roles...")
    aa_conn = sqlite3.connect(ALLABOLAG_DB)

    # Need to map allabolag person IDs to unified person IDs
    cursor = aa_conn.execute("""
        SELECT r.company_org_nr, p.allabolag_person_id, r.role_type, r.role_group, r.scraped_at
        FROM roles r
        JOIN persons p ON p.id = r.person_id
    """)

    count = 0
    for row in cursor:
        # Get unified person ID
        person_row = unified_conn.execute(
            "SELECT id FROM persons WHERE allabolag_person_id = ?",
            (row[1],)
        ).fetchone()

        if not person_row:
            continue

        unified_conn.execute("""
            INSERT OR IGNORE INTO roles
            (company_org_nr, person_id, role_type, role_group, source, discovered_at)
            VALUES (?, ?, ?, ?, 'allabolag', ?)
        """, (row[0], person_row[0], row[2], row[3], row[4]))
        count += 1

    unified_conn.commit()
    aa_conn.close()
    logger.info(f"Imported {count:,} roles from allabolag")
    return count


def import_allabolag_connections(unified_conn):
    """Import person connections from allabolag.db."""
    if not ALLABOLAG_DB.exists():
        return 0

    logger.info("Importing person connections...")
    aa_conn = sqlite3.connect(ALLABOLAG_DB)

    cursor = aa_conn.execute("""
        SELECT p1.allabolag_person_id, p2.allabolag_person_id,
               c.num_shared_companies, c.discovered_at
        FROM person_connections c
        JOIN persons p1 ON p1.id = c.person_id
        JOIN persons p2 ON p2.id = c.connected_person_id
    """)

    count = 0
    for row in cursor:
        # Get unified person IDs
        p1 = unified_conn.execute(
            "SELECT id FROM persons WHERE allabolag_person_id = ?", (row[0],)
        ).fetchone()
        p2 = unified_conn.execute(
            "SELECT id FROM persons WHERE allabolag_person_id = ?", (row[1],)
        ).fetchone()

        if p1 and p2:
            unified_conn.execute("""
                INSERT OR IGNORE INTO person_connections
                (person_id, connected_person_id, num_shared_companies, discovered_at)
                VALUES (?, ?, ?, ?)
            """, (p1[0], p2[0], row[2], row[3]))
            count += 1

    unified_conn.commit()
    aa_conn.close()
    logger.info(f"Imported {count:,} person connections")
    return count


def print_summary(conn):
    """Print summary statistics."""
    print("\n" + "=" * 60)
    print("UNIFIED DATABASE SUMMARY")
    print("=" * 60)

    # Companies
    total = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    bulk_only = conn.execute("SELECT COUNT(*) FROM companies WHERE source = 'bulk'").fetchone()[0]
    both = conn.execute("SELECT COUNT(*) FROM companies WHERE source = 'both'").fetchone()[0]
    print(f"\nCompanies: {total:,}")
    print(f"  - From bulk only: {bulk_only:,}")
    print(f"  - Enriched with allabolag: {both:,}")

    # Persons
    total = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
    with_dob = conn.execute("SELECT COUNT(*) FROM persons WHERE birth_date IS NOT NULL").fetchone()[0]
    from_aa = conn.execute("SELECT COUNT(*) FROM persons WHERE source = 'allabolag'").fetchone()[0]
    print(f"\nPersons: {total:,}")
    print(f"  - With full birth date: {with_dob:,} ({100*with_dob/total:.1f}%)")
    print(f"  - From allabolag: {from_aa:,}")

    # Roles
    total = conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
    print(f"\nRoles: {total:,}")

    # Connections
    total = conn.execute("SELECT COUNT(*) FROM person_connections").fetchone()[0]
    print(f"\nPerson connections: {total:,}")

    # DB size
    import os
    size_mb = os.path.getsize(UNIFIED_DB) / 1024 / 1024
    print(f"\nDatabase size: {size_mb:.1f} MB")
    print("=" * 60)


def main():
    logger.info("Creating unified source-of-truth database...")

    conn = create_unified_db()

    # Import in order of priority (bulk first, then enrich)
    import_bulk_companies(conn)
    import_allabolag_companies(conn)
    import_allabolag_persons(conn)
    import_bolagsverket_directors(conn)
    import_allabolag_roles(conn)
    import_allabolag_connections(conn)

    print_summary(conn)
    conn.close()

    logger.info(f"Done! Unified database: {UNIFIED_DB}")


if __name__ == '__main__':
    main()
