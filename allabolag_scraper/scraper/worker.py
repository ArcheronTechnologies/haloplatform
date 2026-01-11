"""
Async HTTP worker for fetching company and person pages.
"""

import httpx
import asyncio
import random
from typing import Optional
from dataclasses import dataclass
from urllib.parse import quote
from enum import Enum

from allabolag_scraper.config import ScraperConfig


class FetchType(Enum):
    COMPANY = "company"
    PERSON = "person"


@dataclass
class FetchResult:
    identifier: str        # org_nr for company, person_id for person
    fetch_type: FetchType
    html: Optional[str]
    status_code: int
    error: Optional[str]


# Rotate user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_headers() -> dict:
    """Generate realistic browser headers."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }


class Worker:
    """Async worker for fetching company and person pages."""

    BASE_URL = "https://www.allabolag.se"

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=self.config.request_timeout,
            follow_redirects=True,
            http2=True,
        )
        return self

    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()

    def _build_company_url(self, org_nr: str) -> str:
        """Build allabolag URL from org number."""
        clean_org_nr = org_nr.replace('-', '')
        return f"{self.BASE_URL}/{clean_org_nr}"

    def _build_person_url(self, name: str, person_id: str) -> str:
        """
        Build person page URL.
        Format: /befattning/{name-slug}/-/{person_id}
        """
        name_slug = name.lower().replace(' ', '-')
        name_slug = quote(name_slug, safe='-')
        return f"{self.BASE_URL}/befattning/{name_slug}/-/{person_id}"

    async def _fetch_url(self, url: str, identifier: str, fetch_type: FetchType) -> FetchResult:
        """Internal fetch method."""
        try:
            response = await self.client.get(url, headers=get_headers())

            if response.status_code == 200:
                return FetchResult(
                    identifier=identifier,
                    fetch_type=fetch_type,
                    html=response.text,
                    status_code=200,
                    error=None
                )
            elif response.status_code == 404:
                return FetchResult(
                    identifier=identifier,
                    fetch_type=fetch_type,
                    html=None,
                    status_code=404,
                    error="Not found"
                )
            elif response.status_code == 429:
                return FetchResult(
                    identifier=identifier,
                    fetch_type=fetch_type,
                    html=None,
                    status_code=429,
                    error="Rate limited"
                )
            else:
                return FetchResult(
                    identifier=identifier,
                    fetch_type=fetch_type,
                    html=None,
                    status_code=response.status_code,
                    error=f"HTTP {response.status_code}"
                )

        except httpx.TimeoutException:
            return FetchResult(
                identifier=identifier,
                fetch_type=fetch_type,
                html=None,
                status_code=0,
                error="Timeout"
            )
        except httpx.RequestError as e:
            return FetchResult(
                identifier=identifier,
                fetch_type=fetch_type,
                html=None,
                status_code=0,
                error=str(e)
            )

    async def fetch_company(self, org_nr: str) -> FetchResult:
        """Fetch a company page."""
        url = self._build_company_url(org_nr)
        return await self._fetch_url(url, org_nr, FetchType.COMPANY)

    async def fetch_person(self, name: str, person_id: str) -> FetchResult:
        """Fetch a person page."""
        url = self._build_person_url(name, person_id)
        return await self._fetch_url(url, person_id, FetchType.PERSON)

    async def delay(self):
        """Random delay between requests."""
        delay = random.uniform(self.config.min_delay, self.config.max_delay)
        await asyncio.sleep(delay)
