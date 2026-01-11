-- Allabolag Scraper Database Schema (SQLite)

-- Companies table
CREATE TABLE IF NOT EXISTS companies (
    org_nr TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    legal_name TEXT,
    status TEXT,
    status_date TEXT,
    registration_date TEXT,
    company_type TEXT,
    sni_code TEXT,
    sni_name TEXT,
    municipality TEXT,
    county TEXT,

    -- Parent company
    parent_org_nr TEXT,
    parent_name TEXT,

    -- Financial summary
    revenue INTEGER,              -- In KSEK
    profit INTEGER,
    employees INTEGER,

    -- Metadata
    allabolag_company_id TEXT,
    scraped_at TEXT NOT NULL,
    raw_json TEXT
);

-- Persons table (deduplicated by allabolag_person_id)
-- Compatible with unified.db schema for later merge
CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    allabolag_person_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    first_name TEXT,             -- Split from name for matching
    last_name TEXT,              -- Split from name for matching
    birth_date TEXT,             -- YYYY-MM-DD from person page
    year_of_birth INTEGER,
    age INTEGER,
    gender TEXT,                 -- 'M' or 'F'

    -- From person page scrape
    person_page_scraped_at TEXT,
    person_page_raw_json TEXT,

    -- Metadata
    source TEXT DEFAULT 'allabolag',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Roles table (person <-> company relationships)
-- Compatible with unified.db schema for later merge
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_org_nr TEXT NOT NULL,
    person_id INTEGER NOT NULL,
    role_type TEXT NOT NULL,
    role_group TEXT,

    -- Source tracking
    discovered_from TEXT,         -- 'company_page' or 'person_page'
    source TEXT DEFAULT 'allabolag',
    scraped_at TEXT NOT NULL,

    UNIQUE(company_org_nr, person_id, role_type),
    FOREIGN KEY (company_org_nr) REFERENCES companies(org_nr) ON DELETE CASCADE,
    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
);

-- Person connections
CREATE TABLE IF NOT EXISTS person_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    connected_person_id INTEGER NOT NULL,
    num_shared_companies INTEGER,
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(person_id, connected_person_id),
    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE,
    FOREIGN KEY (connected_person_id) REFERENCES persons(id) ON DELETE CASCADE
);

-- Company scrape queue
CREATE TABLE IF NOT EXISTS company_scrape_queue (
    org_nr TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    last_attempt_at TEXT,
    error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Person scrape queue
CREATE TABLE IF NOT EXISTS person_scrape_queue (
    allabolag_person_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_slug TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    last_attempt_at TEXT,
    error_message TEXT,
    discovered_from_company TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_companies_parent ON companies(parent_org_nr);
CREATE INDEX IF NOT EXISTS idx_companies_sni ON companies(sni_code);
CREATE INDEX IF NOT EXISTS idx_roles_company ON roles(company_org_nr);
CREATE INDEX IF NOT EXISTS idx_roles_person ON roles(person_id);
CREATE INDEX IF NOT EXISTS idx_company_queue_status ON company_scrape_queue(status);
CREATE INDEX IF NOT EXISTS idx_person_queue_status ON person_scrape_queue(status);
CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);
CREATE INDEX IF NOT EXISTS idx_persons_birth ON persons(birth_date);
