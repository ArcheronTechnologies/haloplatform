#!/usr/bin/env python3
"""
Import Bolagsverket and SCB bulk files into SQLite databases.

This replaces the slow API enrichment process with direct bulk file import.
"""

import csv
import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
DOWNLOADS_DIR = Path.home() / "Downloads"

# Legal form mapping (SCB codes to names)
LEGAL_FORM_MAP = {
    "10": "Fysisk person",
    "21": "Enkelt bolag",
    "22": "Partrederier",
    "31": "Handelsbolag",
    "32": "Kommanditbolag",
    "41": "Bankaktiebolag",
    "42": "Försäkringsaktiebolag",
    "49": "Aktiebolag",
    "51": "Ekonomisk förening",
    "53": "Bostadsrättsförening",
    "54": "Kooperativ hyresrättsförening",
    "55": "Sambruksförening",
    "56": "Europakooperativ",
    "61": "Ideell förening",
    "62": "Registrerat trossamfund",
    "63": "Familjestiftelse",
    "71": "Annan stiftelse",
    "72": "Pensionsstiftelse",
    "73": "Personalstiftelse",
    "81": "Statlig enhet",
    "82": "Kommun",
    "83": "Region",
    "84": "Kommunalförbund",
    "85": "Allmän försäkringskassa",
    "87": "Offentlig korporation/anstalt",
    "88": "Statligt affärsdrivande verk",
    "89": "Annan offentlig verksamhet",
    "91": "Familjestiftelse",
    "92": "Dödsbo",
    "93": "Ömsesidigt försäkringsbolag",
    "94": "Sparbank",
    "95": "Understödsförening",
    "96": "Utländsk juridisk person (filial)",
    "97": "Europabolag",
    "98": "Europaförening",
}


def import_bolagsverket_bulk(db_path: Path, bulk_file: Path):
    """
    Import Bolagsverket bulk file to SQLite.

    File format: semicolon-delimited with quoted fields
    Fields: organisationsidentitet;namnskyddslopnummer;registreringsland;
            organisationsnamn;organisationsform;avregistreringsdatum;
            avregistreringsorsak;pagandeAvvecklingsEllerOmstruktureringsforfarande;
            registreringsdatum;verksamhetsbeskrivning;postadress
    """
    logger.info(f"Importing Bolagsverket bulk file: {bulk_file}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bolagsverket_companies (
            orgnr TEXT PRIMARY KEY,
            name TEXT,
            legal_form TEXT,
            registration_date TEXT,
            deregistration_date TEXT,
            deregistration_reason TEXT,
            business_description TEXT,
            postal_address TEXT,
            postal_code TEXT,
            city TEXT,
            country TEXT
        )
    """)
    conn.commit()

    batch = []
    batch_size = 10000
    total = 0
    active = 0

    with open(bulk_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';', quotechar='"')
        header = next(reader)  # Skip header

        for row in reader:
            if len(row) < 11:
                continue

            # Parse organisationsidentitet: "5560001234$ORGNR-IDORG"
            org_id = row[0].strip('"')
            orgnr = org_id.split('$')[0] if '$' in org_id else org_id

            # Parse organisationsnamn: "Name$TYPE$DATE|AltName$TYPE$DATE"
            org_name_field = row[3].strip('"')
            name = org_name_field.split('$')[0] if '$' in org_name_field else org_name_field

            # Parse organisationsform: "AB-ORGFO"
            legal_form_raw = row[4].strip('"')
            legal_form = legal_form_raw.split('-')[0] if '-' in legal_form_raw else legal_form_raw

            dereg_date = row[5].strip('"') if row[5] else None
            dereg_reason = row[6].strip('"') if row[6] else None
            reg_date = row[8].strip('"') if row[8] else None
            verksamhet = row[9].strip('"') if row[9] else None

            # Parse postadress: "Street$C/O$City$PostNr$Country"
            address_field = row[10].strip('"') if len(row) > 10 else ""
            address_parts = address_field.split('$')
            street = address_parts[0] if len(address_parts) > 0 else ""
            city = address_parts[2] if len(address_parts) > 2 else ""
            postal_code = address_parts[3] if len(address_parts) > 3 else ""
            country = address_parts[4] if len(address_parts) > 4 else "SE"

            if not dereg_date:
                active += 1

            batch.append((
                orgnr, name, legal_form, reg_date, dereg_date,
                dereg_reason, verksamhet, street, postal_code, city, country
            ))

            if len(batch) >= batch_size:
                conn.executemany("""
                    INSERT OR REPLACE INTO bolagsverket_companies
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, batch)
                conn.commit()
                total += len(batch)
                logger.info(f"Imported {total:,} records ({active:,} active)")
                batch = []

    if batch:
        conn.executemany("""
            INSERT OR REPLACE INTO bolagsverket_companies
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, batch)
        conn.commit()
        total += len(batch)

    # Create index
    logger.info("Creating index on deregistration_date...")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bv_dereg ON bolagsverket_companies(deregistration_date)")
    conn.commit()

    logger.info(f"COMPLETE: {total:,} total records, {active:,} active companies")
    conn.close()


def import_scb_bulk(db_path: Path, bulk_file: Path):
    """
    Import SCB bulk file to SQLite.

    File format: tab-delimited
    Fields: ForAndrTyp, COAdress, Foretagsnamn, FtgStat, Gatuadress, JEStat,
            JurForm, Namn, Ng1-Ng5, PeOrgNr, PostNr, PostOrt, RegDatKtid, Reklamsparrtyp, ...
    """
    logger.info(f"Importing SCB bulk file: {bulk_file}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS scb_companies (
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
            je_status TEXT,
            registration_date TEXT,
            marketing_block TEXT
        )
    """)
    conn.commit()

    batch = []
    batch_size = 10000
    total = 0
    active = 0

    with open(bulk_file, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f, delimiter='\t')
        header = next(reader)  # Skip header

        for row in reader:
            if len(row) < 18:
                continue

            # PeOrgNr is column 14 (0-indexed 13)
            orgnr_raw = row[13]
            # Strip 16 prefix if present
            if len(orgnr_raw) == 12 and orgnr_raw.startswith('16'):
                orgnr = orgnr_raw[2:]
            else:
                orgnr = orgnr_raw

            legal_form_code = row[6]
            legal_form = LEGAL_FORM_MAP.get(legal_form_code, legal_form_code)

            status = row[3]
            if status == '1':
                active += 1

            batch.append((
                orgnr,
                row[7],   # Namn (col 8)
                row[2],   # Foretagsnamn (col 3)
                legal_form_code,
                legal_form,
                row[8],   # Ng1 (col 9)
                row[9],   # Ng2 (col 10)
                row[10],  # Ng3 (col 11)
                row[11],  # Ng4 (col 12)
                row[12],  # Ng5 (col 13)
                row[4],   # Gatuadress (col 5)
                row[1],   # COAdress (col 2)
                row[14],  # PostNr (col 15)
                row[15],  # PostOrt (col 16)
                row[3],   # FtgStat (col 4)
                row[5],   # JEStat (col 6)
                row[16],  # RegDatKtid (col 17)
                row[17],  # Reklamsparrtyp (col 18)
            ))

            if len(batch) >= batch_size:
                conn.executemany("""
                    INSERT OR REPLACE INTO scb_companies
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, batch)
                conn.commit()
                total += len(batch)
                logger.info(f"Imported {total:,} records ({active:,} active)")
                batch = []

    if batch:
        conn.executemany("""
            INSERT OR REPLACE INTO scb_companies
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, batch)
        conn.commit()
        total += len(batch)

    # Create indexes
    logger.info("Creating indexes...")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scb_status ON scb_companies(company_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scb_legal ON scb_companies(legal_form_code)")
    conn.commit()

    logger.info(f"COMPLETE: {total:,} total records, {active:,} active companies")
    conn.close()


def main():
    bolagsverket_bulk = DOWNLOADS_DIR / "bolagsverket_bulkfil.txt"
    scb_bulk = list(DOWNLOADS_DIR.glob("scb_bulkfil_*.txt"))

    if not bolagsverket_bulk.exists():
        logger.error(f"Bolagsverket bulk file not found: {bolagsverket_bulk}")
    else:
        bv_db = DATA_DIR / "bolagsverket_bulk.db"
        import_bolagsverket_bulk(bv_db, bolagsverket_bulk)
        logger.info(f"Bolagsverket data saved to: {bv_db}")

    print()

    if not scb_bulk:
        logger.error("SCB bulk file not found in Downloads")
    else:
        scb_file = scb_bulk[0]  # Use first match
        scb_db = DATA_DIR / "scb_bulk.db"
        import_scb_bulk(scb_db, scb_file)
        logger.info(f"SCB data saved to: {scb_db}")


if __name__ == "__main__":
    main()
