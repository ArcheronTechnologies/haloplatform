"""
SCB Företagsregistret API adapter.

FREE API as of June 2025 (EU High Value Datasets directive).
Contains all 1.8M Swedish companies and 1.4M workplaces.

Registration: Email scbforetag@scb.se for certificate + password.
Docs: [REDACTED_API_ENDPOINT]

Rate limit: 10 requests per 10 seconds
Max rows per request: 2000
Auth: Client certificate (PFX file)
"""

import logging
import ssl
import tempfile
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx

from halo.config import settings
from halo.ingestion.base_adapter import BaseAdapter, IngestionRecord

logger = logging.getLogger(__name__)


class SCBForetagAdapter(BaseAdapter):
    """
    Adapter for SCB Företagsregistret (Swedish Business Register).

    API URL: [REDACTED_API_ENDPOINT]

    Data available:
    - Organisationsnummer (PeOrgNr - 12 digits)
    - Företagsnamn
    - Juridisk form (AB, HB, etc.)
    - SNI codes (industry classification)
    - Addresses
    - Status (active/inactive)
    - F-skatt, Moms, Arbetsgivare registration
    """

    BASE_URL = "[REDACTED_API_ENDPOINT]"

    def __init__(
        self,
        cert_path: Optional[Path] = None,
        cert_password: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        Initialize the SCB adapter.

        Args:
            cert_path: Path to client certificate (PFX/P12 file)
            cert_password: Password for the certificate
            base_url: Override base URL (useful for testing)
        """
        self.cert_path = Path(cert_path) if cert_path else settings.scb_cert_path
        self.cert_password = cert_password or settings.scb_cert_password
        self.base_url = base_url or self.BASE_URL
        self._client: Optional[httpx.AsyncClient] = None
        self._temp_dir: Optional[str] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with certificate authentication."""
        if self._client is not None:
            return self._client

        if self.cert_path and self.cert_path.exists():
            # Convert PFX to PEM for httpx
            cert_pem, key_pem = self._extract_pem_from_pfx()

            self._client = httpx.AsyncClient(
                cert=(cert_pem, key_pem),
                timeout=30.0,
                verify=True,
            )
            logger.info(f"SCB client initialized with certificate: {self.cert_path}")
        else:
            logger.warning("SCB certificate not configured, API calls will fail")
            self._client = httpx.AsyncClient(timeout=30.0)

        return self._client

    def _extract_pem_from_pfx(self) -> tuple[str, str]:
        """Extract PEM certificate and key from PFX file."""
        from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

        # Read PFX file
        with open(self.cert_path, 'rb') as f:
            pfx_data = f.read()

        # Load PKCS12 data
        private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
            pfx_data,
            self.cert_password.encode() if self.cert_password else None
        )

        # Create temporary directory for PEM files
        self._temp_dir = tempfile.mkdtemp()
        cert_pem_path = Path(self._temp_dir) / "cert.pem"
        key_pem_path = Path(self._temp_dir) / "key.pem"

        # Write certificate
        with open(cert_pem_path, 'wb') as f:
            f.write(certificate.public_bytes(Encoding.PEM))

        # Write private key
        with open(key_pem_path, 'wb') as f:
            f.write(private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=NoEncryption()
            ))

        logger.debug(f"Extracted PEM files to {self._temp_dir}")
        return str(cert_pem_path), str(key_pem_path)

    @property
    def source_name(self) -> str:
        return "scb_foretagsregistret"

    async def fetch_company(self, orgnr: str) -> Optional[IngestionRecord]:
        """
        Fetch company by organisationsnummer.

        Args:
            orgnr: 10-digit Swedish org number
        """
        orgnr = orgnr.replace("-", "").replace(" ", "")

        client = await self._get_client()

        try:
            # POST request with OrgNr filter using Variabler
            # Use the correct endpoint and Swedish field names
            response = await client.post(
                f"{self.base_url}/api/Je/HamtaForetag",
                json={
                    "Variabler": [
                        {"Variabel": "OrgNr (10 siffror)", "Varde": orgnr, "Operator": "ArLikaMed"}
                    ],
                    "MaxAntalRader": 1,
                },
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()

            data = response.json()

            # SCB returns a list
            if isinstance(data, list) and len(data) > 0:
                return IngestionRecord(
                    source=self.source_name,
                    source_id=orgnr,
                    entity_type="company",
                    raw_data=data[0],
                    fetched_at=datetime.utcnow(),
                )
            return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Company not found: {orgnr}")
                return None
            logger.error(f"SCB API error fetching company {orgnr}: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"SCB API request failed for company {orgnr}: {e}")
            raise

    async def fetch_companies_batch(
        self,
        offset: int = 0,
        limit: int = 2000,
        only_active: bool = True,
        municipality: Optional[str] = None,
        legal_form: Optional[str] = None,
        **filters
    ) -> list[IngestionRecord]:
        """
        Fetch batch of companies with filters.

        Args:
            offset: Start from row number
            limit: Max rows (max 2000)
            only_active: Only fetch active companies (Företagsstatus=1)
            municipality: 4-digit municipality code (SätesKommun)
            legal_form: Legal form code (e.g., "49" for Aktiebolag)
            **filters: Additional filters as Kategorier

        Returns:
            List of IngestionRecords
        """
        client = await self._get_client()

        # Build request body using SCB's format
        params = {
            "StartRadNr": offset,
            "MaxAntalRader": min(limit, 2000),
        }

        # Add status filters
        if only_active:
            params["Företagsstatus"] = "1"  # 1 = Active
            params["Registreringsstatus"] = "1"  # 1 = Registered

        # Add category filters
        kategorier = []
        if municipality:
            kategorier.append({"Kategori": "SätesKommun", "Kod": [municipality]})
        if legal_form:
            kategorier.append({"Kategori": "Juridisk form", "Kod": [legal_form]})

        if kategorier:
            params["Kategorier"] = kategorier

        try:
            response = await client.post(
                f"{self.base_url}/api/Je/HamtaForetag",
                json=params,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()

            data = response.json()

            records = []
            if isinstance(data, list):
                for company in data:
                    orgnr = company.get("OrgNr", "")
                    records.append(IngestionRecord(
                        source=self.source_name,
                        source_id=orgnr,
                        entity_type="company",
                        raw_data=company,
                        fetched_at=datetime.utcnow(),
                    ))

            return records

        except httpx.HTTPStatusError as e:
            logger.error(f"SCB API batch fetch error: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"SCB API batch request failed: {e}")
            raise

    async def count_companies(
        self,
        only_active: bool = True,
        municipality: Optional[str] = None,
        legal_form: Optional[str] = None,
    ) -> int:
        """
        Count companies matching filters.

        Args:
            only_active: Only count active companies
            municipality: 4-digit municipality code
            legal_form: Legal form code

        Returns:
            Total count of matching companies
        """
        client = await self._get_client()

        params = {}

        if only_active:
            params["Företagsstatus"] = "1"
            params["Registreringsstatus"] = "1"

        kategorier = []
        if municipality:
            kategorier.append({"Kategori": "SätesKommun", "Kod": [municipality]})
        if legal_form:
            kategorier.append({"Kategori": "Juridisk form", "Kod": [legal_form]})

        if kategorier:
            params["Kategorier"] = kategorier

        try:
            response = await client.post(
                f"{self.base_url}/api/Je/RaknaForetag",
                json=params,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()

            data = response.json()
            # Response is a simple integer
            if isinstance(data, int):
                return data
            # Or it might be a dict with count field
            if isinstance(data, dict):
                return data.get("AntalRader", data.get("Antal", 0))
            return 0

        except Exception as e:
            logger.error(f"SCB API count error: {e}")
            raise

    async def fetch_person(self, personnummer: str) -> Optional[IngestionRecord]:
        """SCB Företagsregistret doesn't contain person data."""
        return None

    async def search(
        self,
        query: str,
        limit: int = 100,
        sni_code: Optional[str] = None,
        municipality: Optional[str] = None,
        only_active: bool = True,
    ) -> AsyncIterator[IngestionRecord]:
        """
        Search companies by name or other criteria.

        Args:
            query: Company name search string (uses Innehaller/contains operator)
            limit: Maximum number of results (max 2000)
            sni_code: Filter by SNI industry code (5 digits)
            municipality: Filter by municipality code (4 digits)
            only_active: Only return active companies
        """
        client = await self._get_client()

        params = {
            "MaxAntalRader": min(limit, 2000),
        }

        if only_active:
            params["Företagsstatus"] = "1"
            params["Registreringsstatus"] = "1"

        # Add variable filters
        variabler = []
        if query:
            variabler.append({"Variabel": "Namn", "Varde": query, "Operator": "Innehaller"})

        if variabler:
            params["Variabler"] = variabler

        # Add category filters
        kategorier = []
        if municipality:
            kategorier.append({"Kategori": "SätesKommun", "Kod": [municipality]})
        if sni_code:
            kategorier.append({"Kategori": "Bransch", "Kod": [sni_code]})

        if kategorier:
            params["Kategorier"] = kategorier

        try:
            response = await client.post(
                f"{self.base_url}/api/Je/HamtaForetag",
                json=params,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()

            data = response.json()
            if isinstance(data, list):
                for company in data:
                    orgnr = company.get("OrgNr", "")
                    yield IngestionRecord(
                        source=self.source_name,
                        source_id=orgnr,
                        entity_type="company",
                        raw_data=company,
                        fetched_at=datetime.utcnow(),
                    )

        except httpx.HTTPStatusError as e:
            logger.error(f"SCB API search error: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"SCB API search request failed: {e}")
            raise

    async def get_categories(self) -> list:
        """
        Get available categories and code tables for companies (JE).

        Endpoint: /api/Je/KategorierMedKodtabeller
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"{self.base_url}/api/Je/KategorierMedKodtabeller",
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"SCB categories fetch error: {e}")
            raise

    async def get_variables(self) -> list:
        """
        Get available variables for company queries.

        Endpoint: /api/Je/Variabler
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"{self.base_url}/api/Je/Variabler",
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"SCB variables fetch error: {e}")
            raise

    async def healthcheck(self) -> bool:
        """Check if SCB API is available."""
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/help",
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"SCB healthcheck failed: {e}")
            return False

    async def close(self) -> None:
        """Close the HTTP client and cleanup temp files."""
        if self._client:
            await self._client.aclose()
            self._client = None

        # Cleanup temp PEM files
        if self._temp_dir:
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def __del__(self):
        """Cleanup on destruction."""
        if self._temp_dir:
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
