#!/usr/bin/env python3
"""
Bolagsverket Full Enrichment - ALL 3 ENDPOINTS

Enriches ALL org numbers with:
1. /organisationer - Basic company data
2. /dokumentlista - List of annual reports
3. /dokument/{id} - Download XBRL/PDF annual reports and extract directors

Uses the existing extraction pipeline:
- halo/extraction/xbrl_extractor.py - iXBRL parsing with proper namespaces
- halo/extraction/pdf_extractor.py - PDF fallback using PyMuPDF

Rate limit: 50 requests per 60 seconds
We use: 1 request every 1.5 seconds (40/minute)

Each company = 2-3 requests (company + doc list + maybe 1 download)
Estimated: 644K * 3 * 1.5s = ~33 days

Output: data/bolagsverket_enriched.db (SQLite)
"""

import asyncio
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter
from halo.config import settings
from halo.extraction.xbrl_extractor import XBRLExtractor
from halo.extraction.pdf_extractor import PDFExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# RATE LIMIT: 60 req/min = 1 req/sec (with tiny margin)
REQUEST_DELAY = 1.01


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite database for storing enriched data."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            orgnr TEXT PRIMARY KEY,
            name TEXT,
            legal_form TEXT,
            status TEXT,
            registration_date TEXT,
            address_street TEXT,
            address_postal_code TEXT,
            address_city TEXT,
            sni_codes TEXT,
            purpose TEXT,
            raw_json TEXT,
            enriched_at TEXT
        );

        CREATE TABLE IF NOT EXISTS annual_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orgnr TEXT,
            dokument_id TEXT UNIQUE,
            dokument_typ TEXT,
            rakenskapsperiod_from TEXT,
            rakenskapsperiod_tom TEXT,
            inlamnad_datum TEXT,
            downloaded INTEGER DEFAULT 0,
            raw_json TEXT,
            FOREIGN KEY (orgnr) REFERENCES companies(orgnr)
        );

        CREATE TABLE IF NOT EXISTS directors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orgnr TEXT,
            dokument_id TEXT,
            first_name TEXT,
            last_name TEXT,
            full_name TEXT,
            role TEXT,
            role_normalized TEXT,
            confidence REAL,
            extraction_method TEXT,
            source_field TEXT,
            raw_data TEXT,
            FOREIGN KEY (orgnr) REFERENCES companies(orgnr)
        );

        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_index INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            docs_downloaded INTEGER DEFAULT 0,
            directors_extracted INTEGER DEFAULT 0,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS failures (
            orgnr TEXT PRIMARY KEY,
            error TEXT,
            attempts INTEGER DEFAULT 1,
            last_attempt TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_companies_enriched ON companies(enriched_at);
        CREATE INDEX IF NOT EXISTS idx_reports_orgnr ON annual_reports(orgnr);
        CREATE INDEX IF NOT EXISTS idx_directors_orgnr ON directors(orgnr);
        CREATE INDEX IF NOT EXISTS idx_directors_fullname ON directors(full_name);
        CREATE INDEX IF NOT EXISTS idx_directors_lastname ON directors(last_name);
    """)
    conn.commit()
    return conn


def get_progress(conn: sqlite3.Connection) -> dict:
    """Get current progress."""
    row = conn.execute("SELECT * FROM progress WHERE id = 1").fetchone()
    if row:
        return {
            "last_index": row[1],
            "total": row[2],
            "completed": row[3],
            "failed": row[4],
            "docs_downloaded": row[5],
            "directors_extracted": row[6],
        }
    return {"last_index": 0, "total": 0, "completed": 0, "failed": 0,
            "docs_downloaded": 0, "directors_extracted": 0}


def save_progress(conn: sqlite3.Connection, last_index: int, total: int,
                  completed: int, failed: int, docs_downloaded: int, directors_extracted: int):
    """Save progress checkpoint."""
    conn.execute("""
        INSERT OR REPLACE INTO progress
        (id, last_index, total, completed, failed, docs_downloaded, directors_extracted, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?)
    """, (last_index, total, completed, failed, docs_downloaded, directors_extracted,
          datetime.now(timezone.utc).isoformat()))
    conn.commit()


def save_company(conn: sqlite3.Connection, orgnr: str, data: dict):
    """Save enriched company data."""
    org_namn = data.get("organisationsnamn", {})
    namn_lista = org_namn.get("organisationsnamnLista", [])
    name = ""
    for namn in namn_lista:
        if namn.get("organisationsnamntyp", {}).get("kod") == "FORETAGSNAMN":
            name = namn.get("namn", "")
            break
    if not name and namn_lista:
        name = namn_lista[0].get("namn", "")

    legal_form = data.get("juridiskForm", {}).get("beskrivning", "")
    status = data.get("status", {}).get("beskrivning", "")

    org_datum = data.get("organisationsdatum", {})
    registration_date = org_datum.get("registreringsdatum", "")

    post_addr = data.get("postadressOrganisation", {}).get("postadress", {})
    address_street = post_addr.get("utdelningsadress", "")
    address_postal_code = post_addr.get("postnummer", "")
    address_city = post_addr.get("postort", "")

    naringsgren = data.get("naringsgrenOrganisation", {})
    sni_list = naringsgren.get("sni", [])
    sni_codes = json.dumps([s for s in sni_list if s.get("kod", "").strip()])

    verks = data.get("verksamhetsbeskrivning", {})
    purpose = verks.get("beskrivning", "") if verks else ""

    conn.execute("""
        INSERT OR REPLACE INTO companies
        (orgnr, name, legal_form, status, registration_date,
         address_street, address_postal_code, address_city,
         sni_codes, purpose, raw_json, enriched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        orgnr, name, legal_form, status, registration_date,
        address_street, address_postal_code, address_city,
        sni_codes, purpose, json.dumps(data, ensure_ascii=False),
        datetime.now(timezone.utc).isoformat()
    ))


def save_annual_reports(conn: sqlite3.Connection, orgnr: str, documents: List[dict]):
    """Save annual report metadata."""
    for doc in documents:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO annual_reports
                (orgnr, dokument_id, dokument_typ, rakenskapsperiod_from,
                 rakenskapsperiod_tom, inlamnad_datum, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                orgnr,
                doc.get("dokumentId", ""),
                doc.get("dokumentTyp", {}).get("kod", ""),
                doc.get("rakenskapsperiod", {}).get("periodFran", ""),
                doc.get("rakenskapsperiod", {}).get("periodTill", ""),
                doc.get("inlamnadDatum", ""),
                json.dumps(doc, ensure_ascii=False),
            ))
        except sqlite3.IntegrityError:
            pass  # Already exists


def save_directors_from_result(conn: sqlite3.Connection, orgnr: str, dokument_id: str,
                               extraction_result) -> int:
    """Save extracted directors from ExtractionResult."""
    count = 0
    for director in extraction_result.directors:
        conn.execute("""
            INSERT INTO directors
            (orgnr, dokument_id, first_name, last_name, full_name, role, role_normalized,
             confidence, extraction_method, source_field, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            orgnr,
            dokument_id,
            director.first_name,
            director.last_name,
            director.full_name,
            director.role,
            director.role_normalized,
            director.confidence,
            extraction_result.extraction_method,
            director.source_field,
            json.dumps({
                "first_name": director.first_name,
                "last_name": director.last_name,
                "role": director.role,
                "role_normalized": director.role_normalized,
                "confidence": director.confidence,
            }, ensure_ascii=False),
        ))
        count += 1
    return count


def save_failure(conn: sqlite3.Connection, orgnr: str, error: str):
    """Record a failed enrichment."""
    conn.execute("""
        INSERT INTO failures (orgnr, error, attempts, last_attempt)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(orgnr) DO UPDATE SET
            attempts = attempts + 1,
            error = excluded.error,
            last_attempt = excluded.last_attempt
    """, (orgnr, error, datetime.now(timezone.utc).isoformat()))


# Initialize extractors (used for document processing)
xbrl_extractor = XBRLExtractor(min_confidence=0.5)
pdf_extractor = PDFExtractor(min_confidence=0.5)


def extract_directors_from_document(doc_content: bytes, orgnr: str, dokument_id: str):
    """
    Extract directors from annual report document using the proper extraction pipeline.

    Tries XBRL extraction first (for iXBRL documents), falls back to PDF extraction.

    Returns:
        ExtractionResult with directors, or None if extraction failed
    """
    # Try XBRL extraction first (handles ZIP files with XHTML/XML)
    result = xbrl_extractor.extract_from_zip(doc_content, orgnr, dokument_id)

    if result.directors:
        logger.debug(f"XBRL extracted {len(result.directors)} directors for {orgnr}")
        return result

    # Fall back to PDF extraction
    logger.debug(f"XBRL empty, trying PDF fallback for {orgnr}")
    result = pdf_extractor.extract_from_zip(doc_content, orgnr, dokument_id)

    if result.directors:
        logger.debug(f"PDF extracted {len(result.directors)} directors for {orgnr}")

    return result


async def rate_limited_request(last_request_time: float) -> float:
    """Ensure rate limiting between requests. Returns new last_request_time."""
    elapsed = time.time() - last_request_time
    if elapsed < REQUEST_DELAY:
        await asyncio.sleep(REQUEST_DELAY - elapsed)
    return time.time()


def is_bolagsverket_registered(orgnr: str) -> bool:
    """
    Check if an org number is likely registered with Bolagsverket.

    Bolagsverket tracks registered companies, NOT:
    - Enskild firma (sole proprietorships) - personnummer-based
    - Foreign entities not registered in Sweden

    Org number prefixes Bolagsverket DOES track:
    - 5562-5569, 5590-5599: Aktiebolag (limited companies)
    - 502x: Handelsbolag/Kommanditbolag
    - 716x-717x, 769x: Bostadsrättsföreningar
    - 802x: Ekonomiska föreningar
    - 857x: Bankaktiebolag, försäkringsbolag
    - 916x-919x, 934x: Stiftelser
    - 969x: Utländska filialer (foreign branches)
    - And others with 10-digit org numbers starting with valid prefixes

    NOT tracked (return False):
    - 0xxx-09xx: Various (some are tracked, many aren't)
    - 19xx, 20xx: Personnummer-based (Enskild firma)
    """
    if not orgnr or len(orgnr) < 4:
        return False

    prefix2 = orgnr[:2]
    prefix3 = orgnr[:3]
    prefix4 = orgnr[:4]

    # Skip personnummer-based org numbers (Enskild firma)
    if prefix2 in ('19', '20'):
        return False

    # Skip 00xx-09xx range (mostly not in Bolagsverket)
    if orgnr[0] == '0':
        return False

    # Known Bolagsverket-registered prefixes
    if prefix3 in ('556', '559'):  # Aktiebolag
        return True
    if prefix3 in ('502', '516', '517'):  # Handelsbolag
        return True
    if prefix3 in ('716', '717', '769'):  # Bostadsrättsföreningar
        return True
    if prefix3 in ('802', '822', '835', '857'):  # Föreningar, banker
        return True
    if prefix3 in ('916', '917', '918', '919', '934'):  # Stiftelser
        return True
    if prefix3 in ('969',):  # Utländska filialer
        return True
    if prefix4 in ('7164', '7179', '7696', '8024', '8025'):  # Other registered
        return True

    # Default: try it (Bolagsverket will return 400 if not found)
    # But for efficiency, skip anything that looks like personnummer
    if prefix2.isdigit() and int(prefix2) < 30:
        return False

    return True


def get_orgnrs_from_scb(scb_db_path: Path, enriched_conn: sqlite3.Connection, batch_size: int = 1000):
    """
    Generator that yields org numbers from SCB database that haven't been enriched yet.
    Memory efficient - doesn't load all 1.3M orgnrs at once.
    Only yields org numbers that Bolagsverket is likely to have data for.
    """
    scb_conn = sqlite3.connect(scb_db_path)

    # Get already enriched orgnrs
    enriched = set()
    cursor = enriched_conn.execute("SELECT orgnr FROM companies")
    for row in cursor:
        enriched.add(row[0])

    # Get failed orgnrs with too many attempts (skip them)
    cursor = enriched_conn.execute("SELECT orgnr FROM failures WHERE attempts >= 3")
    for row in cursor:
        enriched.add(row[0])

    logger.info(f"Already processed: {len(enriched):,} orgnrs")

    # Stream orgnrs from SCB database
    offset = 0
    skipped_not_registered = 0
    while True:
        cursor = scb_conn.execute(
            "SELECT orgnr FROM companies ORDER BY orgnr LIMIT ? OFFSET ?",
            (batch_size, offset)
        )
        rows = cursor.fetchall()
        if not rows:
            break

        for row in rows:
            orgnr = row[0]
            if orgnr in enriched:
                continue
            if not is_bolagsverket_registered(orgnr):
                skipped_not_registered += 1
                continue
            yield orgnr

        offset += batch_size

    logger.info(f"Skipped {skipped_not_registered:,} orgnrs not in Bolagsverket (Enskild firma, etc.)")
    scb_conn.close()


async def enrich_all():
    """Enrich all org numbers from SCB with Bolagsverket data - ALL 3 ENDPOINTS."""

    data_dir = Path(__file__).parent.parent / "data"
    scb_db_path = data_dir / "scb_registry.db"
    db_path = data_dir / "bolagsverket_enriched.db"

    if not scb_db_path.exists():
        logger.error(f"SCB database not found: {scb_db_path}")
        logger.error("Run scb_full_pull.py first")
        return

    if not settings.bolagsverket_client_id or not settings.bolagsverket_client_secret:
        logger.error("Bolagsverket credentials not configured!")
        logger.error("Set BOLAGSVERKET_CLIENT_ID and BOLAGSVERKET_CLIENT_SECRET")
        return

    # Get total count from SCB database
    scb_conn = sqlite3.connect(scb_db_path)
    total = scb_conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    scb_conn.close()
    logger.info(f"Total org numbers in SCB: {total:,}")

    conn = init_db(db_path)

    progress = get_progress(conn)
    completed = progress["completed"]
    failed = progress["failed"]
    docs_downloaded = progress["docs_downloaded"]
    directors_extracted = progress["directors_extracted"]

    if completed > 0 or failed > 0:
        logger.info(f"Resuming enrichment...")
        logger.info(f"  Completed: {completed:,}, Failed: {failed:,}")
        logger.info(f"  Docs downloaded: {docs_downloaded:,}, Directors: {directors_extracted:,}")

    remaining = total - completed - failed
    # ~3 requests per company average
    estimated_seconds = remaining * 3 * REQUEST_DELAY
    estimated_days = estimated_seconds / 86400

    logger.info(f"Remaining: ~{remaining:,} companies")
    logger.info(f"Estimated time: {estimated_days:.1f} days (3 requests/company avg)")
    logger.info("=" * 60)
    logger.info("Endpoints: /organisationer + /dokumentlista + /dokument/{id}")
    logger.info("=" * 60)

    adapter = BolagsverketHVDAdapter()

    try:
        logger.info("Testing Bolagsverket API connection...")
        if not await adapter.healthcheck():
            logger.error("Bolagsverket API healthcheck failed!")
            return
        logger.info("Connection OK")

        last_request_time = 0
        processed_count = 0

        for orgnr in get_orgnrs_from_scb(scb_db_path, conn):

            try:
                # === ENDPOINT 1: Company data ===
                last_request_time = await rate_limited_request(last_request_time)
                record = await adapter.fetch_company(orgnr)

                if record and record.raw_data:
                    save_company(conn, orgnr, record.raw_data)
                else:
                    save_failure(conn, orgnr, "not_found")
                    failed += 1
                    continue

                # === ENDPOINT 2: Document list ===
                last_request_time = await rate_limited_request(last_request_time)
                documents = await adapter.list_annual_reports(orgnr)

                if documents:
                    save_annual_reports(conn, orgnr, documents)

                    # === ENDPOINT 3: Download latest annual report for directors ===
                    # All documents are annual reports in ZIP format (filformat: application/zip)
                    # Download the first/latest one
                    latest_doc = documents[0] if documents else None

                    if latest_doc:
                        dokument_id = latest_doc.get("dokumentId", "")
                        if dokument_id:
                            try:
                                last_request_time = await rate_limited_request(last_request_time)
                                doc_content = await adapter.download_document(dokument_id)
                                docs_downloaded += 1

                                # Mark as downloaded
                                conn.execute(
                                    "UPDATE annual_reports SET downloaded = 1 WHERE dokument_id = ?",
                                    (dokument_id,)
                                )

                                # Extract directors using proper XBRL + PDF fallback extractors
                                extraction_result = extract_directors_from_document(
                                    doc_content, orgnr, dokument_id
                                )

                                if extraction_result and extraction_result.directors:
                                    count = save_directors_from_result(
                                        conn, orgnr, dokument_id, extraction_result
                                    )
                                    directors_extracted += count
                                    logger.debug(
                                        f"Extracted {count} directors for {orgnr} "
                                        f"(method: {extraction_result.extraction_method}, "
                                        f"confidence: {extraction_result.extraction_confidence:.2f})"
                                    )

                            except Exception as e:
                                logger.debug(f"Doc download/extraction failed for {orgnr}: {e}")

                completed += 1

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Error enriching {orgnr}: {error_msg[:100]}")
                save_failure(conn, orgnr, error_msg[:500])
                failed += 1

                if "429" in error_msg or "rate" in error_msg.lower():
                    logger.warning("Rate limited! Waiting 60 seconds...")
                    await asyncio.sleep(60)

            processed_count += 1

            # Progress log and checkpoint every 50 companies
            if processed_count % 50 == 0:
                total_processed = completed + failed
                progress_pct = (total_processed / total) * 100 if total > 0 else 0
                rate = 50 / (50 * 3 * REQUEST_DELAY) * 3600
                remaining = total - total_processed
                eta_hours = remaining / rate if rate > 0 else 0

                logger.info(
                    f"Progress: {total_processed:,}/{total:,} ({progress_pct:.2f}%) | "
                    f"OK: {completed:,} | Fail: {failed:,} | "
                    f"Docs: {docs_downloaded:,} | Directors: {directors_extracted:,}"
                )

                save_progress(conn, total_processed, total, completed, failed, docs_downloaded, directors_extracted)
                conn.commit()

        total_processed = completed + failed
        save_progress(conn, total_processed, total, completed, failed, docs_downloaded, directors_extracted)
        conn.commit()

        logger.info("=" * 60)
        logger.info("COMPLETE!")
        logger.info(f"  Total: {total:,}")
        logger.info(f"  Enriched: {completed:,}")
        logger.info(f"  Failed: {failed:,}")
        logger.info(f"  Documents downloaded: {docs_downloaded:,}")
        logger.info(f"  Directors extracted: {directors_extracted:,}")
        logger.info(f"  Database: {db_path}")

    finally:
        await adapter.close()
        conn.close()


if __name__ == "__main__":
    asyncio.run(enrich_all())
