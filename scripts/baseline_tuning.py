"""
Baseline Tuning Analysis

Extracts real statistics from Swedish company data to calibrate detection thresholds.

Usage:
    python baseline_tuning.py --db allabolag_scrape.db

Output:
    - Statistical summary of all metrics
    - Recommended threshold values
    - Updated constants for anomaly.py
    - Metadata for reproducibility
"""
import sqlite3
import argparse
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional
from collections import Counter
import statistics
from pathlib import Path
from datetime import date, datetime


@dataclass
class SampleMetadata:
    """Tracks what data the baseline was calibrated on."""
    calibration_date: str
    sample_size: int
    
    # Filters applied to sample
    status_filter: str          # e.g., "active only"
    legal_form_filter: str      # e.g., "AB (49)"
    geography_filter: str       # e.g., "all Sweden"
    sni_filter: str             # e.g., "all" or "86,87,88"
    
    # Data coverage (0.0 - 1.0)
    address_coverage: float     # % of companies with address data
    director_coverage: float    # % of companies with director data
    financial_coverage: float   # % of companies with revenue/employee data
    age_coverage: float         # % of companies with formation date
    
    # Source info
    data_sources: List[str]     # e.g., ["SCB", "Bolagsverket", "Allabolag"]
    database_path: str
    
    # Recalibration tracking
    next_recalibration: str     # ISO date
    notes: str
    
    def coverage_summary(self) -> str:
        return (
            f"Coverage: address={self.address_coverage:.0%}, "
            f"directors={self.director_coverage:.0%}, "
            f"financials={self.financial_coverage:.0%}, "
            f"age={self.age_coverage:.0%}"
        )


@dataclass
class DistributionStats:
    """Statistics for a single metric."""
    count: int
    mean: float
    std: float
    median: float
    p75: float
    p90: float
    p95: float
    p99: float
    max: float
    
    def __str__(self):
        return (
            f"  n={self.count:,}, mean={self.mean:.2f}, std={self.std:.2f}\n"
            f"  median={self.median:.2f}, p75={self.p75:.2f}, p90={self.p90:.2f}\n"
            f"  p95={self.p95:.2f}, p99={self.p99:.2f}, max={self.max:.2f}"
        )


def compute_distribution(values: List[float]) -> Optional[DistributionStats]:
    """Compute distribution statistics for a list of values."""
    if not values or len(values) < 10:
        return None
    
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    
    def percentile(p: float) -> float:
        idx = int(n * p / 100)
        return sorted_vals[min(idx, n - 1)]
    
    return DistributionStats(
        count=n,
        mean=statistics.mean(values),
        std=statistics.stdev(values) if n > 1 else 0,
        median=statistics.median(values),
        p75=percentile(75),
        p90=percentile(90),
        p95=percentile(95),
        p99=percentile(99),
        max=max(values),
    )


class BaselineAnalyzer:
    """Analyzes company data to extract baseline statistics."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        
        # Results storage
        self.results: Dict[str, DistributionStats] = {}
        self.raw_data: Dict[str, List] = {}
        self.metadata: Optional[SampleMetadata] = None
    
    def compute_metadata(self) -> SampleMetadata:
        """Compute sample metadata and coverage statistics."""
        total = self._get_company_count()
        
        # Count coverage for each data type
        address_count = self.conn.execute("""
            SELECT COUNT(*) FROM companies
            WHERE street_address IS NOT NULL AND street_address != ''
        """).fetchone()[0]
        
        # Check if directors table exists
        has_directors = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='directors'"
        ).fetchone() is not None
        
        if has_directors:
            companies_with_directors = self.conn.execute("""
                SELECT COUNT(DISTINCT orgnr) FROM directors
            """).fetchone()[0]
        else:
            companies_with_directors = 0
        
        financial_count = self.conn.execute("""
            SELECT COUNT(*) FROM companies 
            WHERE revenue IS NOT NULL AND revenue > 0
              AND employees IS NOT NULL AND employees > 0
        """).fetchone()[0]
        
        age_count = self.conn.execute("""
            SELECT COUNT(*) FROM companies
            WHERE registration_date IS NOT NULL
              AND registration_date != ''
              AND registration_date LIKE '____-__-__'
        """).fetchone()[0]
        
        # Detect data sources from available fields
        sources = ["SCB"]  # Assume SCB is always base
        if financial_count > 0:
            sources.append("Bolagsverket")
        if companies_with_directors > 0:
            sources.append("Allabolag")
        
        # Calculate next recalibration (3 months out, or sooner if low director coverage)
        director_coverage = companies_with_directors / total if total > 0 else 0
        if director_coverage < 0.5:
            # Recalibrate monthly until we have good director data
            next_recal = date.today().replace(day=1)
            if next_recal.month == 12:
                next_recal = next_recal.replace(year=next_recal.year + 1, month=1)
            else:
                next_recal = next_recal.replace(month=next_recal.month + 1)
        else:
            # Quarterly recalibration once stable
            next_recal = date.today().replace(day=1)
            for _ in range(3):
                if next_recal.month == 12:
                    next_recal = next_recal.replace(year=next_recal.year + 1, month=1)
                else:
                    next_recal = next_recal.replace(month=next_recal.month + 1)
        
        self.metadata = SampleMetadata(
            calibration_date=date.today().isoformat(),
            sample_size=total,
            status_filter="active only",
            legal_form_filter="AB (49)",
            geography_filter="all Sweden",
            sni_filter="all",
            address_coverage=address_count / total if total > 0 else 0,
            director_coverage=director_coverage,
            financial_coverage=financial_count / total if total > 0 else 0,
            age_coverage=age_count / total if total > 0 else 0,
            data_sources=sources,
            database_path=self.db_path,
            next_recalibration=next_recal.isoformat(),
            notes="Initial calibration" if director_coverage < 0.1 else "",
        )
        
        return self.metadata
    
    def run_all(self):
        """Run all analyses."""
        print("=" * 60)
        print("BASELINE TUNING ANALYSIS")
        print("=" * 60)
        print(f"Database: {self.db_path}")
        
        # Compute metadata first
        self.compute_metadata()
        
        # Print metadata summary
        print("\n" + "-" * 60)
        print("SAMPLE METADATA")
        print("-" * 60)
        print(f"Calibration date: {self.metadata.calibration_date}")
        print(f"Sample size: {self.metadata.sample_size:,} companies")
        print(f"Filters: {self.metadata.status_filter}, {self.metadata.legal_form_filter}")
        print(f"Geography: {self.metadata.geography_filter}")
        print(f"SNI: {self.metadata.sni_filter}")
        print(f"Data sources: {', '.join(self.metadata.data_sources)}")
        print(f"\n{self.metadata.coverage_summary()}")
        print(f"\nNext recalibration: {self.metadata.next_recalibration}")
        
        if self.metadata.director_coverage < 0.1:
            print("\n⚠️  LOW DIRECTOR COVERAGE")
            print("   Director-based thresholds will be placeholders.")
            print("   Re-run after allabolag enrichment progresses.")
        
        # Get basic counts
        self._print_basic_counts()
        
        # Run each analysis
        print("\n" + "=" * 60)
        print("1. ADDRESS DENSITY (companies per address)")
        print("=" * 60)
        self.analyze_address_density()
        
        print("\n" + "=" * 60)
        print("2. DIRECTOR ROLES (directorships per person)")
        print("=" * 60)
        self.analyze_director_roles()
        
        print("\n" + "=" * 60)
        print("3. COMPANY AGE DISTRIBUTION")
        print("=" * 60)
        self.analyze_company_age()
        
        print("\n" + "=" * 60)
        print("4. REVENUE PER EMPLOYEE")
        print("=" * 60)
        self.analyze_revenue_per_employee()
        
        print("\n" + "=" * 60)
        print("5. SNI CODE DISTRIBUTION")
        print("=" * 60)
        self.analyze_sni_distribution()
        
        print("\n" + "=" * 60)
        print("6. DIRECTORS PER COMPANY")
        print("=" * 60)
        self.analyze_directors_per_company()
        
        # Output recommendations
        print("\n" + "=" * 60)
        print("RECOMMENDED THRESHOLDS")
        print("=" * 60)
        self.print_recommendations()
        
        # Output code
        print("\n" + "=" * 60)
        print("UPDATED CODE FOR anomaly.py")
        print("=" * 60)
        self.print_code_update()
    
    def _print_basic_counts(self):
        """Print basic database counts."""
        companies = self.conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        
        # Check if directors table exists
        tables = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        
        directors = 0
        if 'directors' in table_names:
            directors = self.conn.execute("SELECT COUNT(*) FROM directors").fetchone()[0]
        
        print(f"\nTotal companies: {companies:,}")
        print(f"Total director records: {directors:,}")
        
        if directors == 0:
            print("\n⚠️  WARNING: No director data found!")
            print("   Director-based analyses will be skipped.")
            print("   You need allabolag scrape data for director analysis.")
    
    def analyze_address_density(self):
        """Analyze how many companies share each address."""
        # Normalize addresses and count
        rows = self.conn.execute("""
            SELECT
                LOWER(TRIM(COALESCE(street_address, '') || ' ' || COALESCE(postal_code, '') || ' ' || COALESCE(city, ''))) as full_addr,
                COUNT(*) as company_count
            FROM companies
            WHERE street_address IS NOT NULL AND street_address != ''
            GROUP BY full_addr
        """).fetchall()
        
        if not rows:
            print("No address data available.")
            return
        
        densities = [row['company_count'] for row in rows]
        stats = compute_distribution(densities)
        self.results['address_density'] = stats
        
        print(f"\nUnique addresses: {len(rows):,}")
        print(f"\nDistribution of companies per address:")
        print(stats)
        
        # Show high-density addresses
        high_density = [r for r in rows if r['company_count'] >= (stats.p99 if stats else 10)]
        if high_density:
            print(f"\n Top addresses (>= p99 = {stats.p99:.0f} companies):")
            for row in sorted(high_density, key=lambda x: -x['company_count'])[:10]:
                addr = row['full_addr'][:60]
                print(f"   {row['company_count']:4d} companies: {addr}")
    
    def analyze_director_roles(self):
        """Analyze how many directorships each person holds."""
        # Check if directors table exists
        tables = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='directors'"
        ).fetchone()
        
        if not tables:
            print("No directors table found. Skipping.")
            return
        
        # Count roles per person (by name - imperfect but best we have without personnummer)
        rows = self.conn.execute("""
            SELECT 
                LOWER(TRIM(name)) as normalized_name,
                COUNT(DISTINCT orgnr) as role_count
            FROM directors
            WHERE name IS NOT NULL AND name != ''
            GROUP BY normalized_name
        """).fetchall()
        
        if not rows:
            print("No director data available.")
            return
        
        role_counts = [row['role_count'] for row in rows]
        stats = compute_distribution(role_counts)
        self.results['director_roles'] = stats
        
        print(f"\nUnique director names: {len(rows):,}")
        print(f"\nDistribution of directorships per person:")
        print(stats)
        
        # Show serial directors
        serial = [r for r in rows if r['role_count'] >= (stats.p99 if stats else 5)]
        if serial:
            print(f"\n Serial directors (>= p99 = {stats.p99:.0f} roles):")
            for row in sorted(serial, key=lambda x: -x['role_count'])[:15]:
                print(f"   {row['role_count']:4d} roles: {row['normalized_name'][:50]}")
    
    def analyze_company_age(self):
        """Analyze company age distribution."""
        rows = self.conn.execute("""
            SELECT
                registration_date,
                (julianday('now') - julianday(registration_date)) / 365.25 as age_years
            FROM companies
            WHERE registration_date IS NOT NULL
              AND registration_date != ''
              AND registration_date LIKE '____-__-__'
        """).fetchall()
        
        if not rows:
            print("No formation date data available.")
            return
        
        ages = [row['age_years'] for row in rows if row['age_years'] and row['age_years'] > 0]
        stats = compute_distribution(ages)
        self.results['company_age'] = stats
        
        print(f"\nCompanies with valid formation date: {len(ages):,}")
        print(f"\nAge distribution (years):")
        print(stats)
        
        # Recent formations (potential shells)
        recent = len([a for a in ages if a < 2])
        print(f"\n Companies < 2 years old: {recent:,} ({100*recent/len(ages):.1f}%)")
    
    def analyze_revenue_per_employee(self):
        """Analyze revenue per employee ratios."""
        rows = self.conn.execute("""
            SELECT 
                revenue,
                employees,
                CAST(revenue AS FLOAT) / NULLIF(employees, 0) as rev_per_emp
            FROM companies
            WHERE revenue IS NOT NULL 
              AND revenue > 0
              AND employees IS NOT NULL 
              AND employees > 0
        """).fetchall()
        
        if not rows:
            print("No revenue/employee data available.")
            return
        
        ratios = [row['rev_per_emp'] for row in rows if row['rev_per_emp'] and row['rev_per_emp'] > 0]
        stats = compute_distribution(ratios)
        self.results['revenue_per_employee'] = stats
        
        print(f"\nCompanies with revenue+employee data: {len(ratios):,}")
        print(f"\nRevenue per employee (SEK):")
        print(stats)
        
        # Flag potential invoice factories (very high ratio)
        suspicious = len([r for r in ratios if r > 5_000_000])
        print(f"\n Companies with >5M SEK/employee: {suspicious:,}")
    
    def analyze_sni_distribution(self):
        """Analyze SNI code distribution."""
        rows = self.conn.execute("""
            SELECT 
                SUBSTR(sni_code, 1, 2) as sni_2digit,
                COUNT(*) as count
            FROM companies
            WHERE sni_code IS NOT NULL AND sni_code != ''
            GROUP BY sni_2digit
            ORDER BY count DESC
        """).fetchall()
        
        if not rows:
            print("No SNI code data available.")
            return
        
        total = sum(r['count'] for r in rows)
        print(f"\nCompanies with SNI codes: {total:,}")
        print(f"\nTop SNI categories (2-digit):")
        
        # SNI descriptions (common ones)
        sni_names = {
            '46': 'Wholesale trade',
            '47': 'Retail trade',
            '41': 'Construction of buildings',
            '43': 'Specialized construction',
            '68': 'Real estate',
            '70': 'Management consultancy',
            '62': 'Computer programming',
            '56': 'Food/beverage service',
            '86': 'Human health activities',
            '87': 'Residential care',
            '88': 'Social work',
            '49': 'Land transport',
            '96': 'Other personal services',
            '45': 'Motor vehicle trade',
            '69': 'Legal/accounting',
        }
        
        for row in rows[:20]:
            sni = row['sni_2digit']
            name = sni_names.get(sni, '')
            pct = 100 * row['count'] / total
            print(f"   {sni}: {row['count']:6,} ({pct:5.1f}%) {name}")
        
        # Healthcare (fraud-relevant)
        healthcare = sum(r['count'] for r in rows if r['sni_2digit'] in ('86', '87', '88'))
        print(f"\n Healthcare sector (86+87+88): {healthcare:,} ({100*healthcare/total:.1f}%)")
    
    def analyze_directors_per_company(self):
        """Analyze how many directors each company has."""
        tables = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='directors'"
        ).fetchone()
        
        if not tables:
            print("No directors table found. Skipping.")
            return
        
        rows = self.conn.execute("""
            SELECT 
                orgnr,
                COUNT(*) as director_count
            FROM directors
            GROUP BY orgnr
        """).fetchall()
        
        if not rows:
            print("No director data available.")
            return
        
        counts = [row['director_count'] for row in rows]
        stats = compute_distribution(counts)
        self.results['directors_per_company'] = stats
        
        print(f"\nCompanies with director data: {len(rows):,}")
        print(f"\nDirectors per company:")
        print(stats)
        
        # Single-director companies (potential shell indicator)
        single = len([c for c in counts if c == 1])
        print(f"\n Single-director companies: {single:,} ({100*single/len(counts):.1f}%)")
    
    def print_recommendations(self):
        """Print recommended thresholds based on analysis."""
        print("\nBased on the data, recommended thresholds:\n")
        
        if 'address_density' in self.results:
            s = self.results['address_density']
            print(f"ADDRESS DENSITY:")
            print(f"  Mean: {s.mean:.2f}")
            print(f"  Flag at p95 ({s.p95:.0f}): Catches top 5% - use for 'suspicious'")
            print(f"  Flag at p99 ({s.p99:.0f}): Catches top 1% - use for 'highly suspicious'")
        
        if 'director_roles' in self.results:
            s = self.results['director_roles']
            print(f"\nDIRECTOR ROLES:")
            print(f"  Mean: {s.mean:.2f}")
            print(f"  Flag at p95 ({s.p95:.0f}): Professional directors, worth noting")
            print(f"  Flag at p99 ({s.p99:.0f}): Potential nominees, investigate")
        
        if 'revenue_per_employee' in self.results:
            s = self.results['revenue_per_employee']
            print(f"\nREVENUE PER EMPLOYEE:")
            print(f"  Mean: {s.mean:,.0f} SEK")
            print(f"  Median: {s.median:,.0f} SEK")
            print(f"  Flag at p99 ({s.p99:,.0f}): Potential invoice factory")
        
        if 'directors_per_company' in self.results:
            s = self.results['directors_per_company']
            print(f"\nDIRECTORS PER COMPANY:")
            print(f"  Mean: {s.mean:.2f}")
            print(f"  Single-director companies are common but correlate with shells")
    
    def print_code_update(self):
        """Print updated Python code for anomaly.py."""
        
        print(f"""
# ============================================================================
# BASELINE CALIBRATION
# ============================================================================
# Auto-generated by baseline_tuning.py
# DO NOT EDIT MANUALLY - re-run calibration script to update
# ============================================================================

from dataclasses import dataclass
from typing import List

@dataclass
class BaselineMetadata:
    \"\"\"Tracks calibration provenance for reproducibility.\"\"\"
    calibration_date: str = "{self.metadata.calibration_date}"
    sample_size: int = {self.metadata.sample_size}
    status_filter: str = "{self.metadata.status_filter}"
    legal_form_filter: str = "{self.metadata.legal_form_filter}"
    geography_filter: str = "{self.metadata.geography_filter}"
    sni_filter: str = "{self.metadata.sni_filter}"
    address_coverage: float = {self.metadata.address_coverage:.3f}
    director_coverage: float = {self.metadata.director_coverage:.3f}
    financial_coverage: float = {self.metadata.financial_coverage:.3f}
    age_coverage: float = {self.metadata.age_coverage:.3f}
    data_sources: tuple = {tuple(self.metadata.data_sources)}
    next_recalibration: str = "{self.metadata.next_recalibration}"

BASELINE_META = BaselineMetadata()
""")
        
        print("""
@dataclass
class BaselineStats:
    \"\"\"Calibrated from real Swedish company data.\"\"\"
    """)
        
        if 'address_density' in self.results:
            s = self.results['address_density']
            print(f"    # Address density (companies per address)")
            print(f"    # Coverage: {self.metadata.address_coverage:.0%}")
            print(f"    addr_density_mean: float = {s.mean:.2f}")
            print(f"    addr_density_std: float = {s.std:.2f}")
            print(f"    addr_density_p95: float = {s.p95:.1f}")
            print(f"    addr_density_p99: float = {s.p99:.1f}")
            print()
        else:
            print(f"    # Address density - NO DATA")
            print(f"    addr_density_mean: float = 1.5  # PLACEHOLDER")
            print(f"    addr_density_std: float = 2.0   # PLACEHOLDER")
            print(f"    addr_density_p95: float = 5.0   # PLACEHOLDER")
            print(f"    addr_density_p99: float = 10.0  # PLACEHOLDER")
            print()
        
        if 'director_roles' in self.results:
            s = self.results['director_roles']
            print(f"    # Director roles (directorships per person)")
            print(f"    # Coverage: {self.metadata.director_coverage:.0%}")
            print(f"    director_roles_mean: float = {s.mean:.2f}")
            print(f"    director_roles_std: float = {s.std:.2f}")
            print(f"    director_roles_p95: float = {s.p95:.1f}")
            print(f"    director_roles_p99: float = {s.p99:.1f}")
            print()
        else:
            print(f"    # Director roles - NO DATA (awaiting allabolag enrichment)")
            print(f"    # Using conservative placeholders to avoid false positives")
            print(f"    director_roles_mean: float = 1.2   # PLACEHOLDER")
            print(f"    director_roles_std: float = 0.8    # PLACEHOLDER")
            print(f"    director_roles_p95: float = 3.0    # PLACEHOLDER - conservative")
            print(f"    director_roles_p99: float = 6.0    # PLACEHOLDER - conservative")
            print()
        
        if 'revenue_per_employee' in self.results:
            s = self.results['revenue_per_employee']
            print(f"    # Revenue per employee (SEK)")
            print(f"    # Coverage: {self.metadata.financial_coverage:.0%}")
            print(f"    rev_per_emp_mean: float = {s.mean:.0f}")
            print(f"    rev_per_emp_median: float = {s.median:.0f}")
            print(f"    rev_per_emp_p95: float = {s.p95:.0f}")
            print(f"    rev_per_emp_p99: float = {s.p99:.0f}")
            print()
        else:
            print(f"    # Revenue per employee - NO DATA")
            print(f"    rev_per_emp_mean: float = 2_000_000    # PLACEHOLDER")
            print(f"    rev_per_emp_median: float = 1_500_000  # PLACEHOLDER")
            print(f"    rev_per_emp_p95: float = 5_000_000     # PLACEHOLDER")
            print(f"    rev_per_emp_p99: float = 10_000_000    # PLACEHOLDER")
            print()
        
        if 'directors_per_company' in self.results:
            s = self.results['directors_per_company']
            print(f"    # Directors per company")
            print(f"    directors_per_co_mean: float = {s.mean:.2f}")
            print(f"    directors_per_co_median: float = {s.median:.1f}")
            print()
        else:
            print(f"    # Directors per company - NO DATA")
            print(f"    directors_per_co_mean: float = 2.5    # PLACEHOLDER")
            print(f"    directors_per_co_median: float = 2.0  # PLACEHOLDER")
            print()
        
        if 'company_age' in self.results:
            s = self.results['company_age']
            print(f"    # Company age (years)")
            print(f"    # Coverage: {self.metadata.age_coverage:.0%}")
            print(f"    company_age_mean: float = {s.mean:.1f}")
            print(f"    company_age_median: float = {s.median:.1f}")
            print()
        
        # Thresholds section
        print("""
# Anomaly detection thresholds
# 'suspicious' = worth flagging for review (p95)
# 'critical' = high confidence anomaly (p99)
ANOMALY_THRESHOLDS = {""")
        
        if 'address_density' in self.results:
            s = self.results['address_density']
            print(f"    'address_density_suspicious': {s.p95:.0f},    # p95 - CALIBRATED")
            print(f"    'address_density_critical': {s.p99:.0f},      # p99 - CALIBRATED")
        else:
            print(f"    'address_density_suspicious': 5,     # PLACEHOLDER")
            print(f"    'address_density_critical': 10,      # PLACEHOLDER")
        
        if 'director_roles' in self.results:
            s = self.results['director_roles']
            print(f"    'director_roles_suspicious': {s.p95:.0f},     # p95 - CALIBRATED")
            print(f"    'director_roles_critical': {s.p99:.0f},       # p99 - CALIBRATED")
        else:
            print(f"    'director_roles_suspicious': 3,      # PLACEHOLDER - conservative")
            print(f"    'director_roles_critical': 6,        # PLACEHOLDER - conservative")
        
        if 'revenue_per_employee' in self.results:
            s = self.results['revenue_per_employee']
            print(f"    'rev_per_emp_suspicious': {s.p95:.0f},   # p95 - CALIBRATED")
            print(f"    'rev_per_emp_critical': {s.p99:.0f},     # p99 - CALIBRATED")
        else:
            print(f"    'rev_per_emp_suspicious': 5_000_000,  # PLACEHOLDER")
            print(f"    'rev_per_emp_critical': 10_000_000,   # PLACEHOLDER")
        
        if 'directors_per_company' in self.results:
            print(f"    'single_director_flag': True,         # Flag single-director companies")
        
        print("}")
        
        # Validation notes
        print(f"""
# ============================================================================
# CALIBRATION NOTES
# ============================================================================
# Sample: {self.metadata.sample_size:,} active Swedish ABs
# Date: {self.metadata.calibration_date}
# Sources: {', '.join(self.metadata.data_sources)}
#
# Coverage gaps:""")
        
        if self.metadata.director_coverage < 0.5:
            print(f"#   - Director data: {self.metadata.director_coverage:.0%} (INCOMPLETE)")
            print(f"#     → Director thresholds are PLACEHOLDERS")
            print(f"#     → Re-run calibration when allabolag enrichment reaches 50%+")
        
        if self.metadata.financial_coverage < 0.3:
            print(f"#   - Financial data: {self.metadata.financial_coverage:.0%} (LOW)")
            print(f"#     → Revenue thresholds may need adjustment")
        
        print(f"#")
        print(f"# Next scheduled recalibration: {self.metadata.next_recalibration}")
        print(f"# ============================================================================")
    
    
    def _get_company_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    
    def close(self):
        self.conn.close()


def main():
    parser = argparse.ArgumentParser(description='Baseline tuning analysis')
    parser.add_argument('--db', required=True, help='Path to SQLite database')
    parser.add_argument('--output', help='Output JSON file for results')
    
    args = parser.parse_args()
    
    if not Path(args.db).exists():
        print(f"Error: Database not found: {args.db}")
        return 1
    
    analyzer = BaselineAnalyzer(args.db)
    analyzer.run_all()
    
    if args.output:
        # Save results with metadata
        output = {
            'metadata': asdict(analyzer.metadata),
            'distributions': {
                name: {
                    'count': s.count,
                    'mean': s.mean,
                    'std': s.std,
                    'median': s.median,
                    'p75': s.p75,
                    'p90': s.p90,
                    'p95': s.p95,
                    'p99': s.p99,
                    'max': s.max,
                }
                for name, s in analyzer.results.items()
            },
            'thresholds': {
                'address_density_suspicious': analyzer.results['address_density'].p95 if 'address_density' in analyzer.results else 5,
                'address_density_critical': analyzer.results['address_density'].p99 if 'address_density' in analyzer.results else 10,
                'director_roles_suspicious': analyzer.results['director_roles'].p95 if 'director_roles' in analyzer.results else 3,
                'director_roles_critical': analyzer.results['director_roles'].p99 if 'director_roles' in analyzer.results else 6,
                'rev_per_emp_suspicious': analyzer.results['revenue_per_employee'].p95 if 'revenue_per_employee' in analyzer.results else 5_000_000,
                'rev_per_emp_critical': analyzer.results['revenue_per_employee'].p99 if 'revenue_per_employee' in analyzer.results else 10_000_000,
            },
            'calibration_status': {
                'address_density': 'CALIBRATED' if 'address_density' in analyzer.results else 'PLACEHOLDER',
                'director_roles': 'CALIBRATED' if 'director_roles' in analyzer.results else 'PLACEHOLDER',
                'revenue_per_employee': 'CALIBRATED' if 'revenue_per_employee' in analyzer.results else 'PLACEHOLDER',
                'directors_per_company': 'CALIBRATED' if 'directors_per_company' in analyzer.results else 'PLACEHOLDER',
            }
        }
        with open(args.output, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to: {args.output}")
    
    analyzer.close()
    return 0


if __name__ == '__main__':
    exit(main())