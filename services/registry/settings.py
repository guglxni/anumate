"""
Capsule Registry Service Settings

A.4–A.6 Implementation: Configuration management with environment validation
and secure defaults for production deployment.
"""

import os
from typing import Optional, List
from pydantic import BaseSettings, Field, validator
from anumate_core_config import BaseServiceConfig


class RegistrySettings(BaseServiceConfig):
    """Configuration settings for Capsule Registry service."""
    
    # Service identification
    service_name: str = "capsule-registry"
    service_version: str = "1.0.0"
    
    # API Configuration
    api_prefix: str = "/v1"
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT", ge=1000, le=65535)
    workers: int = Field(default=1, env="WORKERS", ge=1, le=16)
    
    # Database Configuration
    database_url: str = Field(
        default="sqlite+aiosqlite:///./capsule_registry.db",
        env="DATABASE_URL",
        description="Database connection URL"
    )
    database_pool_size: int = Field(default=10, env="DB_POOL_SIZE", ge=1, le=50)
    database_max_overflow: int = Field(default=20, env="DB_MAX_OVERFLOW", ge=0, le=100)
    
    # WORM Storage Configuration  
    worm_bucket: str = Field(
        default="file://./_worm",
        env="WORM_BUCKET", 
        description="WORM storage bucket URI (file:// or s3://)"
    )
    worm_base_path: str = Field(
        default="_worm",
        env="WORM_BASE_PATH",
        description="Base path for file:// WORM storage"
    )
    
    # Authentication & Authorization
    oidc_issuer: str = Field(
        default="https://auth.anumate.dev",
        env="OIDC_ISSUER",
        description="OIDC issuer URL"
    )
    oidc_audience: str = Field(
        default="anumate-platform",
        env="OIDC_AUDIENCE", 
        description="OIDC audience identifier"
    )
    oidc_jwks_url: Optional[str] = Field(
        default=None,
        env="OIDC_JWKS_URL",
        description="OIDC JWKS URL (auto-derived if not set)"
    )
    
    # Signing & Crypto
    signing_key_id: str = Field(
        default="registry-v1",
        env="SIGNING_KEY_ID",
        description="Key identifier for signatures"
    )
    ed25519_private_key: Optional[str] = Field(
        default=None,
        env="ED25519_PRIVATE_KEY",
        description="Base64-encoded Ed25519 private key"
    )
    
    # Tenant Configuration
    default_tenant_id: Optional[str] = Field(
        default=None,
        env="DEFAULT_TENANT_ID",
        description="Default tenant ID for development"
    )
    multi_tenant: bool = Field(
        default=True,
        env="MULTI_TENANT",
        description="Enable multi-tenant support"
    )
    
    # Rate Limiting & Pagination
    max_page_size: int = Field(default=100, env="MAX_PAGE_SIZE", ge=10, le=1000)
    default_page_size: int = Field(default=20, env="DEFAULT_PAGE_SIZE", ge=1, le=100)
    rate_limit_per_minute: int = Field(default=300, env="RATE_LIMIT_PER_MIN", ge=10)
    
    # Validation Configuration
    max_yaml_size_mb: float = Field(default=5.0, env="MAX_YAML_SIZE_MB", ge=0.1, le=50.0)
    max_description_length: int = Field(default=2048, env="MAX_DESC_LENGTH", ge=100, le=10000)
    max_tags_count: int = Field(default=20, env="MAX_TAGS_COUNT", ge=1, le=100)
    
    # Performance & Timeouts
    request_timeout: int = Field(default=30, env="REQUEST_TIMEOUT", ge=5, le=300)
    db_query_timeout: int = Field(default=10, env="DB_QUERY_TIMEOUT", ge=1, le=60)
    worm_upload_timeout: int = Field(default=60, env="WORM_UPLOAD_TIMEOUT", ge=10, le=600)
    
    # Observability
    enable_metrics: bool = Field(default=True, env="ENABLE_METRICS")
    enable_tracing: bool = Field(default=True, env="ENABLE_TRACING") 
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Security Headers
    cors_origins: List[str] = Field(
        default=["*"],
        env="CORS_ORIGINS",
        description="CORS allowed origins"
    )
    cors_methods: List[str] = Field(
        default=["GET", "POST", "PATCH", "DELETE"],
        env="CORS_METHODS"
    )
    
    # Idempotency Configuration
    idempotency_ttl_hours: int = Field(
        default=24,
        env="IDEMPOTENCY_TTL_HOURS", 
        ge=1,
        le=168,  # 1 week max
        description="Idempotency key TTL in hours"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    @validator("database_url")
    def validate_database_url(cls, v):
        """Validate database URL format."""
        supported_schemes = ["sqlite", "sqlite+aiosqlite", "postgresql", "postgresql+asyncpg"]
        scheme = v.split("://")[0].split("+")[0] if "://" in v else ""
        
        if not any(v.startswith(s) for s in ["sqlite", "postgresql"]):
            raise ValueError(f"Unsupported database scheme. Use: {supported_schemes}")
        return v
    
    @validator("worm_bucket")
    def validate_worm_bucket(cls, v):
        """Validate WORM bucket URI format.""" 
        if not (v.startswith("file://") or v.startswith("s3://")):
            raise ValueError("WORM bucket must use file:// or s3:// scheme")
        return v
        
    @validator("oidc_issuer")
    def validate_oidc_issuer(cls, v):
        """Validate OIDC issuer URL."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("OIDC issuer must be a valid HTTP(S) URL")
        return v.rstrip("/")
        
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()
        
    @validator("cors_origins")
    def validate_cors_origins(cls, v):
        """Parse CORS origins from string if needed."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return os.getenv("ANUMATE_ENV", "development").lower() == "production"
        
    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        return self.database_url.startswith("sqlite")
        
    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL database."""
        return self.database_url.startswith("postgresql")
        
    @property
    def worm_is_file(self) -> bool:
        """Check if WORM storage is file-based."""
        return self.worm_bucket.startswith("file://")
        
    @property 
    def worm_is_s3(self) -> bool:
        """Check if WORM storage is S3."""
        return self.worm_bucket.startswith("s3://")
        
    @property
    def computed_jwks_url(self) -> str:
        """Compute JWKS URL from issuer if not explicitly set."""
        if self.oidc_jwks_url:
            return self.oidc_jwks_url
        return f"{self.oidc_issuer}/.well-known/jwks.json"


# Global settings instance
settings = RegistrySettings()


def get_settings() -> RegistrySettings:
    """Get settings instance (for dependency injection)."""
    return settings
