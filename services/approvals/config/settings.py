"""Configuration settings for the Approvals service."""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings


class NotificationSettings(BaseSettings):
    """Notification configuration."""
    
    # Email settings
    smtp_host: str = os.getenv("SMTP_HOST", "localhost")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: Optional[str] = os.getenv("SMTP_USERNAME")
    smtp_password: Optional[str] = os.getenv("SMTP_PASSWORD")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    from_email: str = os.getenv("FROM_EMAIL", "noreply@anumate.com")
    
    # Slack settings
    slack_bot_token: Optional[str] = os.getenv("SLACK_BOT_TOKEN")
    
    # Webhook settings
    webhook_timeout: int = int(os.getenv("WEBHOOK_TIMEOUT", "30"))


class ApprovalSettings(BaseSettings):
    """Approval workflow configuration."""
    
    # Default expiry time for approvals (hours)
    default_expiry_hours: int = int(os.getenv("APPROVAL_DEFAULT_EXPIRY_HOURS", "24"))
    
    # Reminder settings
    reminder_hours_before_expiry: int = int(os.getenv("REMINDER_HOURS_BEFORE_EXPIRY", "4"))
    
    # Cleanup settings
    cleanup_expired_interval_hours: int = int(os.getenv("CLEANUP_INTERVAL_HOURS", "1"))


class Settings(BaseSettings):
    """Main application settings."""
    
    # Environment
    environment: str = os.getenv("ANUMATE_ENV", "development")
    debug: bool = environment == "development"
    
    # Service settings
    service_name: str = "anumate-approvals"
    service_version: str = "0.1.0"
    
    # Server settings
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8004"))
    
    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://anumate:anumate@localhost:5432/anumate_approvals"
    )
    
    # Event bus
    event_bus_url: str = os.getenv("EVENT_BUS_URL", "nats://localhost:4222")
    
    # External services
    orchestrator_url: str = os.getenv("ORCHESTRATOR_URL", "http://localhost:8001")
    
    # Security
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret-key")
    
    # Notifications
    notifications: NotificationSettings = NotificationSettings()
    
    # Approvals
    approvals: ApprovalSettings = ApprovalSettings()
    
    # CORS
    cors_origins: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
