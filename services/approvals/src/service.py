"""Core business logic for the Approvals service."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID

from .models import (
    ApprovalCreate,
    ApprovalDetail,
    ApprovalSummary,
    ApprovalResponse,
    ApprovalStatus,
    ApprovalRequestedEvent,
    ApprovalGrantedEvent,
    ApprovalRejectedEvent,
)
from .repository import ApprovalRepository, NotificationRepository
from .notifications import NotificationService

try:
    from anumate_events import EventPublisher
except ImportError:
    EventPublisher = None

logger = logging.getLogger(__name__)


class ApprovalService:
    """Core service for approval workflow management."""
    
    def __init__(
        self,
        approval_repo: ApprovalRepository,
        notification_repo: NotificationRepository,
        notification_service: NotificationService,
        event_publisher: Optional[EventPublisher] = None,
    ):
        self.approval_repo = approval_repo
        self.notification_repo = notification_repo
        self.notification_service = notification_service
        self.event_publisher = event_publisher
        
        # Default expiry time for approvals (24 hours)
        self.default_expiry_hours = 24
        
        # Contact resolution - in production this would integrate with user management
        self.approver_contacts = {}
    
    async def create_approval_request(
        self,
        tenant_id: UUID,
        approval_data: ApprovalCreate,
        approver_contacts: Optional[Dict[str, List[Dict[str, str]]]] = None,
    ) -> ApprovalDetail:
        """Create a new approval request.
        
        Args:
            tenant_id: Tenant ID
            approval_data: Approval request data
            approver_contacts: Contact information for approvers
                             Format: {approver_id: [{"channel": "email", "address": "user@example.com"}]}
        """
        try:
            # Set default expiry if not provided
            if not approval_data.expires_at:
                approval_data.expires_at = datetime.now(timezone.utc) + \
                    timedelta(hours=self.default_expiry_hours)
            
            # Create approval
            approval = await self.approval_repo.create_approval(
                tenant_id=tenant_id,
                approval_data=approval_data,
            )
            
            # Send notifications to approvers
            if approver_contacts:
                try:
                    await self.notification_service.send_approval_requested_notifications(
                        approval=approval,
                        approver_contacts=approver_contacts,
                    )
                except Exception as e:
                    logger.error(f"Failed to send approval notifications: {e}")
            
            # Publish approval requested event
            if self.event_publisher:
                try:
                    event = ApprovalRequestedEvent(
                        approval_id=approval.approval_id,
                        tenant_id=tenant_id,
                        clarification_id=approval.clarification_id,
                        run_id=approval.run_id,
                        title=approval.title,
                        priority=approval.priority,
                        required_approvers=approval.required_approvers,
                        expires_at=approval.expires_at,
                        requested_at=approval.requested_at,
                    )
                    
                    await self.event_publisher.publish(
                        event_type="approval.requested",
                        data=event.dict(),
                        source="anumate.approvals",
                        subject=f"approval.{approval.approval_id}",
                    )
                except Exception as e:
                    logger.error(f"Failed to publish approval.requested event: {e}")
            
            logger.info(f"Created approval request {approval.approval_id}")
            return approval
            
        except Exception as e:
            logger.error(f"Failed to create approval request: {e}")
            raise
    
    async def get_approval(
        self,
        approval_id: UUID,
        tenant_id: UUID,
    ) -> Optional[ApprovalDetail]:
        """Get approval by ID."""
        return await self.approval_repo.get_approval(approval_id, tenant_id)
    
    async def get_approval_by_clarification(
        self,
        clarification_id: str,
        tenant_id: UUID,
    ) -> Optional[ApprovalDetail]:
        """Get approval by clarification ID."""
        return await self.approval_repo.get_approval_by_clarification(
            clarification_id, tenant_id
        )
    
    async def list_pending_approvals(
        self,
        tenant_id: UUID,
        approver_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ApprovalSummary]:
        """List pending approvals."""
        return await self.approval_repo.list_pending_approvals(
            tenant_id=tenant_id,
            approver_id=approver_id,
            limit=limit,
            offset=offset,
        )
    
    async def list_approvals(
        self,
        tenant_id: UUID,
        status: Optional[ApprovalStatus] = None,
        approver_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ApprovalSummary]:
        """List approvals with filtering."""
        return await self.approval_repo.list_approvals(
            tenant_id=tenant_id,
            status=status,
            approver_id=approver_id,
            run_id=run_id,
            limit=limit,
            offset=offset,
        )
    
    async def approve_request(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        response: ApprovalResponse,
        requester_contacts: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[ApprovalDetail]:
        """Approve a request.
        
        Args:
            approval_id: Approval ID
            tenant_id: Tenant ID
            response: Approval response with approver details
            requester_contacts: Contact information for request originator
        """
        if not response.approved:
            return await self.reject_request(
                approval_id, tenant_id, response, requester_contacts
            )
        
        try:
            approval = await self.approval_repo.approve_request(
                approval_id=approval_id,
                tenant_id=tenant_id,
                approver_id=response.approver_id,
                reason=response.reason,
            )
            
            if not approval:
                return None
            
            # Check if approval is now complete
            if approval.status == ApprovalStatus.APPROVED:
                # Send completion notifications
                if requester_contacts:
                    try:
                        await self.notification_service.send_approval_response_notifications(
                            approval=approval,
                            requester_contacts=requester_contacts,
                        )
                    except Exception as e:
                        logger.error(f"Failed to send approval completion notifications: {e}")
                
                # Publish approval granted event
                if self.event_publisher:
                    try:
                        event = ApprovalGrantedEvent(
                            approval_id=approval.approval_id,
                            tenant_id=tenant_id,
                            clarification_id=approval.clarification_id,
                            run_id=approval.run_id,
                            approved_by=approval.approved_by,
                            approval_reason=approval.approval_reason,
                            granted_at=approval.completed_at,
                        )
                        
                        await self.event_publisher.publish(
                            event_type="approval.granted",
                            data=event.dict(),
                            source="anumate.approvals",
                            subject=f"approval.{approval.approval_id}",
                        )
                    except Exception as e:
                        logger.error(f"Failed to publish approval.granted event: {e}")
            
            logger.info(f"Approval {approval_id} approved by {response.approver_id}")
            return approval
            
        except Exception as e:
            logger.error(f"Failed to approve request {approval_id}: {e}")
            raise
    
    async def reject_request(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        response: ApprovalResponse,
        requester_contacts: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[ApprovalDetail]:
        """Reject a request."""
        try:
            approval = await self.approval_repo.reject_request(
                approval_id=approval_id,
                tenant_id=tenant_id,
                approver_id=response.approver_id,
                reason=response.reason,
            )
            
            if not approval:
                return None
            
            # Send rejection notifications
            if requester_contacts:
                try:
                    await self.notification_service.send_approval_response_notifications(
                        approval=approval,
                        requester_contacts=requester_contacts,
                    )
                except Exception as e:
                    logger.error(f"Failed to send rejection notifications: {e}")
            
            # Publish approval rejected event
            if self.event_publisher:
                try:
                    event = ApprovalRejectedEvent(
                        approval_id=approval.approval_id,
                        tenant_id=tenant_id,
                        clarification_id=approval.clarification_id,
                        run_id=approval.run_id,
                        rejected_by=approval.rejected_by,
                        rejection_reason=approval.rejection_reason,
                        rejected_at=approval.completed_at,
                    )
                    
                    await self.event_publisher.publish(
                        event_type="approval.rejected",
                        data=event.dict(),
                        source="anumate.approvals",
                        subject=f"approval.{approval.approval_id}",
                    )
                except Exception as e:
                    logger.error(f"Failed to publish approval.rejected event: {e}")
            
            logger.info(f"Approval {approval_id} rejected by {response.approver_id}")
            return approval
            
        except Exception as e:
            logger.error(f"Failed to reject request {approval_id}: {e}")
            raise
    
    async def delegate_approval(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        current_approver: str,
        delegate_to: str,
    ) -> Optional[ApprovalDetail]:
        """Delegate an approval to another user."""
        try:
            # Get current approval
            approval = await self.approval_repo.get_approval(approval_id, tenant_id)
            if not approval:
                return None
            
            # Check if current user can delegate
            if current_approver not in approval.required_approvers:
                raise ValueError(f"User {current_approver} is not authorized to delegate this approval")
            
            if approval.status != ApprovalStatus.PENDING:
                raise ValueError(f"Cannot delegate approval with status {approval.status}")
            
            # Update required approvers
            updated_approvers = [
                delegate_to if approver == current_approver else approver
                for approver in approval.required_approvers
            ]
            
            # Update approval with new approver list
            from .models import ApprovalUpdate
            updated_approval = await self.approval_repo.update_approval(
                approval_id=approval_id,
                tenant_id=tenant_id,
                update_data=ApprovalUpdate(required_approvers=updated_approvers),
            )
            
            # TODO: Send notification to new delegate
            
            logger.info(f"Approval {approval_id} delegated from {current_approver} to {delegate_to}")
            return updated_approval
            
        except Exception as e:
            logger.error(f"Failed to delegate approval {approval_id}: {e}")
            raise
    
    async def cancel_approval(
        self,
        approval_id: UUID,
        tenant_id: UUID,
    ) -> Optional[ApprovalDetail]:
        """Cancel an approval request."""
        try:
            approval = await self.approval_repo.cancel_approval(approval_id, tenant_id)
            
            if approval:
                logger.info(f"Approval {approval_id} cancelled")
            
            return approval
            
        except Exception as e:
            logger.error(f"Failed to cancel approval {approval_id}: {e}")
            raise
    
    async def cleanup_expired_approvals(self) -> int:
        """Clean up expired approval requests."""
        try:
            count = await self.approval_repo.expire_old_approvals()
            
            if count > 0:
                logger.info(f"Cleaned up {count} expired approval requests")
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired approvals: {e}")
            raise
    
    async def send_approval_reminders(
        self,
        tenant_id: UUID,
        hours_before_expiry: int = 4,
    ) -> int:
        """Send reminder notifications for approvals expiring soon."""
        try:
            # Get approvals expiring soon
            cutoff_time = datetime.now(timezone.utc) + timedelta(hours=hours_before_expiry)
            
            pending_approvals = await self.approval_repo.list_approvals(
                tenant_id=tenant_id,
                status=ApprovalStatus.PENDING,
                limit=100,  # Process in batches
            )
            
            # Filter by expiry time
            expiring_approvals = [
                approval for approval in pending_approvals
                if approval.expires_at and approval.expires_at <= cutoff_time
            ]
            
            reminder_count = 0
            for approval_summary in expiring_approvals:
                # Get full approval details
                approval = await self.approval_repo.get_approval(
                    approval_summary.approval_id, tenant_id
                )
                
                if approval:
                    # Get contacts for pending approvers
                    pending_approvers = [
                        approver for approver in approval.required_approvers
                        if approver not in approval.approved_by
                    ]
                    
                    approver_contacts = {
                        approver: self.approver_contacts.get(approver, [])
                        for approver in pending_approvers
                    }
                    
                    if approver_contacts:
                        try:
                            await self.notification_service.send_reminder_notifications(
                                approval=approval,
                                approver_contacts=approver_contacts,
                            )
                            reminder_count += 1
                        except Exception as e:
                            logger.error(f"Failed to send reminder for approval {approval.approval_id}: {e}")
            
            if reminder_count > 0:
                logger.info(f"Sent {reminder_count} approval reminders")
            
            return reminder_count
            
        except Exception as e:
            logger.error(f"Failed to send approval reminders: {e}")
            raise
    
    def set_approver_contacts(
        self,
        contacts: Dict[str, List[Dict[str, str]]]
    ) -> None:
        """Set approver contact information.
        
        Args:
            contacts: Map of approver_id to contact methods
                     Format: {approver_id: [{"channel": "email", "address": "user@example.com"}]}
        """
        self.approver_contacts.update(contacts)
    
    def get_approval_statistics(
        self,
        tenant_id: UUID,
    ) -> Dict[str, Any]:
        """Get approval statistics for a tenant."""
        # This would be implemented with proper SQL queries
        # For now, return a placeholder
        return {
            "total_pending": 0,
            "total_approved": 0,
            "total_rejected": 0,
            "average_response_time_hours": 0,
            "approvals_by_priority": {
                "urgent": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            },
        }
