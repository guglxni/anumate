"""
Anumate Approvals Service Configuration

Centralized configuration management for the approvals service.
Supports environment-based configuration with validation.
"""

from pydantic import BaseSettings, validator, Field
from typing import Optional, List, Dict, Any
import os
from enum import Enum


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class NotificationProvider(str, Enum):
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


class DatabaseConfig(BaseSettings):
    """Database configuration settings."""
    
    url: str = Field(
        ...,
        description="Database connection URL",
        env="DATABASE_URL"
    )
    
    pool_size: int = Field(
        default=10,
        description="Connection pool size",
        env="DATABASE_POOL_SIZE"
    )
    
    max_overflow: int = Field(
        default=20,
        description="Maximum pool overflow",
        env="DATABASE_MAX_OVERFLOW"
    )
    
    echo: bool = Field(
        default=False,
        description="Enable SQL query logging",
        env="DATABASE_ECHO"
    )

    class Config:
        env_prefix = "DATABASE_"


class EventConfig(BaseSettings):
    """Event system configuration."""
    
    nats_url: str = Field(
        default="nats://localhost:4222",
        description="NATS server URL",
        env="NATS_URL"
    )
    
    subject_prefix: str = Field(
        default="anumate.approvals",
        description="Event subject prefix",
        env="EVENT_SUBJECT_PREFIX"
    )
    
    stream_name: str = Field(
        default="approvals-events",
        description="NATS stream name",
        env="EVENT_STREAM_NAME"
    )
    
    durable_name: str = Field(
        default="approvals-consumer",
        description="Durable consumer name",
        env="EVENT_DURABLE_NAME"
    )

    class Config:
        env_prefix = "EVENT_"


class NotificationConfig(BaseSettings):
    """Notification system configuration."""
    
    enabled_providers: List[NotificationProvider] = Field(
        default=[NotificationProvider.EMAIL],
        description="Enabled notification providers",
        env="NOTIFICATION_PROVIDERS"
    )
    
    # Email settings
    smtp_host: Optional[str] = Field(
        default=None,
        description="SMTP server host",
        env="SMTP_HOST"
    )
    
    smtp_port: int = Field(
        default=587,
        description="SMTP server port",
        env="SMTP_PORT"
    )
    
    smtp_user: Optional[str] = Field(
        default=None,
        description="SMTP username",
        env="SMTP_USER"
    )
    
    smtp_password: Optional[str] = Field(
        default=None,
        description="SMTP password",
        env="SMTP_PASSWORD"
    )
    
    smtp_use_tls: bool = Field(
        default=True,
        description="Use TLS for SMTP",
        env="SMTP_USE_TLS"
    )
    
    from_email: str = Field(
        default="noreply@anumate.io",
        description="From email address",
        env="NOTIFICATION_FROM_EMAIL"
    )
    
    # Slack settings
    slack_bot_token: Optional[str] = Field(
        default=None,
        description="Slack bot token",
        env="SLACK_BOT_TOKEN"
    )
    
    slack_signing_secret: Optional[str] = Field(
        default=None,
        description="Slack signing secret",
        env="SLACK_SIGNING_SECRET"
    )
    
    # Webhook settings
    webhook_endpoints: Dict[str, str] = Field(
        default_factory=dict,
        description="Webhook endpoints by type",
        env="WEBHOOK_ENDPOINTS"
    )

    @validator("enabled_providers", pre=True)
    def parse_providers(cls, v):
        if isinstance(v, str):
            return [NotificationProvider(p.strip()) for p in v.split(",")]
        return v

    class Config:
        env_prefix = "NOTIFICATION_"


class SecurityConfig(BaseSettings):
    """Security configuration settings."""
    
    jwt_secret_key: str = Field(
        ...,
        description="JWT secret key",
        env="JWT_SECRET_KEY"
    )
    
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm",
        env="JWT_ALGORITHM"
    )
    
    jwt_expiration_hours: int = Field(
        default=24,
        description="JWT token expiration in hours",
        env="JWT_EXPIRATION_HOURS"
    )
    
    tenant_header_name: str = Field(
        default="X-Tenant-ID",
        description="HTTP header name for tenant ID",
        env="TENANT_HEADER_NAME"
    )

    class Config:
        env_prefix = "SECURITY_"


class ApprovalConfig(BaseSettings):
    """Approval-specific configuration."""
    
    default_timeout_hours: int = Field(
        default=72,
        description="Default approval timeout in hours",
        env="APPROVAL_DEFAULT_TIMEOUT_HOURS"
    )
    
    max_timeout_hours: int = Field(
        default=720,  # 30 days
        description="Maximum approval timeout in hours",
        env="APPROVAL_MAX_TIMEOUT_HOURS"
    )
    
    reminder_intervals_hours: List[int] = Field(
        default=[24, 48],
        description="Reminder intervals in hours",
        env="APPROVAL_REMINDER_INTERVALS"
    )
    
    auto_escalation_enabled: bool = Field(
        default=True,
        description="Enable auto-escalation",
        env="APPROVAL_AUTO_ESCALATION_ENABLED"
    )
    
    escalation_timeout_hours: int = Field(
        default=48,
        description="Hours before escalation",
        env="APPROVAL_ESCALATION_TIMEOUT_HOURS"
    )

    @validator("reminder_intervals_hours", pre=True)
    def parse_reminder_intervals(cls, v):
        if isinstance(v, str):
            return [int(i.strip()) for i in v.split(",")]
        return v

    class Config:
        env_prefix = "APPROVAL_"


class Settings(BaseSettings):
    """Main application settings."""
    
    # Application settings
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Application environment",
        env="ENVIRONMENT"
    )
    
    service_name: str = Field(
        default="approvals",
        description="Service name",
        env="SERVICE_NAME"
    )
    
    version: str = Field(
        default="1.0.0",
        description="Service version",
        env="VERSION"
    )
    
    host: str = Field(
        default="0.0.0.0",
        description="Host to bind to",
        env="HOST"
    )
    
    port: int = Field(
        default=8080,
        description="Port to bind to",
        env="PORT"
    )
    
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
        env="DEBUG"
    )
    
    log_level: str = Field(
        default="INFO",
        description="Logging level",
        env="LOG_LEVEL"
    )
    
    # Component configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    events: EventConfig = Field(default_factory=EventConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    approvals: ApprovalConfig = Field(default_factory=ApprovalConfig)
    
    # API Configuration
    api_prefix: str = Field(
        default="/api",
        description="API prefix",
        env="API_PREFIX"
    )
    
    cors_origins: List[str] = Field(
        default=["*"],
        description="CORS allowed origins",
        env="CORS_ORIGINS"
    )
    
    docs_enabled: bool = Field(
        default=True,
        description="Enable API documentation",
        env="DOCS_ENABLED"
    )

    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @validator("debug", pre=True)
    def set_debug_from_environment(cls, v, values):
        if values.get("environment") == Environment.DEVELOPMENT:
            return True
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings


# Export commonly used configs
database_config = settings.database
event_config = settings.events
notification_config = settings.notifications
security_config = settings.security
approval_config = settings.approvals
