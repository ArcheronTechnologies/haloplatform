"""
Two-phase orchestration loop for the scraper.

Phase 1: Scrape companies, collect person IDs
Phase 2: Scrape person pages for complete profiles and network discovery
"""

import asyncio
import logging
import json
import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import quote

from allabolag_scraper.config import ScraperConfig
from allabolag_scraper.db.connection import init_db
from allabolag_scraper.scraper.worker import Worker, FetchResult, FetchType
from allabolag_scraper.scraper.parser_company import parse_company, Company as ParsedCompany
from allabolag_scraper.scraper.parser_person import parse_person_page, PersonProfile

logger = logging.getLogger(__name__)


def split_name(full_name: str) -> Tuple[Optional[str], Optional[str]]:
    """Split full name into first_name and last_name for matching."""
    if not full_name:
        return None, None
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0], None
    return parts[0], ' '.join(parts[1:])


class Orchestrator:
    """
    Manages two-phase scraping:
    1. Company pages -> companies, persons (basic), roles
    2. Person pages -> complete person profiles, connections, additional companies
    """

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.conn = init_db(config)

        # Stats per phase
        self.company_stats = {'processed': 0, 'success': 0, 'failed': 0, 'not_found': 0}
        self.person_stats = {'processed': 0, 'success': 0, 'failed': 0, 'not_found': 0}
        self.start_time: Optional[datetime] = None

    # ========================
    # PHASE 1: Company Scraping
    # ========================

    def get_pending_companies(self, size: int) -> List[str]:
        """Get batch of pending company org numbers."""
        cursor = self.conn.execute("""
            SELECT org_nr FROM company_scrape_queue
            WHERE status = 'pending'
            LIMIT ?
        """, (size,))
        org_nrs = [row[0] for row in cursor.fetchall()]

        if org_nrs:
            placeholders = ','.join('?' * len(org_nrs))
            self.conn.execute(f"""
                UPDATE company_scrape_queue
                SET status = 'in_progress', last_attempt_at = ?
                WHERE org_nr IN ({placeholders})
            """, [datetime.utcnow().isoformat()] + org_nrs)
            self.conn.commit()

        return org_nrs

    def save_company(self, parsed: ParsedCompany):
        """Save parsed company and queue discovered persons for Phase 2."""
        now = datetime.utcnow().isoformat()

        # Upsert company
        self.conn.execute("""
            INSERT OR REPLACE INTO companies
            (org_nr, name, legal_name, status, status_date, registration_date,
             company_type, sni_code, sni_name, municipality, county,
             parent_org_nr, parent_name, revenue, profit, employees,
             allabolag_company_id, scraped_at, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            parsed.org_nr,
            parsed.name,
            parsed.legal_name,
            parsed.status,
            parsed.status_date.isoformat() if parsed.status_date else None,
            parsed.registration_date.isoformat() if parsed.registration_date else None,
            parsed.company_type,
            parsed.sni_code,
            parsed.sni_name,
            parsed.municipality,
            parsed.county,
            parsed.parent_org_nr,
            parsed.parent_name,
            parsed.revenue,
            parsed.profit,
            parsed.employees,
            parsed.allabolag_company_id,
            now,
            json.dumps(parsed.raw_json, ensure_ascii=False)
        ))

        # Process each person discovered
        for person_data in parsed.persons:
            if not person_data.allabolag_id:
                continue

            # Check if person exists
            cursor = self.conn.execute(
                "SELECT id FROM persons WHERE allabolag_person_id = ?",
                (person_data.allabolag_id,)
            )
            row = cursor.fetchone()

            if row:
                person_id = row[0]
            else:
                # Insert new person with split name for matching
                first_name, last_name = split_name(person_data.name)
                cursor = self.conn.execute("""
                    INSERT INTO persons (allabolag_person_id, name, first_name, last_name, birth_date, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    person_data.allabolag_id,
                    person_data.name,
                    first_name,
                    last_name,
                    person_data.birth_date.isoformat() if person_data.birth_date else None,
                    now
                ))
                person_id = cursor.lastrowid

            # Upsert role
            self.conn.execute("""
                INSERT OR REPLACE INTO roles
                (company_org_nr, person_id, role_type, role_group, discovered_from, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                parsed.org_nr,
                person_id,
                person_data.role,
                person_data.role_group,
                'company_page',
                now
            ))

            # Queue person for Phase 2 scraping (if not already queued/scraped)
            name_slug = person_data.name.lower().replace(' ', '-')
            self.conn.execute("""
                INSERT OR IGNORE INTO person_scrape_queue
                (allabolag_person_id, name, name_slug, discovered_from_company, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                person_data.allabolag_id,
                person_data.name,
                quote(name_slug, safe='-'),
                parsed.org_nr,
                now
            ))

        self.conn.commit()

    def mark_company_completed(self, org_nr: str):
        self.conn.execute(
            "UPDATE company_scrape_queue SET status = 'completed' WHERE org_nr = ?",
            (org_nr,)
        )
        self.conn.commit()

    def mark_company_failed(self, org_nr: str, error: str):
        self.conn.execute("""
            UPDATE company_scrape_queue
            SET status = 'pending', attempts = attempts + 1, error_message = ?
            WHERE org_nr = ?
        """, (error, org_nr))
        self.conn.commit()

    async def process_company_result(self, result: FetchResult):
        """Process a company fetch result."""
        if result.status_code == 200 and result.html:
            parsed = parse_company(result.html)
            if parsed:
                self.save_company(parsed)
                self.mark_company_completed(result.identifier)
                self.company_stats['success'] += 1
                logger.info(f"[OK] {result.identifier}: {parsed.name} ({len(parsed.persons)} persons)")
            else:
                self.mark_company_failed(result.identifier, "Parse failed")
                self.company_stats['failed'] += 1
                logger.warning(f"[PARSE FAIL] {result.identifier}")
        elif result.status_code == 404:
            self.mark_company_completed(result.identifier)
            self.company_stats['not_found'] += 1
            logger.debug(f"[404] {result.identifier}")
        else:
            self.mark_company_failed(result.identifier, result.error or "Unknown")
            self.company_stats['failed'] += 1
            logger.warning(f"[FAIL] {result.identifier}: {result.error}")

        self.company_stats['processed'] += 1

    # ========================
    # PHASE 2: Person Scraping
    # ========================

    def get_pending_persons(self, size: int) -> List[Tuple[str, str, str]]:
        """Get batch of pending persons: (person_id, name, name_slug)."""
        cursor = self.conn.execute("""
            SELECT allabolag_person_id, name, name_slug
            FROM person_scrape_queue
            WHERE status = 'pending'
            LIMIT ?
        """, (size,))
        persons = [(row[0], row[1], row[2]) for row in cursor.fetchall()]

        if persons:
            person_ids = [p[0] for p in persons]
            placeholders = ','.join('?' * len(person_ids))
            self.conn.execute(f"""
                UPDATE person_scrape_queue
                SET status = 'in_progress', last_attempt_at = ?
                WHERE allabolag_person_id IN ({placeholders})
            """, [datetime.utcnow().isoformat()] + person_ids)
            self.conn.commit()

        return persons

    def save_person(self, profile: PersonProfile) -> int:
        """Save complete person profile. Returns number of new companies discovered."""
        now = datetime.utcnow().isoformat()
        first_name, last_name = split_name(profile.name)

        # Update person with full data
        self.conn.execute("""
            UPDATE persons SET
                name = ?,
                first_name = ?,
                last_name = ?,
                birth_date = ?,
                year_of_birth = ?,
                age = ?,
                gender = ?,
                person_page_scraped_at = ?,
                person_page_raw_json = ?,
                updated_at = ?
            WHERE allabolag_person_id = ?
        """, (
            profile.name,
            first_name,
            last_name,
            profile.birth_date.isoformat() if profile.birth_date else None,
            profile.year_of_birth,
            profile.age,
            profile.gender,
            now,
            json.dumps(profile.raw_json, ensure_ascii=False),
            now,
            profile.allabolag_person_id
        ))

        # Get person ID
        cursor = self.conn.execute(
            "SELECT id FROM persons WHERE allabolag_person_id = ?",
            (profile.allabolag_person_id,)
        )
        row = cursor.fetchone()
        if not row:
            return 0
        person_id = row[0]

        # Process roles (may include companies we haven't seen yet)
        new_companies = 0
        for role in profile.roles:
            if not role.company_org_nr:
                continue

            # Check if company exists
            cursor = self.conn.execute(
                "SELECT org_nr FROM companies WHERE org_nr = ?",
                (role.company_org_nr,)
            )
            if not cursor.fetchone():
                # Create placeholder company entry (foreign key requires it)
                self.conn.execute("""
                    INSERT OR IGNORE INTO companies
                    (org_nr, name, scraped_at, raw_json)
                    VALUES (?, ?, ?, '{}')
                """, (role.company_org_nr, role.company_name or 'Unknown', now))

                # Queue for full scrape
                self.conn.execute("""
                    INSERT OR IGNORE INTO company_scrape_queue (org_nr, created_at)
                    VALUES (?, ?)
                """, (role.company_org_nr, now))
                new_companies += 1

            # Upsert role
            self.conn.execute("""
                INSERT OR REPLACE INTO roles
                (company_org_nr, person_id, role_type, role_group, discovered_from, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                role.company_org_nr,
                person_id,
                role.role,
                'Unknown',
                'person_page',
                now
            ))

        # Process connections (other persons)
        for conn_data in profile.connections:
            if not conn_data.person_id:
                continue

            # Ensure connected person exists
            cursor = self.conn.execute(
                "SELECT id FROM persons WHERE allabolag_person_id = ?",
                (conn_data.person_id,)
            )
            row = cursor.fetchone()

            if row:
                connected_person_id = row[0]
            else:
                # Create placeholder person with split name
                first_name, last_name = split_name(conn_data.name)
                cursor = self.conn.execute("""
                    INSERT INTO persons (allabolag_person_id, name, first_name, last_name, gender, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (conn_data.person_id, conn_data.name, first_name, last_name, conn_data.gender, now))
                connected_person_id = cursor.lastrowid

                # Queue for scraping
                name_slug = conn_data.name.lower().replace(' ', '-')
                self.conn.execute("""
                    INSERT OR IGNORE INTO person_scrape_queue
                    (allabolag_person_id, name, name_slug, created_at)
                    VALUES (?, ?, ?, ?)
                """, (conn_data.person_id, conn_data.name, quote(name_slug, safe='-'), now))

            # Record connection
            self.conn.execute("""
                INSERT OR IGNORE INTO person_connections
                (person_id, connected_person_id, num_shared_companies, discovered_at)
                VALUES (?, ?, ?, ?)
            """, (person_id, connected_person_id, conn_data.num_shared_companies, now))

        self.conn.commit()
        return new_companies

    def mark_person_completed(self, person_id: str):
        self.conn.execute(
            "UPDATE person_scrape_queue SET status = 'completed' WHERE allabolag_person_id = ?",
            (person_id,)
        )
        self.conn.commit()

    def mark_person_failed(self, person_id: str, error: str):
        self.conn.execute("""
            UPDATE person_scrape_queue
            SET status = 'pending', attempts = attempts + 1, error_message = ?
            WHERE allabolag_person_id = ?
        """, (error, person_id))
        self.conn.commit()

    async def process_person_result(self, result: FetchResult, name: str):
        """Process a person fetch result."""
        if result.status_code == 200 and result.html:
            profile = parse_person_page(result.html)
            if profile:
                new_companies = self.save_person(profile)
                self.mark_person_completed(result.identifier)
                self.person_stats['success'] += 1
                logger.info(
                    f"[OK] {profile.name}: {len(profile.roles)} roles, "
                    f"{len(profile.connections)} connections, {new_companies} new companies"
                )
            else:
                self.mark_person_failed(result.identifier, "Parse failed")
                self.person_stats['failed'] += 1
                logger.warning(f"[PARSE FAIL] Person {result.identifier}")
        elif result.status_code == 404:
            self.mark_person_completed(result.identifier)
            self.person_stats['not_found'] += 1
            logger.debug(f"[404] Person {result.identifier}")
        else:
            self.mark_person_failed(result.identifier, result.error or "Unknown")
            self.person_stats['failed'] += 1
            logger.warning(f"[FAIL] Person {result.identifier}: {result.error}")

        self.person_stats['processed'] += 1

    # ========================
    # Stats
    # ========================

    def get_queue_stats(self) -> dict:
        """Get current queue statistics."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM company_scrape_queue WHERE status = 'pending'"
        )
        company_pending = cursor.fetchone()[0]

        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM person_scrape_queue WHERE status = 'pending'"
        )
        person_pending = cursor.fetchone()[0]

        return {
            'company_pending': company_pending,
            'person_pending': person_pending
        }

    def print_stats(self, phase: str):
        """Print current progress stats."""
        elapsed = datetime.now() - self.start_time
        minutes = max(elapsed.total_seconds() / 60, 0.1)

        if phase == 'company':
            stats = self.company_stats
        else:
            stats = self.person_stats

        rate = stats['processed'] / minutes
        logger.info(
            f"[{phase.upper()}] {stats['processed']} processed, "
            f"{stats['success']} OK, {stats['not_found']} 404, {stats['failed']} failed | "
            f"{rate:.1f}/min"
        )

    # ========================
    # Main Run Methods
    # ========================

    async def run_phase1_companies(self):
        """Phase 1: Scrape all pending companies."""
        logger.info("=" * 50)
        logger.info("PHASE 1: Company Scraping")
        logger.info("=" * 50)

        async with Worker(self.config) as worker:
            while True:
                batch = self.get_pending_companies(self.config.batch_size)

                if not batch:
                    logger.info("Phase 1 complete: No more pending companies")
                    break

                for org_nr in batch:
                    result = await worker.fetch_company(org_nr)
                    await self.process_company_result(result)
                    await worker.delay()

                    if self.company_stats['processed'] % self.config.checkpoint_interval == 0:
                        self.print_stats('company')

        self.print_stats('company')

    async def run_phase2_persons(self):
        """Phase 2: Scrape all pending persons."""
        logger.info("=" * 50)
        logger.info("PHASE 2: Person Scraping")
        logger.info("=" * 50)

        async with Worker(self.config) as worker:
            while True:
                batch = self.get_pending_persons(self.config.batch_size)

                if not batch:
                    logger.info("Phase 2 complete: No more pending persons")
                    break

                for person_id, name, _ in batch:
                    result = await worker.fetch_person(name, person_id)
                    await self.process_person_result(result, name)
                    await worker.delay()

                    if self.person_stats['processed'] % self.config.checkpoint_interval == 0:
                        self.print_stats('person')

        self.print_stats('person')

    async def run_interleaved(self):
        """
        Run both phases concurrently - process companies and persons as they become available.
        More efficient than sequential phases.
        """
        logger.info("=" * 50)
        logger.info("INTERLEAVED MODE: Companies + Persons")
        logger.info("=" * 50)

        async with Worker(self.config) as worker:
            companies_done = False
            persons_done = False

            while not (companies_done and persons_done):
                # Get pending counts
                stats = self.get_queue_stats()
                company_pending = stats['company_pending']
                person_pending = stats['person_pending']

                # Process a company if available
                if company_pending > 0:
                    batch = self.get_pending_companies(1)
                    if batch:
                        org_nr = batch[0]
                        result = await worker.fetch_company(org_nr)
                        await self.process_company_result(result)
                        await worker.delay()

                        if self.company_stats['processed'] % self.config.checkpoint_interval == 0:
                            self.print_stats('company')
                else:
                    companies_done = True

                # Process a person if available (interleave)
                stats = self.get_queue_stats()
                if stats['person_pending'] > 0:
                    persons_done = False  # New persons may have been discovered
                    batch = self.get_pending_persons(1)
                    if batch:
                        person_id, name, _ = batch[0]
                        result = await worker.fetch_person(name, person_id)
                        await self.process_person_result(result, name)
                        await worker.delay()

                        if self.person_stats['processed'] % self.config.checkpoint_interval == 0:
                            self.print_stats('person')
                elif companies_done:
                    persons_done = True

                # Check for newly discovered companies from person pages
                stats = self.get_queue_stats()
                if stats['company_pending'] > 0:
                    companies_done = False

        self.print_stats('company')
        self.print_stats('person')

    async def run(self, phase: str = 'all'):
        """
        Main run method.

        Args:
            phase: 'companies', 'persons', 'interleaved', or 'all' (default)
        """
        self.start_time = datetime.now()

        stats = self.get_queue_stats()
        logger.info(f"Queue: {stats['company_pending']} companies, {stats['person_pending']} persons pending")

        if phase == 'interleaved':
            await self.run_interleaved()
        elif phase in ('all', 'companies'):
            await self.run_phase1_companies()
            if phase == 'all':
                await self.run_phase2_persons()
        elif phase == 'persons':
            await self.run_phase2_persons()

        # Check if new companies were discovered during person scraping
        final_stats = self.get_queue_stats()
        if final_stats['company_pending'] > 0:
            logger.info(
                f"Note: {final_stats['company_pending']} new companies discovered "
                f"during person scraping. Run again to scrape them."
            )

        logger.info("Scraper finished")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
