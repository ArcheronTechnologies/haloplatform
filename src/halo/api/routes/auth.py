"""
Authentication API routes for Halo Platform.

Provides endpoints for:
- Login (username/password)
- BankID authentication (Swedish e-ID)
- OIDC/SAML federation (identity providers)
- Token refresh
- Logout (session revocation)
- Session management
- Password validation (HIBP check)
"""

import hashlib
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from pydantic import BaseModel, Field

from halo.config import settings
from halo.security.auth import (
    User,
    UserRole,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_access_token,
    verify_refresh_token,
    AuthenticationError,
)
from halo.security.sessions import SessionManager, get_session_manager
from halo.security.lockout import LockoutManager, LockoutAction, LockoutResult, get_lockout_manager
from halo.security.bankid import (
    BankIDClient,
    BankIDAuthenticator,
    BankIDUser,
    BankIDOrder,
    BankIDError,
    BankIDUserCancelledError,
    BankIDExpiredError,
    BankIDStatus,
    get_bankid_client,
)
from halo.api.deps import UserRepo
from halo.security.oidc import (
    OIDCClient,
    OIDCConfiguration,
    OIDCUser,
    OIDCTokens,
    OIDCError,
    OIDCProvider,
    OIDCProviderFactory,
    OIDCStateStore,
    get_oidc_state_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# Request/Response Models
class LoginRequest(BaseModel):
    """Login request body."""

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)
    captcha_token: Optional[str] = None  # Required if lockout requires CAPTCHA


class LoginResponse(BaseModel):
    """Login response with tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


class RefreshResponse(BaseModel):
    """Token refresh response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SessionInfo(BaseModel):
    """Session information."""

    session_id: str
    device_info: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    last_accessed: Optional[datetime]
    is_current: bool = False


class SessionListResponse(BaseModel):
    """List of user sessions."""

    sessions: list[SessionInfo]
    total: int


class PasswordCheckRequest(BaseModel):
    """Password breach check request."""

    password: str = Field(..., min_length=1, max_length=200)


class PasswordCheckResponse(BaseModel):
    """Password breach check response."""

    breached: bool
    breach_count: int = 0
    message: str


# BankID Request/Response Models
class BankIDInitRequest(BaseModel):
    """BankID authentication initiation request."""

    personnummer: Optional[str] = Field(None, pattern=r"^\d{12}$")


class BankIDInitResponse(BaseModel):
    """BankID authentication initiation response."""

    order_ref: str
    auto_start_token: str
    qr_start_token: str
    qr_start_secret: str
    auto_start_url: str


class BankIDQRRequest(BaseModel):
    """Request for QR code data."""

    order_ref: str
    qr_start_token: str
    qr_start_secret: str
    created_at: datetime


class BankIDQRResponse(BaseModel):
    """QR code data response."""

    qr_data: str  # String to encode in QR code


class BankIDCollectRequest(BaseModel):
    """BankID collect/poll request."""

    order_ref: str


class BankIDCollectResponse(BaseModel):
    """BankID collect/poll response."""

    status: str  # pending, complete, failed
    hint_code: Optional[str] = None
    # Only present when status == complete
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user_name: Optional[str] = None
    personnummer_masked: Optional[str] = None  # Show only last 4 digits


class BankIDCancelRequest(BaseModel):
    """BankID cancel request."""

    order_ref: str


# OIDC Request/Response Models
class OIDCAuthRequest(BaseModel):
    """OIDC authentication initiation request."""

    provider: str = Field(..., description="Provider: signicat, azure_ad, okta, custom")
    redirect_after: Optional[str] = Field(None, description="URL to redirect after auth")


class OIDCAuthResponse(BaseModel):
    """OIDC authentication initiation response."""

    auth_url: str
    state: str  # For correlation


class OIDCCallbackRequest(BaseModel):
    """OIDC callback processing request."""

    code: str
    state: str


class OIDCCallbackResponse(BaseModel):
    """OIDC callback response with tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_name: Optional[str] = None
    email: Optional[str] = None
    personnummer_masked: Optional[str] = None


# In-memory storage for pending BankID orders (use Redis in production)
_pending_bankid_orders: dict[str, BankIDOrder] = {}


# Helper functions
def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    # Check for forwarded headers (behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_device_info(request: Request) -> str:
    """Extract device info from request headers."""
    user_agent = request.headers.get("User-Agent", "unknown")
    # Truncate for storage
    return user_agent[:200] if user_agent else "unknown"


async def check_hibp(password: str) -> tuple[bool, int]:
    """
    Check password against Have I Been Pwned API using k-anonymity.

    Returns (is_breached, breach_count)
    """
    # Hash password with SHA-1 (HIBP requirement)
    sha1_hash = hashlib.sha1(password.encode()).hexdigest().upper()
    prefix = sha1_hash[:5]
    suffix = sha1_hash[5:]

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.pwnedpasswords.com/range/{prefix}",
                headers={"Add-Padding": "true"},  # Prevent timing attacks
                timeout=5.0,
            )

            if response.status_code != 200:
                logger.warning(f"HIBP API returned {response.status_code}")
                return False, 0

            # Check if our suffix is in the response
            for line in response.text.splitlines():
                parts = line.split(":")
                if len(parts) == 2:
                    hash_suffix, count = parts
                    if hash_suffix == suffix:
                        return True, int(count)

            return False, 0

    except Exception as e:
        logger.error(f"HIBP check failed: {e}")
        return False, 0


# Endpoints
@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: LoginRequest,
    user_repo: UserRepo,
    session_manager: SessionManager = Depends(get_session_manager),
    lockout_manager: LockoutManager = Depends(get_lockout_manager),
):
    """
    Authenticate user and issue tokens.

    Returns access and refresh tokens on success.
    Implements lockout protection against brute force.
    """
    client_ip = get_client_ip(request)

    # Look up user from database
    db_user = await user_repo.get_by_username(body.username)

    # Verify password if user exists
    auth_success = False
    if db_user is not None and db_user.is_active:
        auth_success = verify_password(body.password, db_user.password_hash)

    # Update login tracking
    if auth_success:
        await user_repo.update_last_login(db_user.id, client_ip)
    elif db_user is not None:
        await user_repo.increment_failed_attempts(db_user.id)

    # Check lockout and record attempt
    lockout_result = await lockout_manager.check_and_record(
        username=body.username,
        ip_address=client_ip,
        success=auth_success,
    )

    if lockout_result.action == LockoutAction.BLOCK:
        raise HTTPException(
            status_code=429,
            detail="Kontot är tillfälligt låst. Försök igen senare.",
            headers={"Retry-After": str(lockout_result.block_expires_in or 1800)},
        )

    if lockout_result.action == LockoutAction.CAPTCHA:
        if not body.captcha_token:
            raise HTTPException(
                status_code=428,
                detail="CAPTCHA krävs för att fortsätta.",
                headers={"X-Captcha-Required": "true"},
            )
        # In production, verify captcha_token here

    if not auth_success:
        raise HTTPException(
            status_code=401,
            detail="Felaktigt användarnamn eller lösenord.",
        )

    # Create user object for token
    auth_user = User(
        id=str(db_user.id) if db_user else "placeholder",
        username=body.username,
        role=UserRole.ANALYST,  # Get from user record
    )

    # Generate tokens
    access_token = create_access_token(auth_user)
    refresh_token = create_refresh_token(auth_user)

    # Create session
    device_info = get_device_info(request)
    await session_manager.create_session(
        user_id=auth_user.id,
        access_token=access_token,
        refresh_token=refresh_token,
        device_info=device_info,
        ip_address=client_ip,
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Refresh access token using refresh token.
    """
    try:
        payload = verify_refresh_token(body.refresh_token)
    except AuthenticationError:
        raise HTTPException(
            status_code=401,
            detail="Ogiltig eller utgången refresh-token.",
        )

    # Validate session
    session = await session_manager.validate_session(body.refresh_token)
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Sessionen har avslutats.",
        )

    # Create new access token
    user = User(
        id=payload.sub,
        username="",  # Not needed for token
        role=payload.role,
    )
    new_access_token = create_access_token(user)

    # Refresh session
    await session_manager.refresh_session(
        user_id=payload.sub,
        old_refresh_token=body.refresh_token,
        new_access_token=new_access_token,
    )

    return RefreshResponse(
        access_token=new_access_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout")
async def logout(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Logout current session (revoke tokens).
    """
    # Get token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token saknas.")

    token = auth_header[7:]

    try:
        payload = verify_access_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Ogiltig token.")

    # Revoke session
    await session_manager.revoke_session(payload.sub, token)

    return {"message": "Utloggad."}


@router.post("/logout/all")
async def logout_all_sessions(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Logout all sessions for current user (emergency revocation).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token saknas.")

    token = auth_header[7:]

    try:
        payload = verify_access_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Ogiltig token.")

    # Revoke all sessions
    revoked_count = await session_manager.revoke_all_sessions(payload.sub)

    return {
        "message": f"Alla sessioner avslutade.",
        "revoked_count": revoked_count,
    }


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    List all active sessions for current user.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token saknas.")

    token = auth_header[7:]

    try:
        payload = verify_access_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Ogiltig token.")

    # Get sessions
    sessions = await session_manager.get_user_sessions(payload.sub)

    # Format response
    session_list = []
    for s in sessions:
        session_list.append(
            SessionInfo(
                session_id=s.get("session_id", ""),
                device_info=s.get("device_info"),
                ip_address=s.get("ip_address"),
                created_at=s.get("created_at", datetime.utcnow()),
                last_accessed=s.get("last_accessed"),
                is_current=s.get("is_current", False),
            )
        )

    return SessionListResponse(
        sessions=session_list,
        total=len(session_list),
    )


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Revoke a specific session by ID.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token saknas.")

    token = auth_header[7:]

    try:
        payload = verify_access_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Ogiltig token.")

    # Revoke specific session
    success = await session_manager.revoke_session_by_id(payload.sub, session_id)

    if not success:
        raise HTTPException(status_code=404, detail="Sessionen hittades inte.")

    return {"message": "Sessionen avslutad."}


@router.post("/password/check", response_model=PasswordCheckResponse)
async def check_password_breach(body: PasswordCheckRequest):
    """
    Check if a password has been exposed in known data breaches.

    Uses Have I Been Pwned API with k-anonymity (password never sent).
    """
    is_breached, count = await check_hibp(body.password)

    if is_breached:
        return PasswordCheckResponse(
            breached=True,
            breach_count=count,
            message=f"Detta lösenord har förekommit i {count:,} dataintrång. Välj ett annat lösenord.",
        )

    return PasswordCheckResponse(
        breached=False,
        breach_count=0,
        message="Lösenordet har inte hittats i kända dataintrång.",
    )


@router.get("/health")
async def auth_health():
    """Health check for auth service."""
    return {"status": "ok", "service": "auth"}


# =============================================================================
# BankID Authentication Endpoints
# =============================================================================

@router.post("/bankid/init", response_model=BankIDInitResponse)
async def bankid_init(
    request: Request,
    body: BankIDInitRequest,
    bankid_client: BankIDClient = Depends(get_bankid_client),
):
    """
    Initiera BankID-autentisering.

    Returnerar tokens för att starta BankID-appen eller visa QR-kod.
    Klienten måste sedan polla /bankid/collect för att få resultatet.
    """
    client_ip = get_client_ip(request)

    try:
        order = await bankid_client.auth(
            end_user_ip=client_ip,
            personnummer=body.personnummer,
        )

        # Store order for later collect calls
        _pending_bankid_orders[order.order_ref] = order

        # Generate auto-start URL
        auto_start_url = bankid_client.generate_auto_start_url(order)

        logger.info(f"BankID auth initiated: {order.order_ref[:8]}...")

        return BankIDInitResponse(
            order_ref=order.order_ref,
            auto_start_token=order.auto_start_token,
            qr_start_token=order.qr_start_token,
            qr_start_secret=order.qr_start_secret,
            auto_start_url=auto_start_url,
        )

    except BankIDError as e:
        logger.error(f"BankID init failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"BankID-tjänsten kunde inte nås: {e.details}",
        )


@router.post("/bankid/qr", response_model=BankIDQRResponse)
async def bankid_qr(
    body: BankIDQRRequest,
    bankid_client: BankIDClient = Depends(get_bankid_client),
):
    """
    Generera QR-kodsdata för animerad BankID QR-kod.

    Anropas varje sekund för att uppdatera QR-koden.
    """
    order = BankIDOrder(
        order_ref=body.order_ref,
        auto_start_token="",  # Not needed for QR
        qr_start_token=body.qr_start_token,
        qr_start_secret=body.qr_start_secret,
        created_at=body.created_at,
    )

    qr_data = bankid_client.generate_qr_code_data(order)

    return BankIDQRResponse(qr_data=qr_data)


@router.post("/bankid/collect", response_model=BankIDCollectResponse)
async def bankid_collect(
    request: Request,
    body: BankIDCollectRequest,
    bankid_client: BankIDClient = Depends(get_bankid_client),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Polla BankID-status.

    Returnerar pending tills användaren autentiserat sig,
    sedan complete med tokens eller failed med felkod.
    """
    try:
        status, user, hint_code = await bankid_client.collect(body.order_ref)

        if status == BankIDStatus.PENDING:
            return BankIDCollectResponse(
                status="pending",
                hint_code=hint_code,
            )

        elif status == BankIDStatus.COMPLETE:
            # Clean up pending order
            _pending_bankid_orders.pop(body.order_ref, None)

            # Create or get user from database
            # TODO: Look up or create user by personnummer
            # db_user = await get_or_create_user_by_personnummer(user.personnummer)

            # Create auth user for tokens
            auth_user = User(
                id=str(uuid4()),  # Replace with DB user ID
                username=user.personnummer,  # Use personnummer as username
                role=UserRole.ANALYST,  # Get from DB
            )

            # Generate tokens
            access_token = create_access_token(auth_user)
            refresh_token = create_refresh_token(auth_user)

            # Create session
            client_ip = get_client_ip(request)
            device_info = get_device_info(request)
            await session_manager.create_session(
                user_id=auth_user.id,
                access_token=access_token,
                refresh_token=refresh_token,
                device_info=f"BankID: {device_info}",
                ip_address=client_ip,
            )

            # Mask personnummer for response
            masked_pnr = f"********{user.personnummer[-4:]}"

            logger.info(f"BankID auth complete: {masked_pnr}")

            return BankIDCollectResponse(
                status="complete",
                access_token=access_token,
                refresh_token=refresh_token,
                user_name=user.name,
                personnummer_masked=masked_pnr,
            )

        else:  # FAILED
            # Clean up pending order
            _pending_bankid_orders.pop(body.order_ref, None)

            return BankIDCollectResponse(
                status="failed",
                hint_code=hint_code,
            )

    except BankIDUserCancelledError:
        _pending_bankid_orders.pop(body.order_ref, None)
        return BankIDCollectResponse(
            status="failed",
            hint_code="userCancel",
        )

    except BankIDExpiredError:
        _pending_bankid_orders.pop(body.order_ref, None)
        return BankIDCollectResponse(
            status="failed",
            hint_code="expiredTransaction",
        )

    except BankIDError as e:
        logger.error(f"BankID collect failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"BankID-fel: {e.details}",
        )


@router.post("/bankid/cancel")
async def bankid_cancel(
    body: BankIDCancelRequest,
    bankid_client: BankIDClient = Depends(get_bankid_client),
):
    """
    Avbryt pågående BankID-autentisering.
    """
    try:
        await bankid_client.cancel(body.order_ref)
        _pending_bankid_orders.pop(body.order_ref, None)
        return {"message": "BankID-autentisering avbruten."}

    except BankIDError as e:
        # Already cancelled or expired - that's fine
        _pending_bankid_orders.pop(body.order_ref, None)
        return {"message": "BankID-autentisering redan avslutad."}


# =============================================================================
# OIDC Authentication Endpoints
# =============================================================================

@router.post("/oidc/init", response_model=OIDCAuthResponse)
async def oidc_init(
    body: OIDCAuthRequest,
    state_store: OIDCStateStore = Depends(get_oidc_state_store),
):
    """
    Initiera OIDC-autentisering.

    Returnerar URL för omdirigering till identity provider.
    """
    # Map provider string to enum
    provider_map = {
        "signicat": OIDCProvider.SIGNICAT,
        "azure_ad": OIDCProvider.AZURE_AD,
        "okta": OIDCProvider.OKTA,
        "freja": OIDCProvider.FREJA,
        "siths": OIDCProvider.SITHS,
        "custom": OIDCProvider.CUSTOM,
    }

    provider = provider_map.get(body.provider.lower())
    if not provider:
        raise HTTPException(
            status_code=400,
            detail=f"Okänd provider: {body.provider}. Tillgängliga: {list(provider_map.keys())}",
        )

    # Get provider config from settings
    client_id = getattr(settings, f"oidc_{body.provider}_client_id", None)
    client_secret = getattr(settings, f"oidc_{body.provider}_client_secret", None)
    issuer = getattr(settings, f"oidc_{body.provider}_issuer", None)

    if not client_id:
        raise HTTPException(
            status_code=501,
            detail=f"OIDC provider '{body.provider}' är inte konfigurerad.",
        )

    try:
        # Create OIDC client
        redirect_uri = f"{settings.base_url}/api/v1/auth/oidc/callback"
        client = await OIDCProviderFactory.create(
            provider=provider,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            issuer=issuer,
        )

        # Generate auth URL
        auth_url, state, nonce, code_verifier = client.generate_auth_url()

        # Store state for callback validation
        extra_data = {"redirect_after": body.redirect_after} if body.redirect_after else {}
        state_store.save(state, nonce, code_verifier, extra_data)

        logger.info(f"OIDC auth initiated for provider: {body.provider}")

        return OIDCAuthResponse(
            auth_url=auth_url,
            state=state,
        )

    except OIDCError as e:
        logger.error(f"OIDC init failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Kunde inte initiera OIDC: {str(e)}",
        )


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    code: str,
    state: str,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    state_store: OIDCStateStore = Depends(get_oidc_state_store),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    OIDC callback endpoint.

    Hanterar redirect från identity provider efter autentisering.
    """
    # Handle error response from provider
    if error:
        logger.warning(f"OIDC callback error: {error} - {error_description}")
        raise HTTPException(
            status_code=401,
            detail=f"Autentisering misslyckades: {error_description or error}",
        )

    # Retrieve and validate state
    stored = state_store.get(state)
    if not stored:
        raise HTTPException(
            status_code=400,
            detail="Ogiltig eller utgången state-parameter.",
        )

    nonce = stored["nonce"]
    code_verifier = stored["code_verifier"]
    extra_data = stored.get("extra_data", {})

    # TODO: Recreate OIDC client based on which provider initiated this flow
    # For now, we'll need to store the provider in the state or use a single provider

    # This is a simplified implementation - in production you'd:
    # 1. Store provider info in state
    # 2. Recreate the appropriate OIDCClient
    # 3. Exchange code for tokens
    # 4. Validate ID token
    # 5. Create/lookup user and session

    # Placeholder response - redirect to frontend with tokens
    redirect_after = extra_data.get("redirect_after", "/")

    # In a full implementation, you would:
    # tokens = await client.exchange_code(code, code_verifier)
    # user = await client.get_userinfo(tokens.access_token)
    # ... create session and tokens ...

    logger.info(f"OIDC callback received for state: {state[:8]}...")

    # For now, return a message - full implementation requires the client recreation
    return {
        "message": "OIDC callback received",
        "note": "Full implementation requires storing provider info in state",
        "redirect_after": redirect_after,
    }


@router.post("/oidc/token", response_model=OIDCCallbackResponse)
async def oidc_token_exchange(
    request: Request,
    body: OIDCCallbackRequest,
    state_store: OIDCStateStore = Depends(get_oidc_state_store),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Utbyt OIDC authorization code mot tokens.

    Används av SPA som hanterar callback själv.
    """
    # Retrieve and validate state
    stored = state_store.get(body.state)
    if not stored:
        raise HTTPException(
            status_code=400,
            detail="Ogiltig eller utgången state-parameter.",
        )

    nonce = stored["nonce"]
    code_verifier = stored["code_verifier"]

    # TODO: Implement full token exchange
    # This requires knowing which provider to use, which should be stored in state

    raise HTTPException(
        status_code=501,
        detail="Token exchange not fully implemented - use callback endpoint with provider config.",
    )


@router.get("/oidc/providers")
async def list_oidc_providers():
    """
    Lista tillgängliga OIDC-providers.
    """
    providers = []

    # Check which providers are configured
    for provider_name in ["signicat", "azure_ad", "okta", "freja", "siths"]:
        client_id = getattr(settings, f"oidc_{provider_name}_client_id", None)
        if client_id:
            providers.append({
                "id": provider_name,
                "name": provider_name.replace("_", " ").title(),
                "enabled": True,
            })

    return {"providers": providers}
