"""Dependency injection setup for the Approvals service."""

import logging
from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .config.database import get_db_session
from .config.settings import settings
from .src.repository import ApprovalRepository, NotificationRepository
from .src.service import ApprovalService
from .src.notifications import (
    NotificationService,
    EmailNotificationProvider,
    SlackNotificationProvider,
    WebhookNotificationProvider,
)

try:
    from anumate_events import EventPublisher
except ImportError:
    # Mock EventPublisher for development
    class EventPublisher:
        def __init__(self):
            self.events = []
        
        async def publish(self, event_type: str, data: dict, **kwargs):
            self.events.append({
                "event_type": event_type,
                "data": data,
                "timestamp": "mock",
                **kwargs
            })

logger = logging.getLogger(__name__)


async def get_approval_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalRepository:
    """Get approval repository with database session."""
    return ApprovalRepository(session)


async def get_notification_repository(
    session: AsyncSession = Depends(get_db_session),
) -> NotificationRepository:
    """Get notification repository with database session."""
    return NotificationRepository(session)


def get_event_publisher() -> EventPublisher:
    """Get event publisher instance."""
    return EventPublisher()


def get_notification_service(
    notification_repo: NotificationRepository = Depends(get_notification_repository),
) -> NotificationService:
    """Get notification service with configured providers."""
    
    # Configure email provider
    email_provider = None
    if settings.notifications.smtp_host:
        email_provider = EmailNotificationProvider(
            smtp_host=settings.notifications.smtp_host,
            smtp_port=settings.notifications.smtp_port,
            username=settings.notifications.smtp_username,
            password=settings.notifications.smtp_password,
            use_tls=settings.notifications.smtp_use_tls,
            from_email=settings.notifications.from_email,
        )
    
    # Configure Slack provider
    slack_provider = None
    if settings.notifications.slack_bot_token:
        slack_provider = SlackNotificationProvider(
            bot_token=settings.notifications.slack_bot_token
        )
    
    # Configure webhook provider
    webhook_provider = WebhookNotificationProvider(
        timeout=settings.notifications.webhook_timeout
    )
    
    return NotificationService(
        notification_repo=notification_repo,
        email_provider=email_provider,
        slack_provider=slack_provider,
        webhook_provider=webhook_provider,
    )


async def get_approval_service(
    approval_repo: ApprovalRepository = Depends(get_approval_repository),
    notification_repo: NotificationRepository = Depends(get_notification_repository),
    notification_service: NotificationService = Depends(get_notification_service),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> ApprovalService:
    """Get approval service with all dependencies."""
    service = ApprovalService(
        approval_repo=approval_repo,
        notification_repo=notification_repo,
        notification_service=notification_service,
        event_publisher=event_publisher,
    )
    
    # Configure default expiry
    service.default_expiry_hours = settings.approvals.default_expiry_hours
    
    return service
