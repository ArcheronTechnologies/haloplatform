"""
Quick test script - bypasses time restrictions for testing.
"""
import asyncio
import logging
from .config import ScraperConfig
from .orchestrator import AllabolagScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    # Create config with relaxed timing for testing
    config = ScraperConfig()

    # Allow running anytime (for testing only!)
    config.timing.active_hours_start = 0
    config.timing.active_hours_end = 24
    config.timing.skip_weekends = False

    # Faster delays for testing (still polite)
    config.timing.min_delay = 3.0
    config.timing.max_delay = 8.0
    config.behavior.reading_time_min = 1.0
    config.behavior.reading_time_max = 3.0

    scraper = AllabolagScraper(config)

    # Load a few test orgnrs
    test_orgnrs = [
        "5560000043",  # Silvertorpet AB
        "5560000241",  # Another old company
        "5560000472",  # Third test
    ]

    scraper.db.add_jobs(test_orgnrs, priority=10)

    # Run for just 3 companies
    print("\n=== Starting test scrape (3 companies) ===\n")
    await scraper.run(max_jobs=3)

    # Show results
    print("\n=== Results ===")
    stats = scraper.db.get_job_stats()
    print(f"Job stats: {stats}")

    # Show scraped companies
    import sqlite3
    conn = sqlite3.connect("allabolag_scrape.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT orgnr, name, city, legal_form, status, employees,
               (SELECT COUNT(*) FROM directors WHERE directors.orgnr = companies.orgnr) as director_count
        FROM companies
        LIMIT 10
    """).fetchall()

    if rows:
        print("\nScraped companies:")
        for row in rows:
            print(f"  {row['orgnr']}: {row['name']}")
            print(f"    City: {row['city']}, Form: {row['legal_form']}, Status: {row['status']}")
            print(f"    Employees: {row['employees']}, Directors: {row['director_count']}")
    else:
        print("\nNo companies scraped yet (check logs for errors)")

    # Show directors
    directors = conn.execute("""
        SELECT d.name, d.role, d.role_group, c.name as company_name
        FROM directors d
        JOIN companies c ON d.orgnr = c.orgnr
        LIMIT 10
    """).fetchall()

    if directors:
        print("\nSample directors:")
        for d in directors:
            print(f"  {d['name']} - {d['role']} ({d['role_group']}) @ {d['company_name']}")

    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
