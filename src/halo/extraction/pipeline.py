"""
Extraction pipeline for Swedish annual reports.

Orchestrates the full workflow:
1. Authenticate with Bolagsverket HVD API
2. Fetch document list for a company
3. Download annual report ZIP
4. Extract directors using XBRL extractor
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .models import ExtractionResult
from .xbrl_extractor import XBRLExtractor
from .pdf_extractor import PDFExtractor

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the extraction pipeline."""

    bv_client_id: str
    bv_client_secret: str
    bv_base_url: str = "https://gw.api.bolagsverket.se/vardefulla-datamangder/v1"
    bv_token_url: str = "https://portal.api.bolagsverket.se/oauth2/token"
    bv_scopes: str = "vardefulla-datamangder:ping vardefulla-datamangder:read"
    min_confidence: float = 0.5
    rate_limit_delay: float = 0.5  # Seconds between requests
    request_timeout: float = 60.0


@dataclass
class CompanyInfo:
    """Basic company information from the API."""

    orgnr: str
    name: Optional[str] = None
    legal_form: Optional[str] = None
    status: Optional[str] = None
    registration_date: Optional[str] = None
    postal_code: Optional[str] = None
    postal_city: Optional[str] = None
    sni_codes: list[str] = field(default_factory=list)


@dataclass
class DocumentInfo:
    """Document information from dokumentlista."""

    document_id: str
    file_format: str
    reporting_period_end: Optional[str] = None
    registration_date: Optional[str] = None


class ExtractionPipeline:
    """
    End-to-end pipeline for director extraction.

    Usage:
        config = PipelineConfig(
            bv_client_id="...",
            bv_client_secret="..."
        )
        pipeline = ExtractionPipeline(config)

        async with pipeline:
            result = await pipeline.process_company("5592584386")
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._token: Optional[str] = None
        self._token_expires: float = 0
        self._http: Optional[httpx.AsyncClient] = None

        # Initialize extractors
        self.xbrl_extractor = XBRLExtractor(min_confidence=config.min_confidence)
        self.pdf_extractor = PDFExtractor(min_confidence=config.min_confidence)

    async def __aenter__(self):
        self._http = httpx.AsyncClient(timeout=self.config.request_timeout)
        return self

    async def __aexit__(self, *args):
        if self._http:
            await self._http.aclose()

    async def _get_token(self) -> str:
        """Get or refresh OAuth token."""
        if self._token and time.time() < self._token_expires:
            return self._token

        response = await self._http.post(
            self.config.bv_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.config.bv_client_id,
                "client_secret": self.config.bv_client_secret,
                "scope": self.config.bv_scopes,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        data = response.json()

        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600) - 60

        logger.debug("Obtained new Bolagsverket token")
        return self._token

    async def get_company_info(self, orgnr: str) -> Optional[CompanyInfo]:
        """
        Get basic company information from Bolagsverket.

        Args:
            orgnr: Organization number (10 digits, no dash)

        Returns:
            CompanyInfo or None if not found
        """
        orgnr = orgnr.replace("-", "").replace(" ", "")
        token = await self._get_token()

        try:
            response = await self._http.post(
                f"{self.config.bv_base_url}/organisationer",
                json={"identitetsbeteckning": orgnr},
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()

            data = response.json()
            orgs = data.get("organisationer", [])

            if not orgs:
                return None

            org = orgs[0]

            # Extract name
            name = None
            name_list = (
                org.get("organisationsnamn", {}).get("organisationsnamnLista", [])
            )
            if name_list:
                name = name_list[0].get("namn")

            # Extract legal form
            legal_form = org.get("organisationsform", {}).get("kod")

            # Extract status
            status = org.get("verksamOrganisation", {}).get("kod")

            # Extract registration date
            reg_date = org.get("organisationsdatum", {}).get("registreringsdatum")

            # Extract postal info
            postal = org.get("postadressOrganisation", {}).get("postadress") or {}
            postal_code = postal.get("postnummer")
            postal_city = postal.get("postort")

            # Extract SNI codes
            sni_list = org.get("naringsgrenOrganisation", {}).get("sni", [])
            sni_codes = [
                s.get("kod") for s in sni_list if s.get("kod") and s.get("kod").strip()
            ]

            return CompanyInfo(
                orgnr=orgnr,
                name=name,
                legal_form=legal_form,
                status=status,
                registration_date=reg_date,
                postal_code=postal_code,
                postal_city=postal_city,
                sni_codes=sni_codes,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                logger.warning(f"Invalid org number: {orgnr}")
            else:
                logger.error(f"API error for {orgnr}: {e}")
            return None

    async def get_document_list(self, orgnr: str) -> list[DocumentInfo]:
        """
        Get list of annual reports for a company.

        Args:
            orgnr: Organization number

        Returns:
            List of DocumentInfo objects
        """
        orgnr = orgnr.replace("-", "").replace(" ", "")
        token = await self._get_token()

        try:
            response = await self._http.post(
                f"{self.config.bv_base_url}/dokumentlista",
                json={"identitetsbeteckning": orgnr},
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()

            data = response.json()
            documents = []

            for doc in data.get("dokument", []):
                documents.append(
                    DocumentInfo(
                        document_id=doc.get("dokumentId", ""),
                        file_format=doc.get("filformat", ""),
                        reporting_period_end=doc.get("rapporteringsperiodTom"),
                        registration_date=doc.get("registreringstidpunkt"),
                    )
                )

            return documents

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get document list for {orgnr}: {e}")
            return []

    async def download_document(self, document_id: str) -> Optional[bytes]:
        """
        Download an annual report document.

        Args:
            document_id: Document ID from dokumentlista

        Returns:
            ZIP file bytes or None on error
        """
        token = await self._get_token()

        try:
            response = await self._http.get(
                f"{self.config.bv_base_url}/dokument/{document_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.content

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to download document {document_id}: {e}")
            return None

    async def process_company(
        self, orgnr: str, max_documents: int = 1
    ) -> list[ExtractionResult]:
        """
        Process a company: fetch documents and extract directors.

        Args:
            orgnr: Organization number
            max_documents: Maximum number of annual reports to process

        Returns:
            List of ExtractionResult objects
        """
        results = []

        # Get company info first
        company_info = await self.get_company_info(orgnr)
        if not company_info:
            logger.warning(f"Company not found: {orgnr}")
            return results

        # Get document list
        documents = await self.get_document_list(orgnr)

        if not documents:
            logger.info(f"No documents found for {orgnr} ({company_info.name})")
            return results

        logger.info(
            f"Found {len(documents)} documents for {orgnr} ({company_info.name})"
        )

        # Process documents (most recent first - they should already be sorted)
        for doc in documents[:max_documents]:
            if not doc.document_id:
                continue

            try:
                # Download
                logger.debug(f"Downloading {doc.document_id}")
                zip_bytes = await self.download_document(doc.document_id)

                if not zip_bytes:
                    results.append(
                        ExtractionResult(
                            orgnr=orgnr,
                            document_id=doc.document_id,
                            company_name=company_info.name,
                            warnings=["Failed to download document"],
                        )
                    )
                    continue

                # Extract - try XBRL first, fall back to PDF
                logger.debug(f"Extracting from {doc.document_id}")
                result = self.xbrl_extractor.extract_from_zip(
                    zip_bytes, orgnr, doc.document_id
                )

                # If XBRL extraction found no directors, try PDF fallback
                if not result.directors:
                    logger.debug(f"XBRL extraction empty, trying PDF fallback for {doc.document_id}")
                    result = self.pdf_extractor.extract_from_zip(
                        zip_bytes, orgnr, doc.document_id
                    )

                result.company_name = company_info.name

                results.append(result)

                # Rate limiting
                await asyncio.sleep(self.config.rate_limit_delay)

            except Exception as e:
                logger.error(f"Failed to process {doc.document_id}: {e}")
                results.append(
                    ExtractionResult(
                        orgnr=orgnr,
                        document_id=doc.document_id,
                        company_name=company_info.name,
                        warnings=[f"Processing failed: {e}"],
                    )
                )

        return results

    async def process_batch(
        self,
        orgnrs: list[str],
        max_documents_per_company: int = 1,
        concurrency: int = 5,
    ) -> dict[str, list[ExtractionResult]]:
        """
        Process multiple companies with concurrency control.

        Args:
            orgnrs: List of organization numbers
            max_documents_per_company: Documents per company
            concurrency: Max concurrent operations

        Returns:
            Dict mapping orgnr to extraction results
        """
        semaphore = asyncio.Semaphore(concurrency)
        results = {}

        async def process_one(orgnr: str):
            async with semaphore:
                try:
                    results[orgnr] = await self.process_company(
                        orgnr, max_documents_per_company
                    )
                except Exception as e:
                    logger.error(f"Batch processing failed for {orgnr}: {e}")
                    results[orgnr] = []

        tasks = [process_one(orgnr) for orgnr in orgnrs]
        await asyncio.gather(*tasks, return_exceptions=True)

        return results
