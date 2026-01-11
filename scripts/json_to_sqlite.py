#!/usr/bin/env python3
"""
Convert SCB JSON to SQLite using streaming - minimal memory usage.
"""
import sqlite3
import json
import os

INPUT_FILE = "data/scb_full_registry.json"
OUTPUT_DB = "data/scb_registry.db"
BATCH_SIZE = 5000  # Insert in batches to reduce disk writes

def stream_json_array(filepath):
    """Stream JSON array without loading entire file into memory."""
    with open(filepath, 'r') as f:
        # Skip to start of array
        buffer = ""
        in_array = False
        brace_count = 0

        for line in f:
            if not in_array:
                if '"companies": [' in line:
                    in_array = True
                continue

            for char in line:
                if char == '{':
                    brace_count += 1
                    buffer += char
                elif char == '}':
                    brace_count -= 1
                    buffer += char
                    if brace_count == 0 and buffer.strip():
                        try:
                            yield json.loads(buffer)
                        except json.JSONDecodeError:
                            pass
                        buffer = ""
                elif brace_count > 0:
                    buffer += char

def main():
    # Remove old DB if exists
    if os.path.exists(OUTPUT_DB):
        os.remove(OUTPUT_DB)

    conn = sqlite3.connect(OUTPUT_DB)
    conn.execute("PRAGMA journal_mode=WAL")  # Reduce disk writes
    conn.execute("PRAGMA synchronous=NORMAL")

    # Create table
    conn.execute("""
        CREATE TABLE companies (
            orgnr TEXT PRIMARY KEY,
            name TEXT,
            legal_form TEXT,
            sni_code TEXT,
            municipality TEXT,
            status TEXT,
            f_skatt TEXT,
            moms TEXT,
            employer TEXT,
            post_address TEXT,
            post_nr TEXT,
            post_ort TEXT
        )
    """)

    batch = []
    count = 0

    print("Streaming JSON to SQLite...")
    for company in stream_json_array(INPUT_FILE):
        raw = company.get('raw', {})
        batch.append((
            company.get('orgnr', ''),
            raw.get('Företagsnamn', ''),
            company.get('legal_form', ''),
            company.get('sni_code', ''),
            company.get('municipality', ''),
            company.get('status', ''),
            company.get('f_skatt', ''),
            company.get('moms', ''),
            company.get('employer', ''),
            raw.get('PostAdress', ''),
            raw.get('PostNr', ''),
            raw.get('PostOrt', ''),
        ))

        if len(batch) >= BATCH_SIZE:
            conn.executemany(
                "INSERT OR IGNORE INTO companies VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                batch
            )
            conn.commit()
            count += len(batch)
            print(f"  {count:,} records...", end='\r')
            batch = []

    # Final batch
    if batch:
        conn.executemany(
            "INSERT OR IGNORE INTO companies VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            batch
        )
        conn.commit()
        count += len(batch)

    # Create index
    print(f"\n{count:,} records inserted. Creating index...")
    conn.execute("CREATE INDEX idx_legal_form ON companies(legal_form)")
    conn.commit()
    conn.close()

    size_mb = os.path.getsize(OUTPUT_DB) / 1024 / 1024
    print(f"Done: {OUTPUT_DB} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    main()
