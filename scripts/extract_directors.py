#!/usr/bin/env python3
"""
Director Extraction Script - Downloads annual reports and extracts directors.

Optimized version that:
1. Uses merged bulk database (skips /organisationer API calls)
2. Focuses on AB companies (556xxx, 559xxx) - ~800K companies
3. Downloads only the MOST RECENT annual report per company
4. Extracts directors via XBRL (preferred) or PDF fallback

Rate limit: 60 req/min = ~2 requests per company (dokumentlista + dokument)
Estimated time: ~800K × 2 req / 60 req/min / 60 / 24 = ~18.5 days
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

from halo.config import settings
from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter
from halo.extraction.xbrl_extractor import XBRLExtractor
from halo.extraction.pdf_extractor import PDFExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limit: 60 req/min = 1 req/sec
REQUEST_DELAY = 1.01


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite database for storing directors."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS directors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orgnr TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            role TEXT,
            report_year INTEGER,
            extraction_method TEXT,
            extracted_at TEXT,
            UNIQUE(orgnr, first_name, last_name, role)
        );

        CREATE TABLE IF NOT EXISTS processed (
            orgnr TEXT PRIMARY KEY,
            status TEXT,
            doc_id TEXT,
            doc_type TEXT,
            report_year INTEGER,
            directors_count INTEGER DEFAULT 0,
            processed_at TEXT,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS progress (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_directors_orgnr ON directors(orgnr);
        CREATE INDEX IF NOT EXISTS idx_processed_status ON processed(status);
    """)
    conn.commit()
    return conn


def get_progress(conn: sqlite3.Connection) -> dict:
    """Get current progress stats."""
    cursor = conn.execute("SELECT status, COUNT(*) FROM processed GROUP BY status")
    stats = {row[0]: row[1] for row in cursor}

    cursor = conn.execute("SELECT COUNT(*) FROM directors")
    directors_count = cursor.fetchone()[0]

    return {
        "completed": stats.get("ok", 0),
        "no_docs": stats.get("no_docs", 0),
        "failed": stats.get("error", 0),
        "directors": directors_count,
    }


def save_directors(conn: sqlite3.Connection, orgnr: str, directors: list,
                   report_year: int, method: str):
    """Save extracted directors to database."""
    now = datetime.utcnow().isoformat()

    for director in directors:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO directors
                (orgnr, first_name, last_name, role, report_year, extraction_method, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                orgnr,
                director.first_name,
                director.last_name,
                director.role,
                report_year,
                method,
                now
            ))
        except Exception as e:
            logger.warning(f"Error saving director for {orgnr}: {e}")


def save_processed(conn: sqlite3.Connection, orgnr: str, status: str,
                   doc_id: str = None, doc_type: str = None,
                   report_year: int = None, directors_count: int = 0,
                   error: str = None):
    """Mark company as processed."""
    conn.execute("""
        INSERT OR REPLACE INTO processed
        (orgnr, status, doc_id, doc_type, report_year, directors_count, processed_at, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        orgnr, status, doc_id, doc_type, report_year, directors_count,
        datetime.utcnow().isoformat(), error
    ))


def get_ab_companies(merged_db: Path, processed_conn: sqlite3.Connection,
                     batch_size: int = 1000):
    """
    Generator yielding AB company org numbers that haven't been processed.

    Focuses on 556xxx and 559xxx prefixes (Aktiebolag).
    """
    # Get already processed
    processed = set()
    cursor = processed_conn.execute("SELECT orgnr FROM processed")
    for row in cursor:
        processed.add(row[0])

    logger.info(f"Already processed: {len(processed):,} companies")

    # Stream from merged database
    source_conn = sqlite3.connect(merged_db)
    offset = 0

    while True:
        cursor = source_conn.execute("""
            SELECT orgnr FROM companies
            WHERE (orgnr LIKE '556%' OR orgnr LIKE '559%')
            ORDER BY orgnr
            LIMIT ? OFFSET ?
        """, (batch_size, offset))

        rows = cursor.fetchall()
        if not rows:
            break

        for row in rows:
            orgnr = row[0]
            if orgnr not in processed:
                yield orgnr

        offset += batch_size

    source_conn.close()


async def rate_limit(last_time: float) -> float:
    """Enforce rate limiting. Returns new timestamp."""
    elapsed = time.time() - last_time
    if elapsed < REQUEST_DELAY:
        await asyncio.sleep(REQUEST_DELAY - elapsed)
    return time.time()


async def extract_directors_from_doc(doc_bytes: bytes, orgnr: str, doc_id: str) -> tuple:
    """
    Extract directors from document bytes (ZIP package).

    Args:
        doc_bytes: ZIP file bytes
        orgnr: Organization number
        doc_id: Document ID

    Returns: (directors_list, extraction_method)
    """
    # Try XBRL first (more accurate) - documents are ZIP packages
    try:
        xbrl = XBRLExtractor()
        result = xbrl.extract_from_zip(doc_bytes, orgnr, doc_id)
        if result and result.directors:
            return result.directors, "xbrl"
    except Exception as e:
        logger.debug(f"XBRL extraction failed for {orgnr}: {e}")

    # Fall back to PDF extraction from ZIP
    try:
        pdf = PDFExtractor()
        result = pdf.extract_from_zip(doc_bytes, orgnr, doc_id)
        if result and result.directors:
            return result.directors, "pdf"
    except Exception as e:
        logger.debug(f"PDF extraction failed for {orgnr}: {e}")

    return [], None


async def run_extraction():
    """Main extraction loop."""
    data_dir = Path(__file__).parent.parent / "data"
    merged_db = data_dir / "companies_merged.db"
    output_db = data_dir / "directors.db"

    if not merged_db.exists():
        logger.error(f"Merged database not found: {merged_db}")
        logger.error("Run import_bulk_files.py and merge_bulk_data.py first")
        return

    if not settings.bolagsverket_client_id or not settings.bolagsverket_client_secret:
        logger.error("Bolagsverket credentials not configured!")
        logger.error("Set BOLAGSVERKET_CLIENT_ID and BOLAGSVERKET_CLIENT_SECRET")
        return

    # Count AB companies
    source_conn = sqlite3.connect(merged_db)
    total = source_conn.execute("""
        SELECT COUNT(*) FROM companies
        WHERE orgnr LIKE '556%' OR orgnr LIKE '559%'
    """).fetchone()[0]
    source_conn.close()

    logger.info(f"Total AB companies: {total:,}")

    conn = init_db(output_db)
    progress = get_progress(conn)

    processed_count = progress["completed"] + progress["no_docs"] + progress["failed"]

    if processed_count > 0:
        logger.info(f"Resuming extraction...")
        logger.info(f"  Completed: {progress['completed']:,}")
        logger.info(f"  No docs: {progress['no_docs']:,}")
        logger.info(f"  Failed: {progress['failed']:,}")
        logger.info(f"  Directors extracted: {progress['directors']:,}")

    remaining = total - processed_count
    # ~2 requests per company
    estimated_days = remaining * 2 * REQUEST_DELAY / 86400

    logger.info(f"Remaining: {remaining:,} companies")
    logger.info(f"Estimated time: {estimated_days:.1f} days")
    logger.info("=" * 60)

    adapter = BolagsverketHVDAdapter()

    try:
        # Test connection
        logger.info("Testing Bolagsverket API connection...")
        if not await adapter.healthcheck():
            logger.error("API healthcheck failed!")
            return
        logger.info("Connection OK")

        last_request_time = 0
        batch_count = 0

        for orgnr in get_ab_companies(merged_db, conn):
            try:
                # === REQUEST 1: Get document list ===
                last_request_time = await rate_limit(last_request_time)
                docs = await adapter.list_annual_reports(orgnr)

                if not docs:
                    save_processed(conn, orgnr, "no_docs")
                    batch_count += 1
                    continue

                # Get most recent report
                docs_sorted = sorted(
                    docs,
                    key=lambda d: d.get("rakenskapsperiod", {}).get("tom", ""),
                    reverse=True
                )
                latest = docs_sorted[0]
                doc_id = latest.get("dokumentId")
                doc_type = latest.get("dokumentTyp", "")

                # Extract year from period
                period = latest.get("rakenskapsperiod", {})
                year_str = period.get("tom", "")[:4]
                report_year = int(year_str) if year_str.isdigit() else None

                if not doc_id:
                    save_processed(conn, orgnr, "no_docs")
                    batch_count += 1
                    continue

                # === REQUEST 2: Download document ===
                last_request_time = await rate_limit(last_request_time)
                doc_bytes = await adapter.download_document(doc_id)

                if not doc_bytes:
                    save_processed(conn, orgnr, "error", error="Empty document")
                    batch_count += 1
                    continue

                # Extract directors from ZIP package
                directors, method = await extract_directors_from_doc(doc_bytes, orgnr, doc_id)

                if directors:
                    save_directors(conn, orgnr, directors, report_year, method)

                save_processed(
                    conn, orgnr, "ok",
                    doc_id=doc_id,
                    doc_type=doc_type,
                    report_year=report_year,
                    directors_count=len(directors)
                )

                batch_count += 1

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Error processing {orgnr}: {error_msg[:100]}")
                save_processed(conn, orgnr, "error", error=error_msg[:500])
                batch_count += 1

                if "429" in error_msg or "rate" in error_msg.lower():
                    logger.warning("Rate limited! Waiting 60 seconds...")
                    await asyncio.sleep(60)

            # Progress update every 50 companies
            if batch_count % 50 == 0:
                conn.commit()
                progress = get_progress(conn)
                total_done = progress["completed"] + progress["no_docs"] + progress["failed"]
                pct = (total_done / total) * 100 if total > 0 else 0

                logger.info(
                    f"Progress: {total_done:,}/{total:,} ({pct:.2f}%) | "
                    f"OK: {progress['completed']:,} | "
                    f"No docs: {progress['no_docs']:,} | "
                    f"Directors: {progress['directors']:,}"
                )

        conn.commit()
        progress = get_progress(conn)

        logger.info("=" * 60)
        logger.info("COMPLETE!")
        logger.info(f"  Processed: {progress['completed'] + progress['no_docs'] + progress['failed']:,}")
        logger.info(f"  With documents: {progress['completed']:,}")
        logger.info(f"  No documents: {progress['no_docs']:,}")
        logger.info(f"  Errors: {progress['failed']:,}")
        logger.info(f"  Directors extracted: {progress['directors']:,}")
        logger.info(f"  Database: {output_db}")

    finally:
        await adapter.close()
        conn.close()


if __name__ == "__main__":
    asyncio.run(run_extraction())
