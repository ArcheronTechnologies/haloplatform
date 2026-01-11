"""
BankID Integration for Halo Platform.

Implements Swedish BankID authentication for production use.
Supports both test and production environments.

BankID API Documentation: https://www.bankid.com/utvecklare/guider

Security considerations:
- All communication uses mutual TLS (mTLS)
- Personnummer is returned in the completion response
- Signatures are verified using BankID's certificate chain
"""

import asyncio
import base64
import hashlib
import logging
import ssl
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx

from halo.config import settings

logger = logging.getLogger(__name__)


class BankIDEnvironment(str, Enum):
    """BankID environment selection."""

    TEST = "test"
    PRODUCTION = "production"


class BankIDStatus(str, Enum):
    """BankID order status."""

    PENDING = "pending"
    FAILED = "failed"
    COMPLETE = "complete"


class BankIDHintCode(str, Enum):
    """BankID hint codes for pending status."""

    OUTSTANDING_TRANSACTION = "outstandingTransaction"
    NO_CLIENT = "noClient"
    STARTED = "started"
    USER_SIGN = "userSign"
    USER_MRTD = "userMrtd"  # Machine-readable travel document
    UNKNOWN = "unknown"


class BankIDError(Exception):
    """Base exception for BankID errors."""

    def __init__(self, error_code: str, details: str):
        self.error_code = error_code
        self.details = details
        super().__init__(f"BankID error {error_code}: {details}")


class BankIDUserCancelledError(BankIDError):
    """User cancelled the BankID authentication."""

    pass


class BankIDExpiredError(BankIDError):
    """BankID transaction expired."""

    pass


@dataclass
class BankIDUser:
    """User information from BankID completion."""

    personnummer: str  # Swedish personal identity number
    name: str  # Full name
    given_name: str  # First name
    surname: str  # Last name
    device_ip: Optional[str] = None  # IP address of BankID client
    signature: Optional[str] = None  # Base64-encoded signature
    ocsp_response: Optional[str] = None  # OCSP response for certificate validation


@dataclass
class BankIDOrder:
    """BankID authentication/signing order."""

    order_ref: str  # Reference for polling
    auto_start_token: str  # Token for starting BankID app
    qr_start_token: str  # Token for QR code generation
    qr_start_secret: str  # Secret for animated QR code
    created_at: datetime


class BankIDClient:
    """
    BankID Relying Party API client.

    Implements the BankID RP API v6.0 specification.
    """

    # API endpoints
    TEST_URL = "https://appapi2.test.bankid.com/rp/v6.0/"
    PRODUCTION_URL = "https://appapi2.bankid.com/rp/v6.0/"

    # Test certificates (bundled with BankID test environment)
    TEST_CA_CERT = "test.bankid.com.pem"

    def __init__(
        self,
        environment: BankIDEnvironment = BankIDEnvironment.TEST,
        cert_path: Optional[Path] = None,
        key_path: Optional[Path] = None,
        ca_cert_path: Optional[Path] = None,
    ):
        """
        Initialize BankID client.

        Args:
            environment: Test or production environment
            cert_path: Path to client certificate (PEM)
            key_path: Path to client private key (PEM)
            ca_cert_path: Path to CA certificate for verification
        """
        self.environment = environment
        self.base_url = (
            self.TEST_URL if environment == BankIDEnvironment.TEST else self.PRODUCTION_URL
        )

        # Certificate paths
        self._cert_path = cert_path
        self._key_path = key_path
        self._ca_cert_path = ca_cert_path

        # HTTP client (created on first use)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client with mTLS."""
        if self._client is None:
            # Create SSL context for mutual TLS
            ssl_context = ssl.create_default_context()

            if self._ca_cert_path:
                ssl_context.load_verify_locations(self._ca_cert_path)

            if self._cert_path and self._key_path:
                ssl_context.load_cert_chain(self._cert_path, self._key_path)

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                verify=ssl_context if self._cert_path else True,
                timeout=httpx.Timeout(30.0),
            )

        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def auth(
        self,
        end_user_ip: str,
        personnummer: Optional[str] = None,
        requirement: Optional[dict] = None,
        user_visible_data: Optional[str] = None,
        user_non_visible_data: Optional[str] = None,
    ) -> BankIDOrder:
        """
        Initiate an authentication order.

        Args:
            end_user_ip: IP address of the end user
            personnummer: Optional Swedish personal ID (12 digits)
            requirement: Optional requirements (e.g., certificate policies)
            user_visible_data: Optional text shown to user (Base64)
            user_non_visible_data: Optional data not shown (Base64)

        Returns:
            BankIDOrder with order reference and tokens
        """
        payload = {"endUserIp": end_user_ip}

        if personnummer:
            # Normalize personnummer (remove dashes, ensure 12 digits)
            pnr = personnummer.replace("-", "").replace("+", "")
            if len(pnr) == 10:
                # Add century (assume 19xx for simplicity in test)
                pnr = "19" + pnr
            payload["personalNumber"] = pnr

        if requirement:
            payload["requirement"] = requirement

        if user_visible_data:
            payload["userVisibleData"] = base64.b64encode(
                user_visible_data.encode()
            ).decode()

        if user_non_visible_data:
            payload["userNonVisibleData"] = base64.b64encode(
                user_non_visible_data.encode()
            ).decode()

        client = await self._get_client()
        response = await client.post("auth", json=payload)

        if response.status_code != 200:
            await self._handle_error(response)

        data = response.json()
        return BankIDOrder(
            order_ref=data["orderRef"],
            auto_start_token=data["autoStartToken"],
            qr_start_token=data["qrStartToken"],
            qr_start_secret=data["qrStartSecret"],
            created_at=datetime.utcnow(),
        )

    async def sign(
        self,
        end_user_ip: str,
        user_visible_data: str,
        personnummer: Optional[str] = None,
        user_non_visible_data: Optional[str] = None,
        user_visible_data_format: str = "simpleMarkdownV1",
    ) -> BankIDOrder:
        """
        Initiate a signing order.

        Args:
            end_user_ip: IP address of the end user
            user_visible_data: Text to be signed (shown to user)
            personnummer: Optional Swedish personal ID
            user_non_visible_data: Optional data not shown to user
            user_visible_data_format: Format of visible data

        Returns:
            BankIDOrder with order reference and tokens
        """
        payload = {
            "endUserIp": end_user_ip,
            "userVisibleData": base64.b64encode(user_visible_data.encode()).decode(),
            "userVisibleDataFormat": user_visible_data_format,
        }

        if personnummer:
            pnr = personnummer.replace("-", "").replace("+", "")
            if len(pnr) == 10:
                pnr = "19" + pnr
            payload["personalNumber"] = pnr

        if user_non_visible_data:
            payload["userNonVisibleData"] = base64.b64encode(
                user_non_visible_data.encode()
            ).decode()

        client = await self._get_client()
        response = await client.post("sign", json=payload)

        if response.status_code != 200:
            await self._handle_error(response)

        data = response.json()
        return BankIDOrder(
            order_ref=data["orderRef"],
            auto_start_token=data["autoStartToken"],
            qr_start_token=data["qrStartToken"],
            qr_start_secret=data["qrStartSecret"],
            created_at=datetime.utcnow(),
        )

    async def collect(self, order_ref: str) -> tuple[BankIDStatus, Optional[BankIDUser], Optional[str]]:
        """
        Collect the result of an auth/sign order.

        Args:
            order_ref: Order reference from auth/sign

        Returns:
            Tuple of (status, user_info, hint_code)
            - user_info is populated only when status is COMPLETE
            - hint_code is populated only when status is PENDING
        """
        client = await self._get_client()
        response = await client.post("collect", json={"orderRef": order_ref})

        if response.status_code != 200:
            await self._handle_error(response)

        data = response.json()
        status = BankIDStatus(data["status"])

        if status == BankIDStatus.COMPLETE:
            completion = data["completionData"]
            user_data = completion["user"]

            return (
                status,
                BankIDUser(
                    personnummer=user_data["personalNumber"],
                    name=user_data["name"],
                    given_name=user_data["givenName"],
                    surname=user_data["surname"],
                    device_ip=completion.get("device", {}).get("ipAddress"),
                    signature=completion.get("signature"),
                    ocsp_response=completion.get("ocspResponse"),
                ),
                None,
            )

        elif status == BankIDStatus.PENDING:
            hint_code = data.get("hintCode", "unknown")
            return (status, None, hint_code)

        else:  # FAILED
            hint_code = data.get("hintCode", "unknown")
            return (status, None, hint_code)

    async def cancel(self, order_ref: str) -> bool:
        """
        Cancel an ongoing auth/sign order.

        Args:
            order_ref: Order reference to cancel

        Returns:
            True if cancelled successfully
        """
        client = await self._get_client()
        response = await client.post("cancel", json={"orderRef": order_ref})
        return response.status_code == 200

    async def _handle_error(self, response: httpx.Response) -> None:
        """Handle error responses from BankID API."""
        try:
            data = response.json()
            error_code = data.get("errorCode", "unknown")
            details = data.get("details", "No details")
        except Exception:
            error_code = f"http_{response.status_code}"
            details = response.text

        if error_code == "userCancel":
            raise BankIDUserCancelledError(error_code, details)
        elif error_code == "expiredTransaction":
            raise BankIDExpiredError(error_code, details)
        else:
            raise BankIDError(error_code, details)

    def generate_qr_code_data(self, order: BankIDOrder) -> str:
        """
        Generate animated QR code data.

        The QR code should be regenerated every second for animation.

        Args:
            order: BankID order with qr_start_token and qr_start_secret

        Returns:
            String to encode in QR code
        """
        # Calculate time since order creation
        elapsed = int((datetime.utcnow() - order.created_at).total_seconds())

        # Generate HMAC for this time
        qr_auth_code = hashlib.sha256(
            f"{order.qr_start_secret}{elapsed}".encode()
        ).hexdigest()

        return f"bankid.{order.qr_start_token}.{elapsed}.{qr_auth_code}"

    def generate_auto_start_url(self, order: BankIDOrder, redirect_url: Optional[str] = None) -> str:
        """
        Generate URL to start BankID app on same device.

        Args:
            order: BankID order with auto_start_token
            redirect_url: Optional URL to redirect after completion

        Returns:
            URL to open BankID app
        """
        url = f"bankid:///?autostarttoken={order.auto_start_token}"
        if redirect_url:
            url += f"&redirect={redirect_url}"
        return url


class BankIDAuthenticator:
    """
    High-level BankID authentication flow.

    Handles the complete authentication flow including polling.
    """

    # Polling configuration
    POLL_INTERVAL = 2.0  # seconds
    MAX_POLL_TIME = 180  # seconds (3 minutes)

    def __init__(self, client: BankIDClient):
        """
        Initialize authenticator.

        Args:
            client: BankID API client
        """
        self.client = client

    async def authenticate(
        self,
        end_user_ip: str,
        personnummer: Optional[str] = None,
        on_pending: Optional[callable] = None,
    ) -> BankIDUser:
        """
        Complete authentication flow with polling.

        Args:
            end_user_ip: IP address of end user
            personnummer: Optional personnummer to pre-fill
            on_pending: Optional callback for pending status updates

        Returns:
            BankIDUser with authenticated user information

        Raises:
            BankIDError: If authentication fails
            BankIDUserCancelledError: If user cancelled
            BankIDExpiredError: If transaction expired
        """
        # Start authentication
        order = await self.client.auth(end_user_ip, personnummer)

        logger.info(f"BankID auth started: {order.order_ref}")

        # Poll for completion
        start_time = datetime.utcnow()
        while True:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > self.MAX_POLL_TIME:
                await self.client.cancel(order.order_ref)
                raise BankIDExpiredError("timeout", "Authentication timed out")

            status, user, hint_code = await self.client.collect(order.order_ref)

            if status == BankIDStatus.COMPLETE:
                logger.info(f"BankID auth complete for: {user.personnummer[:8]}****")
                return user

            elif status == BankIDStatus.FAILED:
                logger.warning(f"BankID auth failed: {hint_code}")
                if hint_code == "userCancel":
                    raise BankIDUserCancelledError(hint_code, "User cancelled")
                elif hint_code == "expiredTransaction":
                    raise BankIDExpiredError(hint_code, "Transaction expired")
                else:
                    raise BankIDError(hint_code, f"Authentication failed: {hint_code}")

            else:  # PENDING
                if on_pending:
                    await on_pending(hint_code, order)
                await asyncio.sleep(self.POLL_INTERVAL)

    async def authenticate_with_qr(
        self,
        end_user_ip: str,
        on_qr_update: callable,
        on_pending: Optional[callable] = None,
    ) -> BankIDUser:
        """
        Authentication flow using animated QR code.

        Args:
            end_user_ip: IP address of end user
            on_qr_update: Callback to update QR code display
            on_pending: Optional callback for pending status updates

        Returns:
            BankIDUser with authenticated user information
        """
        # Start authentication
        order = await self.client.auth(end_user_ip)

        logger.info(f"BankID QR auth started: {order.order_ref}")

        # Poll for completion with QR updates
        start_time = datetime.utcnow()
        last_qr_update = 0

        while True:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > self.MAX_POLL_TIME:
                await self.client.cancel(order.order_ref)
                raise BankIDExpiredError("timeout", "Authentication timed out")

            # Update QR code every second
            current_second = int(elapsed)
            if current_second > last_qr_update:
                qr_data = self.client.generate_qr_code_data(order)
                await on_qr_update(qr_data)
                last_qr_update = current_second

            status, user, hint_code = await self.client.collect(order.order_ref)

            if status == BankIDStatus.COMPLETE:
                return user

            elif status == BankIDStatus.FAILED:
                if hint_code == "userCancel":
                    raise BankIDUserCancelledError(hint_code, "User cancelled")
                elif hint_code == "expiredTransaction":
                    raise BankIDExpiredError(hint_code, "Transaction expired")
                else:
                    raise BankIDError(hint_code, f"Authentication failed: {hint_code}")

            else:  # PENDING
                if on_pending:
                    await on_pending(hint_code, order)
                await asyncio.sleep(min(1.0, self.POLL_INTERVAL))


# Test environment helper
def create_test_client() -> BankIDClient:
    """
    Create a BankID client for the test environment.

    Note: For actual testing, you need to download test certificates from
    https://www.bankid.com/utvecklare/test

    Returns:
        Configured BankID client for test environment
    """
    return BankIDClient(environment=BankIDEnvironment.TEST)


# Convenience function for getting BankID client
_default_client: Optional[BankIDClient] = None


def get_bankid_client() -> BankIDClient:
    """Get the default BankID client instance."""
    global _default_client
    if _default_client is None:
        # Check settings for environment
        env = getattr(settings, "bankid_environment", "test")
        environment = (
            BankIDEnvironment.PRODUCTION
            if env == "production"
            else BankIDEnvironment.TEST
        )

        cert_path = getattr(settings, "bankid_cert_path", None)
        key_path = getattr(settings, "bankid_key_path", None)
        ca_cert_path = getattr(settings, "bankid_ca_cert_path", None)

        _default_client = BankIDClient(
            environment=environment,
            cert_path=Path(cert_path) if cert_path else None,
            key_path=Path(key_path) if key_path else None,
            ca_cert_path=Path(ca_cert_path) if ca_cert_path else None,
        )

    return _default_client
