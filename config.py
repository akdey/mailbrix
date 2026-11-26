import json
from functools import lru_cache
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TenantConfig(BaseModel):
    """Per-app / per-tenant configuration loaded from TENANTS_JSON env var."""

    key_hash: str = Field(..., min_length=64, max_length=64, description="SHA-256 hex digest of the API key")
    signing_secret: Optional[str] = Field(default=None, description="Optional HMAC-SHA256 secret for request signing")
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    allow_custom_from_name: bool = False
    rate_limit_per_min: int = Field(default=60, ge=1)
    allowed_recipient_domains: List[str] = Field(default_factory=list)

    # Optional per-tenant SMTP overrides
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_use_ssl: Optional[bool] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None

    @field_validator("key_hash")
    @classmethod
    def normalize_hash(cls, v: str) -> str:
        return v.strip().lower()


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env (never committed to Git)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Email Relay Service"
    env: str = "development"  # Set to "production" to disable /docs and /openapi.json

    # Multi-tenant registry as a JSON string in env: {"app-id": {"key_hash": "...", ...}}
    tenants_json: str = ""

    # Global security & abuse limits
    require_hmac_signature: bool = False
    hmac_tolerance_seconds: int = 60
    ip_rate_limit_per_min: int = 120
    max_request_bytes: int = 5 * 1024 * 1024  # 5 MB
    max_recipients: int = 50
    max_attachments: int = 5
    max_attachment_bytes: int = 3 * 1024 * 1024  # 3 MB decoded per file

    # Default SMTP configuration
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_use_ssl: bool = False
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_timeout: int = 15

    # Default sender
    default_from_email: str = ""
    default_from_name: str = "No-Reply"

    def get_tenants(self) -> Dict[str, TenantConfig]:
        """Parse TENANTS_JSON into a mapping of app_id -> TenantConfig."""
        if not self.tenants_json.strip():
            return {}
        raw = json.loads(self.tenants_json)
        if not isinstance(raw, dict):
            raise ValueError("TENANTS_JSON must be a JSON object mapping app_id -> config")
        return {app_id: TenantConfig(**cfg) for app_id, cfg in raw.items()}


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
