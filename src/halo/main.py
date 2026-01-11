"""
Halo - Swedish-Sovereign Intelligence Platform

FastAPI application entry point with security hardening.
"""

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import redis.asyncio as redis
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.middleware.base import BaseHTTPMiddleware

from halo.config import settings
from halo.security.middleware import (
    SessionAuthMiddleware,
    CSRFMiddleware,
    RequestSanitizerMiddleware,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[
    f"{settings.rate_limit_requests}/{settings.rate_limit_window_seconds}seconds"
])


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent DoS attacks."""

    # Default: 10MB max request body
    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB

    # Per-endpoint limits (path prefix -> max bytes)
    ENDPOINT_LIMITS = {
        "/api/v1/documents": 50 * 1024 * 1024,  # 50MB for document uploads
        "/api/v1/auth": 1 * 1024,  # 1KB for auth endpoints
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        # Determine limit for this endpoint
        max_size = self.MAX_BODY_SIZE
        for prefix, limit in self.ENDPOINT_LIMITS.items():
            if request.url.path.startswith(prefix):
                max_size = limit
                break

        # Check Content-Length header
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_size:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "Request entity too large",
                            "message": f"Request body exceeds maximum size of {max_size // 1024}KB",
                            "max_size_bytes": max_size,
                        },
                    )
            except ValueError:
                pass

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS protection (legacy but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self';"
        )

        # Permissions Policy (restrict browser features)
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # HSTS (only in production with HTTPS)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Remove server header
        if "server" in response.headers:
            del response.headers["server"]

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log requests for security auditing."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()

        # Generate request ID
        request_id = request.headers.get("X-Request-ID", f"req_{int(time.time() * 1000)}")

        # Log request (excluding sensitive headers)
        logger.info(
            f"Request: {request.method} {request.url.path} "
            f"[{request_id}] from {request.client.host if request.client else 'unknown'}"
        )

        response = await call_next(request)

        # Log response time
        process_time = time.time() - start_time
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(process_time)

        logger.info(
            f"Response: {request.method} {request.url.path} "
            f"[{request_id}] status={response.status_code} time={process_time:.3f}s"
        )

        return response


# Database engine and session factory
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    logger.info("Starting Halo platform...")

    # Initialize Redis connection pool
    app.state.redis = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )

    # Initialize Elasticsearch client
    app.state.elasticsearch = AsyncElasticsearch([settings.elasticsearch_url])

    # Store database session factory
    app.state.db_session = async_session

    logger.info("Halo platform started successfully")

    yield

    # Cleanup
    logger.info("Shutting down Halo platform...")
    await app.state.redis.close()
    await app.state.elasticsearch.close()
    await engine.dispose()
    logger.info("Halo platform shutdown complete")


app = FastAPI(
    title="Halo",
    description="Swedish-Sovereign Intelligence Platform for law enforcement and financial compliance",
    version="0.1.0",
    lifespan=lifespan,
    # Disable docs in production
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

# Rate limiting
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Request size limit middleware
app.add_middleware(RequestSizeLimitMiddleware)

# Security headers middleware (must be added before CORS)
app.add_middleware(SecurityHeadersMiddleware)

# Request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Request sanitization (blocks path traversal, null bytes, etc.)
app.add_middleware(RequestSanitizerMiddleware)

# Session authentication middleware (optional - uses JWT by default via deps.py)
# Uncomment to use session-based auth at the middleware level:
# app.add_middleware(SessionAuthMiddleware, require_session=True)

# CSRF middleware (for browser-based form submissions)
# Note: API endpoints using Bearer tokens are exempt by default
# app.add_middleware(CSRFMiddleware, secret_key=settings.secret_key.encode())

# CORS middleware - properly configured
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "X-CSRF-Token",
    ],
    expose_headers=["X-Request-ID", "X-Process-Time"],
    max_age=600,  # Cache preflight for 10 minutes
)


# Rate limit exceeded handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": exc.detail,
        },
        headers={"Retry-After": str(exc.detail)},
    )


@app.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    """
    Health check endpoint.

    Returns the status of all dependent services.
    """
    health_status: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "0.1.0",
        "services": {},
    }

    # Check PostgreSQL
    try:
        async with request.app.state.db_session() as session:
            await session.execute("SELECT 1")
        health_status["services"]["postgres"] = {"status": "healthy"}
    except Exception as e:
        health_status["services"]["postgres"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "degraded"

    # Check Redis
    try:
        await request.app.state.redis.ping()
        health_status["services"]["redis"] = {"status": "healthy"}
    except Exception as e:
        health_status["services"]["redis"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "degraded"

    # Check Elasticsearch
    try:
        es_health = await request.app.state.elasticsearch.cluster.health()
        es_status = es_health.get("status", "unknown")
        health_status["services"]["elasticsearch"] = {
            "status": "healthy" if es_status in ["green", "yellow"] else "unhealthy",
            "cluster_status": es_status,
        }
    except Exception as e:
        health_status["services"]["elasticsearch"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "degraded"

    return health_status


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with API information."""
    return {
        "name": "Halo",
        "description": "Swedish-Sovereign Intelligence Platform",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions securely."""
    # Log full exception details server-side
    logger.exception(f"Unhandled exception: {exc}")

    # Never expose internal error details in production
    if settings.is_production:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": "An unexpected error occurred. Please contact support.",
            },
        )

    # In development, include more details for debugging
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "type": type(exc).__name__,
        },
    )


# Import and include routers
from halo.api.routes import (
    alerts_router,
    audit_router,
    auth_router,
    cases_router,
    documents_router,
    entities_router,
    search_router,
    referrals_router,
    evidence_router,
    impact_router,
    resolution_router,
    patterns_router,
    lifecycle_router,
    graph_router,
    intelligence_router,
    dashboard_router,
    sars_router,
    users_router,
)

app.include_router(auth_router, prefix="/api/v1", tags=["authentication"])
app.include_router(entities_router, prefix="/api/v1/entities", tags=["entities"])
app.include_router(search_router, prefix="/api/v1/search", tags=["search"])
app.include_router(alerts_router, prefix="/api/v1/alerts", tags=["alerts"])
app.include_router(cases_router, prefix="/api/v1/cases", tags=["cases"])
app.include_router(audit_router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(documents_router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(referrals_router, prefix="/api/v1/referrals", tags=["referrals"])
app.include_router(evidence_router, prefix="/api/v1/evidence", tags=["evidence"])
app.include_router(impact_router, prefix="/api/v1/impact", tags=["impact"])
app.include_router(resolution_router, prefix="/api/v1", tags=["resolution"])
app.include_router(patterns_router, prefix="/api/v1", tags=["patterns"])
app.include_router(lifecycle_router, prefix="/api/v1", tags=["lifecycle"])
app.include_router(graph_router, prefix="/api/v1/graph", tags=["graph"])
app.include_router(intelligence_router, prefix="/api/v1/intelligence", tags=["intelligence"])
app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(sars_router, prefix="/api/v1/sars", tags=["sars"])
app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
