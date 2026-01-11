"""
Allabolag.se Scraper

Zero-cost, slow-and-steady bulk scraper for Swedish company data.
"""
from .config import ScraperConfig
from .database import ScraperDatabase, Company, ScrapeJob
from .session import SessionManager, BlockDetectedError
from .parser import AllabolagParser
from .orchestrator import AllabolagScraper

__all__ = [
    'ScraperConfig',
    'ScraperDatabase',
    'Company',
    'ScrapeJob',
    'SessionManager',
    'BlockDetectedError',
    'AllabolagParser',
    'AllabolagScraper',
]
