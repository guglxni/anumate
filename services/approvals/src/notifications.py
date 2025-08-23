"""Notification system for sending approval notifications."""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, BaseLoader
from slack_sdk.web.async_client import AsyncWebClient
import httpx

from .models import (
    ApprovalDetail,
    NotificationChannel,
    NotificationCreate,
    NotificationDetail,
)
from .repository import NotificationRepository

logger = logging.getLogger(__name__)


class NotificationProvider(ABC):
    """Abstract base class for notification providers."""
    
    @abstractmethod
    async def send_notification(
        self,
        recipient: str,
        subject: str,
        message: str,
        data: Dict[str, Any],
    ) -> bool:
        """Send a notification."""
        pass


class EmailNotificationProvider(NotificationProvider):
    """Email notification provider using SMTP."""
    
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = True,
        from_email: str = "noreply@anumate.com",
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.from_email = from_email
    
    async def send_notification(
        self,
        recipient: str,
        subject: str,
        message: str,
        data: Dict[str, Any],
    ) -> bool:
        """Send email notification."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = recipient
            
            # Add HTML content
            html_part = MIMEText(message, 'html')
            msg.attach(html_part)
            
            # Send email
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.username,
                password=self.password,
                use_tls=self.use_tls,
            )
            
            logger.info(f"Email sent successfully to {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")
            return False


class SlackNotificationProvider(NotificationProvider):
    """Slack notification provider."""
    
    def __init__(self, bot_token: str):
        self.client = AsyncWebClient(token=bot_token)
    
    async def send_notification(
        self,
        recipient: str,
        subject: str,
        message: str,
        data: Dict[str, Any],
    ) -> bool:
        """Send Slack notification."""
        try:
            # Build message blocks
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": subject
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                }
            ]
            
            # Add action buttons if approval data is available
            if data.get('approval_id'):
                approval_id = data['approval_id']
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Approve"
                            },
                            "style": "primary",
                            "value": f"approve_{approval_id}",
                            "action_id": "approve_action"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Reject"
                            },
                            "style": "danger",
                            "value": f"reject_{approval_id}",
                            "action_id": "reject_action"
                        }
                    ]
                })
            
            response = await self.client.chat_postMessage(
                channel=recipient,
                blocks=blocks,
                text=subject  # Fallback text
            )
            
            if response["ok"]:
                logger.info(f"Slack message sent successfully to {recipient}")
                return True
            else:
                logger.error(f"Failed to send Slack message: {response['error']}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send Slack notification to {recipient}: {e}")
            return False


class WebhookNotificationProvider(NotificationProvider):
    """Webhook notification provider."""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    async def send_notification(
        self,
        recipient: str,  # webhook URL
        subject: str,
        message: str,
        data: Dict[str, Any],
    ) -> bool:
        """Send webhook notification."""
        try:
            payload = {
                "subject": subject,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data,
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    recipient,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code < 400:
                    logger.info(f"Webhook notification sent successfully to {recipient}")
                    return True
                else:
                    logger.error(f"Webhook returned status {response.status_code}: {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send webhook notification to {recipient}: {e}")
            return False


class NotificationTemplates:
    """Template manager for notifications."""
    
    def __init__(self):
        self.jinja_env = Environment(loader=BaseLoader())
        
        # Default templates
        self.templates = {
            'approval_requested_email': """
            <html>
            <body>
                <h2>Approval Request: {{ approval.title }}</h2>
                
                <p><strong>Priority:</strong> {{ approval.priority.value|upper }}</p>
                <p><strong>Requested by:</strong> {{ approval.request_metadata.get('requested_by', 'System') }}</p>
                <p><strong>Run ID:</strong> {{ approval.run_id }}</p>
                
                {% if approval.expires_at %}
                <p><strong>Expires:</strong> {{ approval.expires_at.strftime('%Y-%m-%d %H:%M UTC') }}</p>
                {% endif %}
                
                <h3>Description</h3>
                <p>{{ approval.description or 'No description provided.' }}</p>
                
                <h3>Plan Context</h3>
                {% for key, value in approval.plan_context.items() %}
                <p><strong>{{ key }}:</strong> {{ value }}</p>
                {% endfor %}
                
                <p>
                    <strong>Please respond to this approval request as soon as possible.</strong>
                </p>
                
                <p>You can approve or reject this request through the Anumate platform.</p>
            </body>
            </html>
            """,
            
            'approval_requested_slack': """
            🔔 **Approval Request**: {{ approval.title }}

            **Priority:** {{ approval.priority.value|upper }}
            **Run ID:** {{ approval.run_id }}
            {% if approval.expires_at %}**Expires:** {{ approval.expires_at.strftime('%Y-%m-%d %H:%M UTC') }}{% endif %}

            {{ approval.description or 'No description provided.' }}
            """,
            
            'approval_granted_email': """
            <html>
            <body>
                <h2>✅ Approval Granted: {{ approval.title }}</h2>
                
                <p>Your approval request has been <strong>approved</strong>.</p>
                
                <p><strong>Run ID:</strong> {{ approval.run_id }}</p>
                <p><strong>Approved by:</strong> {{ ', '.join(approval.approved_by) }}</p>
                <p><strong>Approved at:</strong> {{ approval.completed_at.strftime('%Y-%m-%d %H:%M UTC') }}</p>
                
                {% if approval.approval_reason %}
                <h3>Approval Reason</h3>
                <p>{{ approval.approval_reason }}</p>
                {% endif %}
            </body>
            </html>
            """,
            
            'approval_rejected_email': """
            <html>
            <body>
                <h2>❌ Approval Rejected: {{ approval.title }}</h2>
                
                <p>Your approval request has been <strong>rejected</strong>.</p>
                
                <p><strong>Run ID:</strong> {{ approval.run_id }}</p>
                <p><strong>Rejected by:</strong> {{ approval.rejected_by }}</p>
                <p><strong>Rejected at:</strong> {{ approval.completed_at.strftime('%Y-%m-%d %H:%M UTC') }}</p>
                
                {% if approval.rejection_reason %}
                <h3>Rejection Reason</h3>
                <p>{{ approval.rejection_reason }}</p>
                {% endif %}
            </body>
            </html>
            """,
        }
    
    def render_template(
        self,
        template_name: str,
        context: Dict[str, Any],
    ) -> str:
        """Render a template with context."""
        template_content = self.templates.get(template_name, "")
        if not template_content:
            return f"Template {template_name} not found"
        
        template = self.jinja_env.from_string(template_content)
        return template.render(**context)


class NotificationService:
    """Service for managing and sending notifications."""
    
    def __init__(
        self,
        notification_repo: NotificationRepository,
        email_provider: Optional[EmailNotificationProvider] = None,
        slack_provider: Optional[SlackNotificationProvider] = None,
        webhook_provider: Optional[WebhookNotificationProvider] = None,
    ):
        self.notification_repo = notification_repo
        self.templates = NotificationTemplates()
        
        self.providers = {}
        if email_provider:
            self.providers[NotificationChannel.EMAIL] = email_provider
        if slack_provider:
            self.providers[NotificationChannel.SLACK] = slack_provider
        if webhook_provider:
            self.providers[NotificationChannel.WEBHOOK] = webhook_provider
    
    async def send_approval_requested_notifications(
        self,
        approval: ApprovalDetail,
        approver_contacts: Dict[str, List[Dict[str, str]]],
    ) -> List[NotificationDetail]:
        """Send approval requested notifications to all approvers.
        
        Args:
            approval: Approval details
            approver_contacts: Map of approver_id to list of contact methods
                             Format: {approver_id: [{"channel": "email", "address": "user@example.com"}]}
        """
        notifications = []
        
        for approver_id in approval.required_approvers:
            contacts = approver_contacts.get(approver_id, [])
            
            for contact in contacts:
                channel = NotificationChannel(contact['channel'])
                recipient = contact['address']
                
                try:
                    notification = await self._send_approval_notification(
                        approval=approval,
                        channel=channel,
                        recipient=recipient,
                        notification_type="approval_requested",
                    )
                    notifications.append(notification)
                    
                except Exception as e:
                    logger.error(f"Failed to send notification to {approver_id} via {channel}: {e}")
        
        return notifications
    
    async def send_approval_response_notifications(
        self,
        approval: ApprovalDetail,
        requester_contacts: List[Dict[str, str]],
    ) -> List[NotificationDetail]:
        """Send approval response notifications to requester.
        
        Args:
            approval: Approval details with response
            requester_contacts: List of contact methods for requester
        """
        notifications = []
        
        notification_type = "approval_granted" if approval.status.value == "approved" else "approval_rejected"
        
        for contact in requester_contacts:
            channel = NotificationChannel(contact['channel'])
            recipient = contact['address']
            
            try:
                notification = await self._send_approval_notification(
                    approval=approval,
                    channel=channel,
                    recipient=recipient,
                    notification_type=notification_type,
                )
                notifications.append(notification)
                
            except Exception as e:
                logger.error(f"Failed to send response notification via {channel}: {e}")
        
        return notifications
    
    async def _send_approval_notification(
        self,
        approval: ApprovalDetail,
        channel: NotificationChannel,
        recipient: str,
        notification_type: str,
    ) -> NotificationDetail:
        """Send a single approval notification."""
        
        # Generate content
        if channel == NotificationChannel.EMAIL:
            template_name = f"{notification_type}_email"
            subject = self._get_email_subject(notification_type, approval)
        elif channel == NotificationChannel.SLACK:
            template_name = f"{notification_type}_slack"
            subject = self._get_slack_subject(notification_type, approval)
        else:
            template_name = notification_type
            subject = f"Approval {notification_type}: {approval.title}"
        
        message = self.templates.render_template(
            template_name,
            {"approval": approval}
        )
        
        # Create notification record
        notification_data = NotificationCreate(
            channel=channel,
            recipient=recipient,
            notification_type=notification_type,
            subject=subject,
            message_content=message,
            notification_data={
                "approval_id": str(approval.approval_id),
                "clarification_id": approval.clarification_id,
                "run_id": approval.run_id,
                "priority": approval.priority.value,
            },
        )
        
        notification = await self.notification_repo.create_notification(
            approval_id=approval.approval_id,
            tenant_id=approval.tenant_id,
            notification_data=notification_data,
        )
        
        # Send notification
        provider = self.providers.get(channel)
        if not provider:
            await self.notification_repo.mark_notification_failed(
                notification_id=notification.notification_id,
                failure_reason=f"No provider configured for {channel.value}",
            )
            raise ValueError(f"No provider configured for {channel.value}")
        
        success = await provider.send_notification(
            recipient=recipient,
            subject=subject,
            message=message,
            data=notification_data.notification_data,
        )
        
        if success:
            await self.notification_repo.mark_notification_sent(
                notification_id=notification.notification_id,
            )
        else:
            await self.notification_repo.mark_notification_failed(
                notification_id=notification.notification_id,
                failure_reason="Provider failed to send notification",
            )
        
        return notification
    
    def _get_email_subject(self, notification_type: str, approval: ApprovalDetail) -> str:
        """Get email subject for notification type."""
        subjects = {
            "approval_requested": f"🔔 Approval Required: {approval.title}",
            "approval_granted": f"✅ Approval Granted: {approval.title}",
            "approval_rejected": f"❌ Approval Rejected: {approval.title}",
            "approval_reminder": f"⏰ Approval Reminder: {approval.title}",
        }
        return subjects.get(notification_type, f"Approval Notification: {approval.title}")
    
    def _get_slack_subject(self, notification_type: str, approval: ApprovalDetail) -> str:
        """Get Slack subject for notification type."""
        subjects = {
            "approval_requested": f"Approval Required: {approval.title}",
            "approval_granted": f"Approval Granted: {approval.title}",
            "approval_rejected": f"Approval Rejected: {approval.title}",
            "approval_reminder": f"Approval Reminder: {approval.title}",
        }
        return subjects.get(notification_type, f"Approval: {approval.title}")
    
    async def send_reminder_notifications(
        self,
        approval: ApprovalDetail,
        approver_contacts: Dict[str, List[Dict[str, str]]],
    ) -> List[NotificationDetail]:
        """Send reminder notifications for pending approvals."""
        notifications = []
        
        # Only send to approvers who haven't approved yet
        pending_approvers = [
            approver for approver in approval.required_approvers
            if approver not in approval.approved_by
        ]
        
        for approver_id in pending_approvers:
            contacts = approver_contacts.get(approver_id, [])
            
            for contact in contacts:
                channel = NotificationChannel(contact['channel'])
                recipient = contact['address']
                
                try:
                    notification = await self._send_approval_notification(
                        approval=approval,
                        channel=channel,
                        recipient=recipient,
                        notification_type="approval_reminder",
                    )
                    notifications.append(notification)
                    
                except Exception as e:
                    logger.error(f"Failed to send reminder to {approver_id} via {channel}: {e}")
        
        return notifications
