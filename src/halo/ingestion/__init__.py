"""
Data ingestion module for Halo platform.

Provides adapters for Swedish government APIs and data sources:
- SCB Företagsregistret (Swedish Business Register) - individual company records
- SCB PxWeb (Statistical Database) - aggregate statistics for benchmarking
- Bolagsverket HVD (High Value Datasets) - company registration data
- Document uploads (PDF, DOCX, email)
"""

from halo.ingestion.base_adapter import BaseAdapter, IngestionRecord
from halo.ingestion.scb_foretag import SCBForetagAdapter
from halo.ingestion.scb_pxweb import SCBPxWebAdapter
from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter
from halo.ingestion.document_upload import DocumentUploadAdapter
from halo.ingestion.rate_limiter import RateLimiter, RateLimitConfig, RateLimitedClient
from halo.ingestion.allabolag_adapter import AllabolagAdapter

__all__ = [
    # Base
    "BaseAdapter",
    "IngestionRecord",
    # Rate limiting
    "RateLimiter",
    "RateLimitConfig",
    "RateLimitedClient",
    # Government APIs
    "SCBForetagAdapter",
    "SCBPxWebAdapter",
    "BolagsverketHVDAdapter",
    # Data imports
    "DocumentUploadAdapter",
    # Scraped data (read-only)
    "AllabolagAdapter",
]
