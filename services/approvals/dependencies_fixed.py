"""
Dependency injection configuration for Anumate Approvals Service.

Provides centralized dependency management with proper lifecycle handling.
"""

from fastapi import Depends, HTTPException, Header, status
from typing import AsyncGenerator, Optional
from uuid import UUID
import logging

# Internal imports
from src.service import ApprovalService
from src.repository import ApprovalRepository  
from src.notifications import NotificationService
from config import settings


logger = logging.getLogger(__name__)


# Database dependency
async def get_database():
    """Get database connection."""
    # In a real implementation, this would return a database session
    # For now, return a mock for structure
    return None


# Event publisher dependency
def get_event_publisher():
    """Get event publisher instance."""
    # In a real implementation, this would return a NATS/CloudEvents publisher
    return None


# Tenant ID extraction
async def get_tenant_id(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID")
) -> UUID:
    """Extract tenant ID from request headers."""
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required"
        )
    
    try:
        return UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid tenant ID format"
        )


# Repository dependencies
async def get_approval_repository() -> ApprovalRepository:
    """Get approval repository instance."""
    database = await get_database()
    return ApprovalRepository(database)


# Notification service dependency
async def get_notification_service() -> NotificationService:
    """Get notification service instance."""
    return NotificationService(
        email_enabled="email" in settings.notifications.enabled_providers,
        slack_enabled="slack" in settings.notifications.enabled_providers,
        webhook_enabled="webhook" in settings.notifications.enabled_providers,
        from_email=settings.notifications.from_email,
        smtp_config={
            "host": settings.notifications.smtp_host,
            "port": settings.notifications.smtp_port,
            "user": settings.notifications.smtp_user,
            "password": settings.notifications.smtp_password,
            "use_tls": settings.notifications.smtp_use_tls,
        },
        slack_config={
            "bot_token": settings.notifications.slack_bot_token,
        },
        webhook_config=settings.notifications.webhook_endpoints,
    )


# Main service dependencies
async def get_approval_service(
    repository: ApprovalRepository = Depends(get_approval_repository),
    notification_service: NotificationService = Depends(get_notification_service),
) -> ApprovalService:
    """Get approval service instance with all dependencies."""
    event_publisher = get_event_publisher()
    
    return ApprovalService(
        repository=repository,
        notification_service=notification_service,
        event_publisher=event_publisher,
    )
