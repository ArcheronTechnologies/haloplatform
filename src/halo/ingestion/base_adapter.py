"""
Base adapter for data source ingestion.

All data source adapters inherit from this base class to ensure
consistent interface for fetching and transforming data.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel, Field


class IngestionRecord(BaseModel):
    """
    Standardized record from any data source.

    This is the common format that all adapters produce, regardless
    of the underlying API format.
    """

    source: str = Field(..., description="Name of the data source")
    source_id: str = Field(..., description="ID of the record in the source system")
    entity_type: str = Field(..., description="Type of entity: person, company, property, vehicle")
    raw_data: dict[str, Any] = Field(..., description="Original data from the source")
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict[str, Any]] = Field(default=None, description="Optional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "source": "scb_foretagsregistret",
                "source_id": "5566778899",
                "entity_type": "company",
                "raw_data": {
                    "organisationsnummer": "5566778899",
                    "namn": "Test AB",
                    "status": "Aktivt",
                },
                "fetched_at": "2025-01-01T12:00:00Z",
            }
        }


class BaseAdapter(ABC):
    """
    Abstract base for data source adapters.

    Each data source (SCB, Bolagsverket, Lantmäteriet, etc.) has its own
    adapter that inherits from this class.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Unique identifier for this data source.

        Used in IngestionRecord.source and for logging.
        """
        pass

    @abstractmethod
    async def fetch_company(self, orgnr: str) -> Optional[IngestionRecord]:
        """
        Fetch a company by organisationsnummer.

        Args:
            orgnr: Swedish organization number (10 digits)

        Returns:
            IngestionRecord if found, None otherwise
        """
        pass

    @abstractmethod
    async def fetch_person(self, personnummer: str) -> Optional[IngestionRecord]:
        """
        Fetch a person by personnummer.

        Note: Not all data sources have person data. Those that don't
        should return None.

        Args:
            personnummer: Swedish personal identity number (10-12 digits)

        Returns:
            IngestionRecord if found, None otherwise
        """
        pass

    @abstractmethod
    async def search(
        self, query: str, limit: int = 10
    ) -> AsyncIterator[IngestionRecord]:
        """
        Search for entities matching query.

        Args:
            query: Search string
            limit: Maximum number of results

        Yields:
            IngestionRecord for each matching entity
        """
        pass

    async def healthcheck(self) -> bool:
        """
        Check if the data source is available.

        Returns:
            True if the data source is reachable, False otherwise
        """
        return True

    async def close(self) -> None:
        """
        Clean up any resources (connections, etc.)

        Called when the adapter is no longer needed.
        """
        pass

    async def __aenter__(self):
        """Support for async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Support for async context manager."""
        await self.close()
        return False
