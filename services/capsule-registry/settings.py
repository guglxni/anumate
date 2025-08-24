"""Settings for the Capsule Registry service."""

from typing import Optional
from pydantic import Field, validator
from anumate_core_config import BaseServiceSettings


class CapsuleRegistrySettings(BaseServiceSettings):
    """Configuration settings for Capsule Registry service."""
    
    # Service identification
    service_name: str = "capsule-registry"
    service_port: int = 8010
    service_version: str = "1.0.0"
    
    # Database settings
    database_url: str = Field(
        default="sqlite:///./capsule_registry.db",
        env="DATABASE_URL",
        description="Database connection URL"
    )
    database_pool_size: int = Field(
        default=20,
        env="DATABASE_POOL_SIZE",
        description="Database connection pool size"
    )
    
    # OIDC settings
    oidc_issuer: str = Field(
        env="OIDC_ISSUER",
        description="OIDC issuer URL for token validation"
    )
    oidc_audience: str = Field(
        env="OIDC_AUDIENCE", 
        description="OIDC audience for token validation"
    )
    oidc_jwks_url: Optional[str] = Field(
        default=None,
        env="OIDC_JWKS_URL",
        description="OIDC JWKS URL (auto-discovered if not provided)"
    )
    
    # Signing keys
    signing_private_key: str = Field(
        env="SIGNING_PRIVATE_KEY",
        description="Ed25519 private key for content signing (base64 PEM)"
    )
    signing_public_key_id: str = Field(
        default="default",
        env="SIGNING_PUBLIC_KEY_ID",
        description="Public key ID for signature verification"
    )
    
    # WORM storage
    worm_bucket: str = Field(
        default="file://./_worm",
        env="WORM_BUCKET",
        description="WORM storage bucket URL (file:// for local)"
    )
    
    # Business limits
    max_capsule_size: int = Field(
        default=1024 * 1024,  # 1MB
        env="MAX_CAPSULE_SIZE",
        description="Maximum Capsule YAML size in bytes"
    )
    max_versions_per_capsule: int = Field(
        default=1000,
        env="MAX_VERSIONS_PER_CAPSULE",
        description="Maximum versions per Capsule"
    )
    
    # Performance settings
    default_page_size: int = Field(
        default=20,
        env="DEFAULT_PAGE_SIZE",
        description="Default pagination size"
    )
    max_page_size: int = Field(
        default=100,
        env="MAX_PAGE_SIZE",
        description="Maximum pagination size"
    )
    
    # Redis for idempotency (fallback to in-memory for tests)
    redis_url: Optional[str] = Field(
        default=None,
        env="REDIS_URL",
        description="Redis URL for idempotency store"
    )
    
    # Event publishing
    event_bus_url: Optional[str] = Field(
        default=None,
        env="EVENT_BUS_URL",
        description="Event bus URL for CloudEvents publishing"
    )
    
    @validator('signing_private_key')
    def validate_signing_key(cls, v):
        """Validate that signing key is provided."""
        if not v:
            raise ValueError("SIGNING_PRIVATE_KEY is required")
        return v
    
    @validator('oidc_issuer', 'oidc_audience')
    def validate_oidc_config(cls, v):
        """Validate OIDC configuration is provided."""
        if not v:
            raise ValueError("OIDC configuration is required")
        return v

    class Config:
        env_prefix = "ANUMATE_"
        case_sensitive = False
