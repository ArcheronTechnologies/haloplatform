"""
SCB PxWeb API adapter for the Statistical Database.

FREE API - No registration required (but rate limited).
Docs: [REDACTED_API_ENDPOINT]

API Versions:
- v1 (current): [REDACTED_API_ENDPOINT]
- v2 (new Oct 2025): [REDACTED_API_ENDPOINT]

Rate limits:
- 10 requests per 10 seconds per IP
- Max 100,000 values per query

Available data categories:
- BE: Population
- NV: Business activities
- AM: Labour market
- BO: Housing, construction and building
- EN: Energy
- FM: Financial markets
- HA: Trade in goods and services
- HE: Household finances
- JO: Agriculture, forestry and fishery
- LE: Living conditions
- ME: Democracy
- MI: Environment
- NR: National accounts
- OE: Public finances
- PR: Prices and Consumption
- TK: Transport and communications
- UF: Education and research
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import httpx

from halo.ingestion.base_adapter import BaseAdapter, IngestionRecord
from halo.ingestion.rate_limiter import RateLimiter, RateLimitConfig, RateLimitedClient

logger = logging.getLogger(__name__)


# SCB rate limiter: 10 requests per 10 seconds
SCB_RATE_LIMITER = RateLimiter(
    RateLimitConfig(
        requests_per_window=10,
        window_seconds=10.0,
    )
)


@dataclass
class SCBTable:
    """Metadata about an SCB statistical table."""

    table_id: str
    title: str
    path: list[str]
    variables: list[dict] = field(default_factory=list)
    last_updated: Optional[datetime] = None


@dataclass
class SCBQuery:
    """Query parameters for fetching data from SCB."""

    table_id: str
    variables: dict[str, list[str]]  # variable_code -> list of values
    response_format: str = "json"


class SCBPxWebAdapter(BaseAdapter):
    """
    Adapter for SCB Statistical Database via PxWeb API.

    This is different from SCB Företagsregistret (business register).
    This adapter accesses aggregate statistics, not individual records.

    Useful for:
    - Industry statistics (benchmark company data)
    - Population demographics (validate person context)
    - Economic indicators (detect anomalies)
    - Geographic data (validate addresses)
    """

    # API v1 (current) - will be deprecated fall 2025
    BASE_URL_V1 = "[REDACTED_API_ENDPOINT]"

    # API v2 (new) - RESTful design
    BASE_URL_V2 = "[REDACTED_API_ENDPOINT]"

    # Subject area codes
    SUBJECT_AREAS = {
        "BE": "Population",
        "NV": "Business activities",
        "AM": "Labour market",
        "BO": "Housing, construction and building",
        "EN": "Energy",
        "FM": "Financial markets",
        "HA": "Trade in goods and services",
        "HE": "Household finances",
        "JO": "Agriculture, forestry and fishery",
        "LE": "Living conditions",
        "ME": "Democracy",
        "MI": "Environment",
        "NR": "National accounts",
        "OE": "Public finances",
        "PR": "Prices and Consumption",
        "TK": "Transport and communications",
        "UF": "Education and research",
    }

    def __init__(
        self,
        use_v2: bool = False,
        language: str = "en",
    ):
        """
        Initialize the SCB PxWeb adapter.

        Args:
            use_v2: Use the new v2 API (recommended for new integrations)
            language: Language code ('en' or 'sv')
        """
        self.use_v2 = use_v2
        self.language = language

        if use_v2:
            self.base_url = self.BASE_URL_V2
        else:
            self.base_url = self.BASE_URL_V1

        # Create rate-limited client
        self._raw_client = httpx.AsyncClient(
            timeout=60.0,  # Some queries take a while
            headers={"Accept": "application/json"},
        )
        self._client = RateLimitedClient(self._raw_client, SCB_RATE_LIMITER)

    @property
    def source_name(self) -> str:
        return "scb_pxweb"

    async def fetch_company(self, orgnr: str) -> Optional[IngestionRecord]:
        """PxWeb doesn't have individual company data - use SCBForetagAdapter."""
        return None

    async def fetch_person(self, personnummer: str) -> Optional[IngestionRecord]:
        """PxWeb doesn't have individual person data."""
        return None

    async def list_subject_areas(self) -> list[dict]:
        """
        List all available subject areas.

        Returns:
            List of subject areas with code and title
        """
        response = await self._client.get(self.base_url)
        data = response.json()

        return [
            {
                "code": item.get("id", ""),
                "title": item.get("text", ""),
                "has_tables": item.get("type", "") == "l",
            }
            for item in data
        ]

    async def list_tables(
        self,
        subject_area: str,
        sub_path: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        List tables in a subject area.

        Args:
            subject_area: Subject area code (e.g., 'NV' for Business)
            sub_path: Optional path components to drill down

        Returns:
            List of tables/folders in the path
        """
        path_parts = [subject_area]
        if sub_path:
            path_parts.extend(sub_path)

        url = f"{self.base_url}/{'/'.join(path_parts)}"
        response = await self._client.get(url)
        data = response.json()

        return [
            {
                "id": item.get("id", ""),
                "text": item.get("text", ""),
                "type": "table" if item.get("type") == "t" else "folder",
            }
            for item in data
        ]

    async def get_table_metadata(
        self,
        table_path: str,
    ) -> SCBTable:
        """
        Get metadata for a specific table.

        Args:
            table_path: Full path to table (e.g., 'NV/NV0101/NV0101A/NV0101A00')

        Returns:
            SCBTable with variable information
        """
        url = f"{self.base_url}/{table_path}"
        response = await self._client.get(url)
        data = response.json()

        variables = []
        for var in data.get("variables", []):
            variables.append({
                "code": var.get("code", ""),
                "text": var.get("text", ""),
                "values": var.get("values", []),
                "valueTexts": var.get("valueTexts", []),
                "elimination": var.get("elimination", False),
            })

        return SCBTable(
            table_id=table_path.split("/")[-1],
            title=data.get("title", ""),
            path=table_path.split("/"),
            variables=variables,
        )

    async def query_table(
        self,
        table_path: str,
        query: dict[str, list[str]],
        response_format: str = "json",
    ) -> dict[str, Any]:
        """
        Query data from a table.

        Args:
            table_path: Full path to table
            query: Dict mapping variable codes to selected values
            response_format: Output format ('json', 'json-stat', 'csv', 'xlsx')

        Returns:
            Query results in requested format
        """
        url = f"{self.base_url}/{table_path}"

        # Build query payload
        query_items = []
        for code, values in query.items():
            query_items.append({
                "code": code,
                "selection": {
                    "filter": "item",
                    "values": values,
                },
            })

        payload = {
            "query": query_items,
            "response": {
                "format": response_format,
            },
        }

        response = await self._client.post(url, json=payload)
        return response.json()

    async def get_business_statistics(
        self,
        sni_code: Optional[str] = None,
        municipality: Optional[str] = None,
        year: Optional[str] = None,
    ) -> IngestionRecord:
        """
        Get business/industry statistics.

        Useful for benchmarking company data.

        Args:
            sni_code: Industry classification code
            municipality: Municipality code
            year: Year to query

        Returns:
            IngestionRecord with business statistics
        """
        # Example: Number of enterprises by industry
        table_path = "NV/NV0101/NV0101A/NV0101ENS2020N"

        query = {}
        if sni_code:
            query["SNI2007"] = [sni_code]
        if year:
            query["Tid"] = [year]
        else:
            query["Tid"] = ["*"]  # All available years

        try:
            data = await self.query_table(table_path, query)

            return IngestionRecord(
                source=self.source_name,
                source_id=f"business_stats_{sni_code or 'all'}_{year or 'all'}",
                entity_type="statistics",
                raw_data=data,
                fetched_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(f"Failed to get business statistics: {e}")
            raise

    async def get_population_statistics(
        self,
        region: Optional[str] = None,
        age_group: Optional[str] = None,
        year: Optional[str] = None,
    ) -> IngestionRecord:
        """
        Get population statistics.

        Useful for demographic context.

        Args:
            region: Region code
            age_group: Age group filter
            year: Year to query

        Returns:
            IngestionRecord with population statistics
        """
        # Population by region, age and sex
        table_path = "BE/BE0101/BE0101A/BesijNV"

        query = {}
        if region:
            query["Region"] = [region]
        if year:
            query["Tid"] = [year]
        else:
            query["Tid"] = ["*"]

        try:
            data = await self.query_table(table_path, query)

            return IngestionRecord(
                source=self.source_name,
                source_id=f"population_{region or 'all'}_{year or 'all'}",
                entity_type="statistics",
                raw_data=data,
                fetched_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(f"Failed to get population statistics: {e}")
            raise

    async def get_financial_statistics(
        self,
        indicator: str,
        year: Optional[str] = None,
    ) -> IngestionRecord:
        """
        Get financial market statistics.

        Useful for economic context in investigations.

        Args:
            indicator: Financial indicator type
            year: Year to query

        Returns:
            IngestionRecord with financial statistics
        """
        # Financial market statistics path
        table_path = "FM/FM0001/FM0001M"

        query = {}
        if year:
            query["Tid"] = [year]
        else:
            query["Tid"] = ["*"]

        try:
            data = await self.query_table(table_path, query)

            return IngestionRecord(
                source=self.source_name,
                source_id=f"financial_{indicator}_{year or 'all'}",
                entity_type="statistics",
                raw_data=data,
                fetched_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(f"Failed to get financial statistics: {e}")
            raise

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> AsyncIterator[IngestionRecord]:
        """
        Search is not directly supported by PxWeb API.

        Use list_tables() to browse available data.
        """
        logger.warning("Search not supported by PxWeb API - use list_tables()")
        return
        yield  # Make this a generator

    async def healthcheck(self) -> bool:
        """Check if SCB API is available."""
        try:
            response = await self._raw_client.get(
                self.base_url,
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"SCB PxWeb healthcheck failed: {e}")
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._raw_client.aclose()


# Convenience functions for common queries

async def get_industry_benchmarks(
    sni_code: str,
    years: list[str] = None,
) -> dict[str, Any]:
    """
    Get industry benchmark data for a specific SNI code.

    Args:
        sni_code: Swedish Standard Industrial Classification code
        years: Years to include (default: last 5 years)

    Returns:
        Industry statistics for benchmarking
    """
    adapter = SCBPxWebAdapter()
    try:
        if not years:
            current_year = datetime.now().year
            years = [str(y) for y in range(current_year - 5, current_year)]

        results = []
        for year in years:
            record = await adapter.get_business_statistics(
                sni_code=sni_code,
                year=year,
            )
            results.append(record.raw_data)

        return {
            "sni_code": sni_code,
            "years": years,
            "data": results,
        }
    finally:
        await adapter.close()


async def get_municipality_demographics(
    municipality_code: str,
) -> dict[str, Any]:
    """
    Get demographic data for a municipality.

    Useful for context in investigations involving specific areas.

    Args:
        municipality_code: Swedish municipality code (e.g., '0180' for Stockholm)

    Returns:
        Population and demographic statistics
    """
    adapter = SCBPxWebAdapter()
    try:
        record = await adapter.get_population_statistics(
            region=municipality_code,
        )
        return record.raw_data
    finally:
        await adapter.close()
