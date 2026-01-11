"""
Bolagsverket HVD (Värdefulla Datamängder / High Value Datasets) API adapter.

API for Swedish company information from Bolagsverket (Companies Registration Office).
This is the free "High Value Datasets" API providing basic company registration data.

Portal: https://portal.api.bolagsverket.se/
API Docs: https://gw.api.bolagsverket.se/vardefulla-datamangder/v1

Available endpoints:
- GET /isalive - Health check
- POST /organisationer - Company data lookup by org number
- POST /dokumentlista - List annual reports for a company
- GET /dokument/{dokumentId} - Download annual report PDF

OAuth2 Scopes:
- vardefulla-datamangder:ping - Health check access
- vardefulla-datamangder:read - Company data read access

Auth: OAuth2 Client Credentials
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, AsyncIterator, Optional

import httpx

from halo.config import settings
from halo.ingestion.base_adapter import BaseAdapter, IngestionRecord
from halo.ingestion.rate_limiter import RateLimiter, RateLimitConfig, RateLimitedClient

logger = logging.getLogger(__name__)


@dataclass
class ParsedCompany:
    """Parsed company data from Bolagsverket HVD API response."""

    orgnummer: str
    name: str
    legal_form: Optional[str] = None
    legal_form_code: Optional[str] = None
    status: Optional[str] = None
    registration_date: Optional[date] = None
    deregistration_date: Optional[date] = None
    sni_codes: list[str] = field(default_factory=list)
    sni_primary: Optional[str] = None
    address_street: Optional[str] = None
    address_postal_code: Optional[str] = None
    address_city: Optional[str] = None
    address_co: Optional[str] = None
    business_description: Optional[str] = None
    raw_data: dict = field(default_factory=dict)


def parse_hvd_response(org_data: dict) -> ParsedCompany:
    """
    Parse a Bolagsverket HVD API response into structured company data.

    The HVD API returns deeply nested JSON. This function extracts
    the relevant fields into a flat structure.

    Args:
        org_data: Raw organization data from API response

    Returns:
        ParsedCompany with extracted fields
    """
    # Extract org number
    identity = org_data.get("organisationsidentitet", {})
    orgnummer = identity.get("identitetsbeteckning", "")

    # Extract company name from nested strukture
    # organisationsnamn.organisationsnamnLista[0].namn
    names_wrapper = org_data.get("organisationsnamn", {})
    names_list = names_wrapper.get("organisationsnamnLista", [])
    name = ""
    if names_list:
        name = names_list[0].get("namn", "")

    # Extract legal form (rättslig form)
    # rattsligForm.rattsligFormKod / rattsligFormBenamning
    legal_form_wrapper = org_data.get("rattsligForm", {})
    legal_form_code = legal_form_wrapper.get("rattsligFormKod")
    legal_form = legal_form_wrapper.get("rattsligFormBenamning")

    # Extract status from juridiskForm or registreringsstatus
    status = None
    juridisk_form = org_data.get("juridiskForm", {})
    if juridisk_form:
        status = juridisk_form.get("status", juridisk_form.get("juridiskFormBenamning"))

    # Registration dates
    # registreringsDatum or from sarskildUppgiftslista
    registration_date = None
    deregistration_date = None

    reg_datum = org_data.get("registreringsDatum")
    if reg_datum:
        try:
            registration_date = datetime.strptime(reg_datum, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

    avregistrering = org_data.get("avregistreringsDatum")
    if avregistrering:
        try:
            deregistration_date = datetime.strptime(avregistrering, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

    # Extract SNI codes from verksamhet.sniKoder
    sni_codes = []
    sni_primary = None
    verksamhet = org_data.get("verksamhet", {})
    sni_data = verksamhet.get("sniKoder", verksamhet.get("sniKodLista", []))
    if isinstance(sni_data, list):
        for sni in sni_data:
            if isinstance(sni, dict):
                code = sni.get("sniKod", sni.get("kod"))
                if code:
                    sni_codes.append(code)
                    # First SNI code is typically primary
                    if not sni_primary:
                        sni_primary = code
            elif isinstance(sni, str):
                sni_codes.append(sni)
                if not sni_primary:
                    sni_primary = sni

    # Business description
    business_desc = verksamhet.get("verksamhetsbeskrivning")

    # Extract postal address
    # postadress.gatuadress, postadress.postnummer, postadress.postort
    address_street = None
    address_postal = None
    address_city = None
    address_co = None

    postadress = org_data.get("postadress", {})
    if postadress:
        address_street = postadress.get("gatuadress", postadress.get("utdelningsadress"))
        address_postal = postadress.get("postnummer")
        address_city = postadress.get("postort")
        address_co = postadress.get("coAdress")

        # Sometimes address is nested further
        if not address_street:
            utdelning = postadress.get("utdelningsadress", {})
            if isinstance(utdelning, dict):
                address_street = utdelning.get("gatuadress")

    # Try alternate address location: besoksadress
    if not address_street:
        besoksadress = org_data.get("besoksadress", {})
        if besoksadress:
            address_street = besoksadress.get("gatuadress")
            if not address_postal:
                address_postal = besoksadress.get("postnummer")
            if not address_city:
                address_city = besoksadress.get("postort")

    return ParsedCompany(
        orgnummer=orgnummer,
        name=name,
        legal_form=legal_form,
        legal_form_code=legal_form_code,
        status=status,
        registration_date=registration_date,
        deregistration_date=deregistration_date,
        sni_codes=sni_codes,
        sni_primary=sni_primary,
        address_street=address_street,
        address_postal_code=address_postal,
        address_city=address_city,
        address_co=address_co,
        business_description=business_desc,
        raw_data=org_data,
    )


@dataclass
class TokenCache:
    """Cached OAuth2 access token."""
    token: str
    expires_at: datetime


class OAuthScope(str, Enum):
    """Bolagsverket HVD OAuth2 scopes."""

    PING = "vardefulla-datamangder:ping"  # Health check
    READ = "vardefulla-datamangder:read"  # Company data access


# Bolagsverket rate limiter (conservative estimate, adjust after API docs)
BOLAGSVERKET_RATE_LIMITER = RateLimiter(
    RateLimitConfig(
        requests_per_window=50,
        window_seconds=60.0,
    )
)


class BolagsverketHVDAdapter(BaseAdapter):
    """
    Adapter for Bolagsverket HVD (Värdefulla Datamängder / High Value Datasets) API.

    This free API provides basic company registration data including:
    - Organization identity (org number, type)
    - Company name and legal form
    - Registration dates
    - SNI industry codes
    - Postal address
    - Business description
    - Annual report documents

    Authentication: OAuth2 Client Credentials flow with scopes
    """

    # API Gateway URLs
    PROD_BASE_URL = "https://gw.api.bolagsverket.se/vardefulla-datamangder/v1"
    TEST_BASE_URL = "https://gw-accept2.api.bolagsverket.se/vardefulla-datamangder/v1"

    # OAuth2 Token Endpoints
    PROD_TOKEN_URL = "https://portal.api.bolagsverket.se/oauth2/token"
    TEST_TOKEN_URL = "https://portal-accept2.api.bolagsverket.se/oauth2/token"

    # Required OAuth2 scopes
    OAUTH_SCOPES = f"{OAuthScope.PING.value} {OAuthScope.READ.value}"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        use_test: Optional[bool] = None,
        base_url: Optional[str] = None,
    ):
        """
        Initialize the Bolagsverket HVD adapter.

        Args:
            client_id: OAuth2 client ID (defaults to settings)
            client_secret: OAuth2 client secret (defaults to settings)
            use_test: Use test environment (defaults to settings)
            base_url: Override base URL (useful for testing)
        """
        self.client_id = client_id or settings.bolagsverket_client_id
        self.client_secret = client_secret or settings.bolagsverket_client_secret
        self.use_test = use_test if use_test is not None else settings.bolagsverket_use_test
        self.base_url = base_url or (self.TEST_BASE_URL if self.use_test else self.PROD_BASE_URL)

        # Token cache for OAuth2
        self._token_cache: Optional[TokenCache] = None

        if not self.client_id or not self.client_secret:
            logger.warning(
                "Bolagsverket OAuth2 credentials not configured. "
                "Set BOLAGSVERKET_CLIENT_ID and BOLAGSVERKET_CLIENT_SECRET."
            )

        # HTTP client without auth header (we'll add it dynamically)
        self._raw_client = httpx.AsyncClient(
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self._client = RateLimitedClient(self._raw_client, BOLAGSVERKET_RATE_LIMITER)

    @property
    def token_url(self) -> str:
        """Get the OAuth2 token endpoint URL based on environment."""
        return self.TEST_TOKEN_URL if self.use_test else self.PROD_TOKEN_URL

    async def _get_token(self) -> str:
        """
        Get a valid OAuth2 access token, refreshing if needed.

        Uses client credentials grant flow.
        Tokens are cached until 60 seconds before expiration.
        """
        # Return cached token if still valid
        if self._token_cache and self._token_cache.expires_at > datetime.utcnow():
            return self._token_cache.token

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Bolagsverket OAuth2 credentials not configured. "
                "Set BOLAGSVERKET_CLIENT_ID and BOLAGSVERKET_CLIENT_SECRET."
            )

        logger.debug(f"Fetching new Bolagsverket OAuth2 token from {self.token_url}")

        try:
            response = await self._raw_client.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": self.OAUTH_SCOPES,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

            # Cache token with safety margin (60 seconds before expiration)
            expires_in = data.get("expires_in", 3600)
            self._token_cache = TokenCache(
                token=data["access_token"],
                expires_at=datetime.utcnow() + timedelta(seconds=expires_in - 60),
            )

            logger.debug(f"Bolagsverket token cached, expires in {expires_in}s")
            return self._token_cache.token

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get Bolagsverket OAuth2 token: {e}")
            raise
        except KeyError as e:
            logger.error(f"Invalid OAuth2 token response: missing {e}")
            raise ValueError(f"Invalid OAuth2 token response: missing {e}")

    async def _authorized_request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """
        Make an authorized HTTP request with OAuth2 token.

        Automatically fetches/refreshes the access token as needed.
        """
        token = await self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        if method.upper() == "GET":
            return await self._client.get(url, headers=headers, **kwargs)
        elif method.upper() == "POST":
            return await self._client.post(url, headers=headers, **kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    @property
    def source_name(self) -> str:
        return "bolagsverket_hvd"

    async def fetch_company(
        self,
        orgnr: str,
    ) -> Optional[IngestionRecord]:
        """
        Fetch company details by organisationsnummer.

        Args:
            orgnr: Swedish organisation number (10 digits, no dash)

        Returns company data including:
        - Organization identity (org number, type)
        - Company name and legal form
        - Registration dates
        - SNI industry codes
        - Postal address
        - Business description
        - Active/inactive status
        """
        orgnr = orgnr.replace("-", "").replace(" ", "")

        try:
            response = await self._authorized_request(
                "POST",
                f"{self.base_url}/organisationer",
                json={"identitetsbeteckning": orgnr},
            )
            response.raise_for_status()

            data = response.json()

            # Extract the first organization from the response
            organisationer = data.get("organisationer", [])
            if not organisationer:
                logger.debug(f"Company not found: {orgnr}")
                return None

            org_data = organisationer[0]

            return IngestionRecord(
                source=self.source_name,
                source_id=orgnr,
                entity_type="company",
                raw_data=org_data,
                fetched_at=datetime.utcnow(),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Company not found: {orgnr}")
                return None
            logger.error(f"Bolagsverket HVD API error for company {orgnr}: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Bolagsverket HVD API request failed for company {orgnr}: {e}")
            raise

    async def fetch_person(self, personnummer: str) -> Optional[IngestionRecord]:
        """
        Fetch person by personnummer.

        Note: The HVD API does not support person lookups.
        Always returns None.
        """
        logger.debug("HVD API does not support person lookups")
        return None

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> AsyncIterator[IngestionRecord]:
        """
        Search companies by name.

        Note: The HVD API does not support search - only lookup by org number.
        This method yields no results.
        """
        logger.debug("HVD API does not support search - use fetch_company with org number")
        return
        yield  # Makes this a generator

    async def list_annual_reports(self, orgnr: str) -> list[dict[str, Any]]:
        """
        List available annual reports (årsredovisningar) for a company.

        Args:
            orgnr: Swedish organisation number (10 digits, no dash)

        Returns list of documents with:
        - dokumentId: ID for downloading
        - dokumentTyp: Document type
        - rakenskapsperiod: Accounting period
        """
        orgnr = orgnr.replace("-", "").replace(" ", "")

        try:
            response = await self._authorized_request(
                "POST",
                f"{self.base_url}/dokumentlista",
                json={"identitetsbeteckning": orgnr},
            )
            response.raise_for_status()

            data = response.json()
            return data.get("dokument", [])
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            logger.error(f"Bolagsverket HVD API error listing documents for {orgnr}: {e}")
            raise

    async def download_document(self, dokument_id: str) -> bytes:
        """
        Download an annual report document by ID.

        Args:
            dokument_id: Document ID from list_annual_reports

        Returns:
            PDF bytes of the annual report
        """
        try:
            response = await self._authorized_request(
                "GET",
                f"{self.base_url}/dokument/{dokument_id}",
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as e:
            logger.error(f"Bolagsverket HVD API error downloading document {dokument_id}: {e}")
            raise

    async def healthcheck(self) -> bool:
        """Check if Bolagsverket HVD API is available and credentials are valid."""
        try:
            response = await self._authorized_request(
                "GET",
                f"{self.base_url}/isalive",
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Bolagsverket HVD healthcheck failed: {e}")
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._raw_client.aclose()

    async def fetch_company_parsed(
        self,
        orgnr: str,
    ) -> Optional[ParsedCompany]:
        """
        Fetch company details and return parsed/structured data.

        This is a convenience method that fetches and parses in one call.

        Args:
            orgnr: Swedish organisation number (10 digits, no dash)

        Returns:
            ParsedCompany with extracted fields, or None if not found
        """
        record = await self.fetch_company(orgnr)
        if not record or not record.raw_data:
            return None

        return parse_hvd_response(record.raw_data)

    async def fetch_companies_batch(
        self,
        orgnummers: list[str],
    ) -> list[ParsedCompany]:
        """
        Fetch multiple companies by organisationsnummer.

        Args:
            orgnummers: List of org numbers to fetch

        Returns:
            List of ParsedCompany for found companies
        """
        results = []
        for orgnr in orgnummers:
            try:
                parsed = await self.fetch_company_parsed(orgnr)
                if parsed:
                    results.append(parsed)
            except Exception as e:
                logger.warning(f"Failed to fetch company {orgnr}: {e}")
        return results
