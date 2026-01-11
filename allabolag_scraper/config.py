"""
Configuration for the Allabolag scraper.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
import os


@dataclass
class ScraperConfig:
    # Database (SQLite for portability)
    database_path: Path = field(
        default_factory=lambda: Path(__file__).parent.parent / "data" / "allabolag.db"
    )

    # Timing
    min_delay: float = 2.0          # Minimum seconds between requests
    max_delay: float = 5.0          # Maximum seconds between requests
    request_timeout: float = 30.0   # HTTP timeout

    # Concurrency
    max_workers: int = 3            # Parallel workers (conservative)
    batch_size: int = 50            # Companies per batch

    # Rate limiting
    backoff_factor: float = 2.0     # Exponential backoff multiplier
    max_retries: int = 3            # Retries per company

    # Anti-detection
    proxy_url: Optional[str] = None  # Rotating proxy service

    # Resume
    checkpoint_interval: int = 25   # Save progress every N items

    def __post_init__(self):
        # Ensure data directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
