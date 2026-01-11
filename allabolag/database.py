"""
SQLite database for scraper state and results.

Stores:
- Job queue (orgnrs to scrape)
- Scraped company data
- Request logs for monitoring
- Block events
"""
import sqlite3
import gzip
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
import json
import logging

from .config import StorageConfig

logger = logging.getLogger(__name__)


@dataclass
class ScrapeJob:
    """A job in the scrape queue."""
    orgnr: str
    status: str = "pending"  # pending, in_progress, completed, failed, blocked
    priority: int = 0
    attempts: int = 0
    last_attempt: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class Company:
    """Parsed company data."""
    orgnr: str
    name: str
    legal_form: Optional[str] = None
    status: Optional[str] = None
    registration_date: Optional[str] = None

    # Address
    street_address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    municipality: Optional[str] = None
    county: Optional[str] = None

    # Contact
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    # Business
    sni_code: Optional[str] = None
    sni_description: Optional[str] = None
    purpose: Optional[str] = None

    # Financials (latest year)
    revenue: Optional[int] = None
    profit: Optional[int] = None
    employees: Optional[int] = None
    share_capital: Optional[int] = None

    # Board/Management
    directors: List[Dict[str, Any]] = field(default_factory=list)
    signatories: List[str] = field(default_factory=list)

    # Corporate structure
    parent_company: Optional[str] = None
    num_subsidiaries: Optional[int] = None

    # Meta
    scraped_at: Optional[str] = None
    source_url: Optional[str] = None

    # Raw JSON data for reprocessing
    raw_json: Optional[dict] = None


class ScraperDatabase:
    """SQLite database manager for the scraper."""

    def __init__(self, config: StorageConfig):
        self.config = config
        self.db_path = Path(config.database_path)
        self.html_dir = Path(config.raw_html_dir)

        # Create directories
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if config.store_raw_html:
            self.html_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_connection()
        try:
            conn.executescript("""
                -- Job queue
                CREATE TABLE IF NOT EXISTS jobs (
                    orgnr TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'pending',
                    priority INTEGER DEFAULT 0,
                    attempts INTEGER DEFAULT 0,
                    last_attempt TEXT,
                    error TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC);

                -- Companies
                CREATE TABLE IF NOT EXISTS companies (
                    orgnr TEXT PRIMARY KEY,
                    name TEXT,
                    legal_form TEXT,
                    status TEXT,
                    registration_date TEXT,
                    street_address TEXT,
                    postal_code TEXT,
                    city TEXT,
                    municipality TEXT,
                    county TEXT,
                    phone TEXT,
                    email TEXT,
                    website TEXT,
                    sni_code TEXT,
                    sni_description TEXT,
                    purpose TEXT,
                    revenue INTEGER,
                    profit INTEGER,
                    employees INTEGER,
                    share_capital INTEGER,
                    parent_company TEXT,
                    num_subsidiaries INTEGER,
                    signatories TEXT,
                    raw_json TEXT,
                    scraped_at TEXT,
                    source_url TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_companies_city ON companies(city);
                CREATE INDEX IF NOT EXISTS idx_companies_sni ON companies(sni_code);
                CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(status);

                -- Directors (many-to-many with companies)
                CREATE TABLE IF NOT EXISTS directors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    orgnr TEXT,
                    name TEXT,
                    role TEXT,
                    role_group TEXT,
                    person_type TEXT,
                    person_id TEXT,
                    birth_date TEXT,
                    birth_year INTEGER,
                    FOREIGN KEY (orgnr) REFERENCES companies(orgnr)
                );

                CREATE INDEX IF NOT EXISTS idx_directors_orgnr ON directors(orgnr);
                CREATE INDEX IF NOT EXISTS idx_directors_name ON directors(name);
                CREATE INDEX IF NOT EXISTS idx_directors_person_id ON directors(person_id);

                -- Request log
                CREATE TABLE IF NOT EXISTS request_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    orgnr TEXT,
                    success INTEGER,
                    status_code INTEGER,
                    response_time_ms INTEGER,
                    proxy_session TEXT,
                    error_type TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_request_log_timestamp ON request_log(timestamp);

                -- Block events
                CREATE TABLE IF NOT EXISTS block_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    proxy_session TEXT,
                    status_code INTEGER,
                    error_message TEXT,
                    cooldown_hours INTEGER
                );
            """)
            conn.commit()
            logger.info(f"Database initialized: {self.db_path}")
        finally:
            conn.close()

    def add_jobs(self, orgnrs: List[str], priority: int = 0):
        """Add orgnrs to the job queue."""
        conn = self._get_connection()
        try:
            # Use INSERT OR IGNORE to skip duplicates
            conn.executemany(
                """
                INSERT OR IGNORE INTO jobs (orgnr, priority, created_at)
                VALUES (?, ?, ?)
                """,
                [(orgnr, priority, datetime.utcnow().isoformat()) for orgnr in orgnrs]
            )
            conn.commit()
            logger.info(f"Added {len(orgnrs)} jobs to queue (priority={priority})")
        finally:
            conn.close()

    def get_next_job(self) -> Optional[ScrapeJob]:
        """Get next job to process (highest priority, oldest first)."""
        conn = self._get_connection()
        try:
            # Get next pending job
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'pending'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """
            ).fetchone()

            if not row:
                return None

            # Mark as in_progress
            conn.execute(
                """
                UPDATE jobs
                SET status = 'in_progress',
                    last_attempt = ?,
                    attempts = attempts + 1
                WHERE orgnr = ?
                """,
                (datetime.utcnow().isoformat(), row['orgnr'])
            )
            conn.commit()

            return ScrapeJob(
                orgnr=row['orgnr'],
                status='in_progress',
                priority=row['priority'],
                attempts=row['attempts'] + 1,
                last_attempt=datetime.utcnow().isoformat(),
                error=row['error'],
                created_at=row['created_at']
            )
        finally:
            conn.close()

    def complete_job(self, orgnr: str, success: bool, error: str = None):
        """Mark job as completed or failed."""
        status = 'completed' if success else 'failed'
        conn = self._get_connection()
        try:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, error = ?
                WHERE orgnr = ?
                """,
                (status, error, orgnr)
            )
            conn.commit()
        finally:
            conn.close()

    def mark_blocked(self, orgnr: str):
        """Mark job as blocked (will retry after cooldown)."""
        conn = self._get_connection()
        try:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'blocked'
                WHERE orgnr = ?
                """,
                (orgnr,)
            )
            conn.commit()
        finally:
            conn.close()

    def reset_in_progress(self):
        """Reset all in_progress jobs to pending (for recovery after crash)."""
        conn = self._get_connection()
        try:
            result = conn.execute(
                """
                UPDATE jobs
                SET status = 'pending'
                WHERE status = 'in_progress'
                """
            )
            conn.commit()
            logger.info(f"Reset {result.rowcount} in_progress jobs to pending")
        finally:
            conn.close()

    def reset_blocked(self):
        """Reset blocked jobs to pending (after cooldown)."""
        conn = self._get_connection()
        try:
            result = conn.execute(
                """
                UPDATE jobs
                SET status = 'pending'
                WHERE status = 'blocked'
                """
            )
            conn.commit()
            logger.info(f"Reset {result.rowcount} blocked jobs to pending")
        finally:
            conn.close()

    def get_job_stats(self) -> Dict[str, int]:
        """Get job queue statistics."""
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM jobs
                GROUP BY status
                """
            ).fetchall()
            return {row['status']: row['count'] for row in rows}
        finally:
            conn.close()

    def save_company(self, company, raw_html: bytes = None):
        """Save parsed company data. Accepts either parser.Company or database.Company."""
        conn = self._get_connection()
        try:
            # Serialize JSON fields
            signatories_json = json.dumps(getattr(company, 'signatories', []) or [])
            raw_json_str = json.dumps(getattr(company, 'raw_json', None)) if getattr(company, 'raw_json', None) else None

            # Insert/update company
            conn.execute(
                """
                INSERT OR REPLACE INTO companies (
                    orgnr, name, legal_form, status, registration_date,
                    street_address, postal_code, city, municipality, county,
                    phone, email, website, sni_code, sni_description, purpose,
                    revenue, profit, employees, share_capital,
                    parent_company, num_subsidiaries, signatories, raw_json,
                    scraped_at, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company.orgnr, company.name, company.legal_form, company.status,
                    company.registration_date, company.street_address, company.postal_code,
                    company.city, company.municipality, company.county, company.phone,
                    company.email, company.website, company.sni_code, company.sni_description,
                    getattr(company, 'purpose', None),
                    company.revenue, company.profit, company.employees,
                    getattr(company, 'share_capital', None),
                    getattr(company, 'parent_company', None),
                    getattr(company, 'num_subsidiaries', None),
                    signatories_json, raw_json_str,
                    company.scraped_at, company.source_url
                )
            )

            # Delete old directors and insert new
            conn.execute("DELETE FROM directors WHERE orgnr = ?", (company.orgnr,))
            for director in (company.directors or []):
                conn.execute(
                    """
                    INSERT INTO directors (orgnr, name, role, role_group, person_type, person_id, birth_date, birth_year)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company.orgnr,
                        director.get('name'),
                        director.get('role'),
                        director.get('group'),
                        director.get('type'),
                        director.get('id'),
                        director.get('birth_date'),
                        director.get('birth_year')
                    )
                )

            conn.commit()

            # Save raw HTML if configured
            if raw_html and self.config.store_raw_html:
                self._save_raw_html(company.orgnr, raw_html)

        finally:
            conn.close()

    def _save_raw_html(self, orgnr: str, html: bytes):
        """Save raw HTML to disk."""
        # Organize by first 2 digits of orgnr
        subdir = self.html_dir / orgnr[:2]
        subdir.mkdir(exist_ok=True)

        filepath = subdir / f"{orgnr}.html"

        if self.config.compress_html:
            filepath = filepath.with_suffix('.html.gz')
            with gzip.open(filepath, 'wb') as f:
                f.write(html)
        else:
            with open(filepath, 'wb') as f:
                f.write(html)

    def log_request(self, orgnr: str, success: bool, status_code: int,
                    response_time_ms: int, proxy_session: str,
                    error_type: str = None):
        """Log a request for monitoring."""
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO request_log
                (orgnr, success, status_code, response_time_ms, proxy_session, error_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (orgnr, int(success), status_code, response_time_ms, proxy_session, error_type)
            )
            conn.commit()
        finally:
            conn.close()

    def log_block_event(self, proxy_session: str, status_code: int,
                        error_message: str, cooldown_hours: int):
        """Log a block event."""
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO block_events
                (proxy_session, status_code, error_message, cooldown_hours)
                VALUES (?, ?, ?, ?)
                """,
                (proxy_session, status_code, error_message, cooldown_hours)
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_error_rate(self, minutes: int = 60) -> float:
        """Get error rate over the last N minutes."""
        conn = self._get_connection()
        try:
            cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors
                FROM request_log
                WHERE timestamp > ?
                """,
                (cutoff,)
            ).fetchone()

            total = row['total'] or 0
            errors = row['errors'] or 0

            return errors / total if total > 0 else 0.0
        finally:
            conn.close()

    def get_requests_today(self) -> int:
        """Get number of requests made today."""
        conn = self._get_connection()
        try:
            today_start = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()

            row = conn.execute(
                """
                SELECT COUNT(*) as count
                FROM request_log
                WHERE timestamp > ?
                """,
                (today_start,)
            ).fetchone()

            return row['count'] or 0
        finally:
            conn.close()

    def get_company(self, orgnr: str) -> Optional[Company]:
        """Get a scraped company by orgnr."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM companies WHERE orgnr = ?",
                (orgnr,)
            ).fetchone()

            if not row:
                return None

            # Get directors
            directors = conn.execute(
                "SELECT name, role, birth_year FROM directors WHERE orgnr = ?",
                (orgnr,)
            ).fetchall()

            return Company(
                orgnr=row['orgnr'],
                name=row['name'],
                legal_form=row['legal_form'],
                status=row['status'],
                registration_date=row['registration_date'],
                street_address=row['street_address'],
                postal_code=row['postal_code'],
                city=row['city'],
                municipality=row['municipality'],
                county=row['county'],
                phone=row['phone'],
                email=row['email'],
                website=row['website'],
                sni_code=row['sni_code'],
                sni_description=row['sni_description'],
                revenue=row['revenue'],
                profit=row['profit'],
                employees=row['employees'],
                directors=[dict(d) for d in directors],
                scraped_at=row['scraped_at'],
                source_url=row['source_url']
            )
        finally:
            conn.close()
