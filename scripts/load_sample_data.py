#!/usr/bin/env python3
"""
Load sample data from SQLite databases into PostgreSQL for testing.

This script loads a small sample of companies from the existing SQLite
databases into the PostgreSQL database so you can test the platform
without waiting for full data ingestion.
"""

import asyncio
import sqlite3
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from halo.db.session import AsyncSessionLocal, engine
from halo.db.models import Base, Company, Person
from sqlalchemy import select


async def create_tables():
    """Create database tables."""
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✓ Tables created")


async def load_companies_from_sqlite(limit: int = 100):
    """Load sample companies from unified.db SQLite database."""

    db_path = Path(__file__).parent.parent / "data" / "unified.db"

    if not db_path.exists():
        print(f"⚠ Database not found: {db_path}")
        print("  Try data/bolagsverket_bulk.db or data/allabolag.db instead")
        return 0

    print(f"Loading {limit} sample companies from {db_path.name}...")

    # Connect to SQLite
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check what tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"  Available tables: {', '.join(tables)}")

    # Try to find companies table
    companies_table = None
    for table in tables:
        if 'compan' in table.lower() or 'bolag' in table.lower():
            companies_table = table
            break

    if not companies_table:
        print("  ⚠ No companies table found")
        conn.close()
        return 0

    print(f"  Using table: {companies_table}")

    # Get sample data
    try:
        cursor.execute(f"SELECT * FROM {companies_table} LIMIT {limit}")
        rows = cursor.fetchall()

        if not rows:
            print("  ⚠ No data in table")
            conn.close()
            return 0

        # Get column names
        columns = [desc[0] for desc in cursor.description]
        print(f"  Columns: {', '.join(columns[:10])}...")

        # Map columns to Company model
        async with AsyncSessionLocal() as session:
            count = 0
            for row in rows:
                data = dict(row)

                # Try to map common fields
                company_data = {}

                # Organization number (required)
                for col in ['orgnr', 'organisationsnummer', 'registration_number', 'org_nr']:
                    if col in data and data[col]:
                        company_data['orgnr'] = str(data[col]).strip()
                        break

                if not company_data.get('orgnr'):
                    continue  # Skip if no org number

                # Company name
                for col in ['name', 'company_name', 'foretag', 'foretagsnamn']:
                    if col in data and data[col]:
                        company_data['name'] = str(data[col])[:500]
                        break

                # Status
                for col in ['status', 'company_status']:
                    if col in data and data[col]:
                        company_data['status'] = str(data[col])[:50]
                        break

                # Legal form
                for col in ['legal_form', 'juridisk_form', 'form']:
                    if col in data and data[col]:
                        company_data['legal_form'] = str(data[col])[:100]
                        break

                # Create company
                try:
                    company = Company(**company_data)
                    session.add(company)
                    count += 1

                    if count % 10 == 0:
                        await session.commit()
                        print(f"  Loaded {count}/{limit} companies...", end='\r')

                except Exception as e:
                    # Skip duplicates or invalid data
                    continue

            await session.commit()
            print(f"\n✓ Loaded {count} companies")

        conn.close()
        return count

    except Exception as e:
        print(f"  ✗ Error loading data: {e}")
        conn.close()
        return 0


async def check_data():
    """Check what data was loaded."""
    print("\nChecking loaded data...")

    async with AsyncSessionLocal() as session:
        # Count companies
        result = await session.execute(select(Company))
        companies = result.scalars().all()
        print(f"✓ Total companies in database: {len(companies)}")

        if companies:
            print(f"  Sample: {companies[0].name} ({companies[0].orgnr})")

        # Count persons
        result = await session.execute(select(Person))
        persons = result.scalars().all()
        print(f"✓ Total persons in database: {len(persons)}")


async def main():
    """Load sample data for testing."""
    print("=" * 60)
    print("HALO PLATFORM - SAMPLE DATA LOADER")
    print("=" * 60)
    print()

    try:
        # Create tables
        await create_tables()
        print()

        # Load sample companies
        count = await load_companies_from_sqlite(limit=100)

        if count > 0:
            print()
            await check_data()
            print()
            print("=" * 60)
            print("✓ Sample data loaded successfully!")
            print("=" * 60)
            print()
            print("You can now test the platform:")
            print("  - API: http://localhost:8000/docs")
            print("  - Health: http://localhost:8000/health")
            print()
        else:
            print()
            print("=" * 60)
            print("⚠ No data loaded")
            print("=" * 60)
            print()
            print("To load data manually:")
            print("  1. Check available SQLite databases in data/")
            print("  2. Use the ingestion scripts to populate PostgreSQL")
            print()

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
