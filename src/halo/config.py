"""
Halo configuration management using pydantic-settings.

Security-hardened configuration with validation.
"""

import secrets
import warnings
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: str = Field(
        default="development",
        description="Environment: development, staging, production",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://halo:halo@localhost:5432/halo",
        description="PostgreSQL connection URL",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
    )

    # Elasticsearch
    elasticsearch_url: str = Field(
        default="http://localhost:9200",
        description="Elasticsearch connection URL",
    )

    # SCB Företagsregistret API
    scb_cert_path: Optional[Path] = Field(
        default=None,
        description="Path to SCB API certificate (PFX file)",
    )
    scb_cert_password: Optional[str] = Field(
        default=None,
        description="Password for SCB API certificate",
    )

    # Bolagsverket Företagsinformation API (v4) - OAuth2 Client Credentials
    bolagsverket_client_id: Optional[str] = Field(
        default=None,
        description="Bolagsverket API OAuth2 client ID",
    )
    bolagsverket_client_secret: Optional[str] = Field(
        default=None,
        description="Bolagsverket API OAuth2 client secret",
    )
    bolagsverket_use_test: bool = Field(
        default=False,
        description="Use Bolagsverket test environment",
    )

    # Lantmäteriet Open Data
    lantmateriet_api_key: Optional[str] = Field(
        default=None,
        description="Lantmäteriet Open Data API key",
    )
    lantmateriet_subscription_key: Optional[str] = Field(
        default=None,
        description="Lantmäteriet subscription key for paid services",
    )

    # Lantmäteriet Geotorget (authenticated services)
    lantmateriet_geotorget_username: Optional[str] = Field(
        default=None,
        description="Lantmäteriet Geotorget username",
    )
    lantmateriet_geotorget_password: Optional[str] = Field(
        default=None,
        description="Lantmäteriet Geotorget password",
    )

    # SPAR (Statens personadressregister)
    spar_org_nummer: Optional[str] = Field(
        default=None,
        description="Your organization number for SPAR agreement",
    )
    spar_cert_path: Optional[Path] = Field(
        default=None,
        description="Path to SPAR client certificate for mTLS",
    )
    spar_key_path: Optional[Path] = Field(
        default=None,
        description="Path to SPAR client key for mTLS",
    )
    spar_environment: str = Field(
        default="test",
        description="SPAR environment: 'test' or 'production'",
    )

    # Application Settings
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Security - Secret Key (REQUIRED in production)
    secret_key: str = Field(
        default="",
        description="Secret key for JWT and session encryption (min 32 chars)",
    )

    # JWT Settings
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    access_token_expire_minutes: int = Field(
        default=30, description="Access token expiration in minutes"
    )
    refresh_token_expire_days: int = Field(
        default=7, description="Refresh token expiration in days"
    )

    # PII Encryption Key (for personnummer, etc.)
    pii_encryption_key: str = Field(
        default="",
        description="Fernet key for PII field encryption (32 bytes, base64 encoded)",
    )

    # NLP Model Paths
    kb_bert_model_path: Path = Field(
        default=Path("./models/kb-bert-ner"),
        description="Path to KB-BERT NER model",
    )
    gpt_sw3_model_path: Path = Field(
        default=Path("./models/gpt-sw3"),
        description="Path to GPT-SW3 model",
    )

    # Security - CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins",
    )
    cors_allow_credentials: bool = Field(
        default=True, description="Allow credentials in CORS"
    )

    # Security - Rate Limiting
    rate_limit_requests: int = Field(
        default=100, description="Rate limit requests per window"
    )
    rate_limit_window_seconds: int = Field(
        default=60, description="Rate limit window in seconds"
    )

    # Security - Session
    session_cookie_secure: bool = Field(
        default=True, description="Secure flag for session cookies"
    )
    session_cookie_httponly: bool = Field(
        default=True, description="HttpOnly flag for session cookies"
    )
    session_cookie_samesite: str = Field(
        default="lax", description="SameSite policy for session cookies"
    )

    # Human-in-Loop Compliance Thresholds
    tier_3_threshold: float = Field(
        default=0.85,
        description="Confidence threshold for Tier 3 (approval required) alerts",
    )
    tier_2_threshold: float = Field(
        default=0.50,
        description="Confidence threshold for Tier 2 (acknowledgment required) alerts",
    )
    min_review_seconds: float = Field(
        default=2.0,
        description="Minimum review time before flagging as rubber-stamp",
    )

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Validate and potentially generate a secret key."""
        insecure_defaults = [
            "",
            "change-this-to-a-secure-random-string",
            "secret",
            "changeme",
        ]
        if v in insecure_defaults:
            # Generate a secure key for development
            generated = secrets.token_urlsafe(32)
            warnings.warn(
                f"SECRET_KEY not set or insecure. Generated temporary key for development. "
                f"Set SECRET_KEY environment variable in production!",
                UserWarning,
                stacklevel=2,
            )
            return generated
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("pii_encryption_key")
    @classmethod
    def validate_pii_key(cls, v: str) -> str:
        """Validate PII encryption key or generate one for development."""
        if not v:
            # Generate a Fernet key for development
            from cryptography.fernet import Fernet
            generated = Fernet.generate_key().decode()
            warnings.warn(
                "PII_ENCRYPTION_KEY not set. Generated temporary key for development. "
                "Set PII_ENCRYPTION_KEY environment variable in production!",
                UserWarning,
                stacklevel=2,
            )
            return generated
        return v

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Ensure critical settings are configured in production."""
        if self.environment == "production":
            if self.debug:
                raise ValueError("DEBUG must be False in production")
            if "localhost" in self.database_url:
                warnings.warn(
                    "DATABASE_URL contains 'localhost' in production",
                    UserWarning,
                    stacklevel=2,
                )
            if not self.session_cookie_secure:
                raise ValueError("SESSION_COOKIE_SECURE must be True in production")
        return self

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"


# Global settings instance
settings = Settings()
