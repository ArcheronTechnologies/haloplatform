#!/usr/bin/env python3
"""
Analyze extracted directors for shell company patterns.

Loads results.json into SQLite and runs fraud detection queries:
- Serial directors (same person in multiple companies)
- Shared directors between companies
- Name clustering patterns
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
import unicodedata
import re


def normalize_name(name: str) -> str:
    """Normalize name for matching (lowercase, remove accents, standardize whitespace)."""
    if not name:
        return ""
    # Convert to lowercase
    name = name.lower()
    # Normalize unicode (decompose accents)
    name = unicodedata.normalize('NFKD', name)
    # Remove accent marks
    name = ''.join(c for c in name if not unicodedata.combining(c))
    # Standardize whitespace
    name = ' '.join(name.split())
    return name


def load_to_sqlite(results_file: Path) -> sqlite3.Connection:
    """Load results.json into SQLite database."""
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
        CREATE TABLE companies (
            orgnr TEXT PRIMARY KEY,
            company_name TEXT,
            document_id TEXT,
            extraction_method TEXT,
            extraction_confidence REAL,
            signature_date TEXT,
            processing_time_ms INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE directors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_orgnr TEXT,
            first_name TEXT,
            last_name TEXT,
            full_name TEXT,
            full_name_normalized TEXT,
            role TEXT,
            role_normalized TEXT,
            confidence REAL,
            source_field TEXT,
            FOREIGN KEY (company_orgnr) REFERENCES companies(orgnr)
        )
    ''')

    # Load data
    with open(results_file) as f:
        results = json.load(f)

    for result in results:
        cursor.execute('''
            INSERT INTO companies VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            result['orgnr'],
            result['company_name'],
            result['document_id'],
            result['extraction_method'],
            result['extraction_confidence'],
            result['signature_date'],
            result['processing_time_ms'],
        ))

        for director in result['directors']:
            cursor.execute('''
                INSERT INTO directors
                (company_orgnr, first_name, last_name, full_name, full_name_normalized,
                 role, role_normalized, confidence, source_field)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result['orgnr'],
                director['first_name'],
                director['last_name'],
                director['full_name'],
                normalize_name(director['full_name']),
                director['role'],
                director['role_normalized'],
                director['confidence'],
                director['source_field'],
            ))

    conn.commit()
    return conn


def analyze_serial_directors(conn: sqlite3.Connection) -> list[dict]:
    """Find directors who appear in multiple companies."""
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            full_name_normalized,
            full_name,
            COUNT(DISTINCT company_orgnr) as company_count,
            GROUP_CONCAT(DISTINCT company_orgnr) as orgnrs,
            GROUP_CONCAT(DISTINCT
                (SELECT company_name FROM companies WHERE orgnr = directors.company_orgnr)
            ) as company_names
        FROM directors
        GROUP BY full_name_normalized
        HAVING COUNT(DISTINCT company_orgnr) >= 2
        ORDER BY company_count DESC
    ''')

    results = []
    for row in cursor.fetchall():
        results.append({
            'name_normalized': row[0],
            'name': row[1],
            'company_count': row[2],
            'orgnrs': row[3].split(','),
            'company_names': row[4].split(',') if row[4] else [],
        })

    return results


def analyze_shared_directors(conn: sqlite3.Connection) -> list[dict]:
    """Find pairs of companies that share directors."""
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            d1.company_orgnr as company1,
            d2.company_orgnr as company2,
            COUNT(DISTINCT d1.full_name_normalized) as shared_count,
            GROUP_CONCAT(DISTINCT d1.full_name) as shared_names
        FROM directors d1
        JOIN directors d2 ON d1.full_name_normalized = d2.full_name_normalized
        WHERE d1.company_orgnr < d2.company_orgnr
        GROUP BY d1.company_orgnr, d2.company_orgnr
        HAVING COUNT(DISTINCT d1.full_name_normalized) >= 1
        ORDER BY shared_count DESC
    ''')

    results = []
    for row in cursor.fetchall():
        # Get company names
        cursor.execute('SELECT company_name FROM companies WHERE orgnr = ?', (row[0],))
        name1 = cursor.fetchone()[0]
        cursor.execute('SELECT company_name FROM companies WHERE orgnr = ?', (row[1],))
        name2 = cursor.fetchone()[0]

        results.append({
            'company1_orgnr': row[0],
            'company1_name': name1,
            'company2_orgnr': row[1],
            'company2_name': name2,
            'shared_director_count': row[2],
            'shared_names': row[3].split(',') if row[3] else [],
        })

    return results


def analyze_last_name_clusters(conn: sqlite3.Connection) -> list[dict]:
    """Find clusters of companies with same last name (potential family networks)."""
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            LOWER(last_name) as last_name_norm,
            last_name,
            COUNT(DISTINCT company_orgnr) as company_count,
            COUNT(*) as director_count,
            GROUP_CONCAT(DISTINCT company_orgnr) as orgnrs
        FROM directors
        WHERE last_name IS NOT NULL AND last_name != ''
        GROUP BY LOWER(last_name)
        HAVING COUNT(DISTINCT company_orgnr) >= 2
        ORDER BY company_count DESC
    ''')

    results = []
    for row in cursor.fetchall():
        results.append({
            'last_name': row[1],
            'company_count': row[2],
            'director_count': row[3],
            'orgnrs': row[4].split(','),
        })

    return results


def analyze_director_stats(conn: sqlite3.Connection) -> dict:
    """Get overall statistics."""
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM companies')
    company_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM directors')
    director_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(DISTINCT full_name_normalized) FROM directors')
    unique_directors = cursor.fetchone()[0]

    cursor.execute('''
        SELECT role_normalized, COUNT(*)
        FROM directors
        GROUP BY role_normalized
        ORDER BY COUNT(*) DESC
    ''')
    roles = {row[0]: row[1] for row in cursor.fetchall()}

    return {
        'total_companies': company_count,
        'total_director_records': director_count,
        'unique_directors': unique_directors,
        'roles_breakdown': roles,
    }


def main():
    results_file = Path(__file__).parent.parent / "data" / "extraction_100" / "results.json"

    if not results_file.exists():
        print(f"Error: Results file not found: {results_file}")
        return

    print("=" * 70)
    print("SHELL COMPANY PATTERN ANALYSIS")
    print("=" * 70)
    print(f"\nLoading data from: {results_file}")

    conn = load_to_sqlite(results_file)

    # Overall stats
    stats = analyze_director_stats(conn)
    print(f"\n📊 OVERALL STATISTICS")
    print("-" * 40)
    print(f"Companies with extracted data: {stats['total_companies']}")
    print(f"Total director records: {stats['total_director_records']}")
    print(f"Unique directors (by name): {stats['unique_directors']}")
    print(f"\nRoles breakdown:")
    for role, count in stats['roles_breakdown'].items():
        print(f"  {role}: {count}")

    # Serial directors
    serial = analyze_serial_directors(conn)
    print(f"\n🚨 SERIAL DIRECTORS (same person, multiple companies)")
    print("-" * 40)
    if serial:
        for s in serial:
            print(f"\n  {s['name']} - {s['company_count']} companies")
            for orgnr, name in zip(s['orgnrs'], s['company_names']):
                print(f"    • {orgnr}: {name}")
    else:
        print("  No serial directors found in this sample")

    # Shared directors
    shared = analyze_shared_directors(conn)
    print(f"\n🔗 COMPANY PAIRS WITH SHARED DIRECTORS")
    print("-" * 40)
    if shared:
        for s in shared:
            print(f"\n  {s['company1_name']} ↔ {s['company2_name']}")
            print(f"    Shared: {', '.join(s['shared_names'])}")
            print(f"    Orgnrs: {s['company1_orgnr']} & {s['company2_orgnr']}")
    else:
        print("  No company pairs with shared directors found")

    # Last name clusters
    clusters = analyze_last_name_clusters(conn)
    print(f"\n👨‍👩‍👧‍👦 LAST NAME CLUSTERS (potential family networks)")
    print("-" * 40)
    if clusters:
        for c in clusters[:10]:  # Top 10
            print(f"  {c['last_name']}: {c['company_count']} companies, {c['director_count']} directors")
    else:
        print("  No significant last name clusters found")

    # Summary
    print(f"\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Serial directors found: {len(serial)}")
    print(f"Company pairs with shared directors: {len(shared)}")
    print(f"Significant last name clusters: {len(clusters)}")

    if serial or shared:
        print("\n⚠️  Patterns detected that warrant further investigation!")
    else:
        print("\n✓ No obvious shell company patterns in this sample")
        print("  (Sample size may be too small - try with 1000+ companies)")

    conn.close()


if __name__ == "__main__":
    main()
