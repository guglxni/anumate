"""Database operations for the Approvals service."""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_, desc, func

from .models import (
    Approval,
    ApprovalNotification,
    ApprovalStatus,
    ApprovalCreate,
    ApprovalUpdate,
    ApprovalDetail,
    ApprovalSummary,
    NotificationCreate,
    NotificationDetail,
)

logger = logging.getLogger(__name__)


class ApprovalRepository:
    """Repository for approval database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_approval(
        self,
        tenant_id: UUID,
        approval_data: ApprovalCreate,
    ) -> ApprovalDetail:
        """Create a new approval request."""
        try:
            approval = Approval(
                tenant_id=tenant_id,
                clarification_id=approval_data.clarification_id,
                run_id=approval_data.run_id,
                title=approval_data.title,
                description=approval_data.description,
                priority=approval_data.priority,
                required_approvers=approval_data.required_approvers,
                approval_rules=approval_data.approval_rules,
                requires_all_approvers=approval_data.requires_all_approvers,
                expires_at=approval_data.expires_at,
                plan_context=approval_data.plan_context,
                request_metadata=approval_data.request_metadata,
            )
            
            self.session.add(approval)
            await self.session.commit()
            await self.session.refresh(approval)
            
            logger.info(f"Created approval {approval.approval_id} for clarification {approval_data.clarification_id}")
            return ApprovalDetail.from_orm(approval)
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to create approval: {e}")
            raise
    
    async def get_approval(
        self,
        approval_id: UUID,
        tenant_id: UUID,
    ) -> Optional[ApprovalDetail]:
        """Get an approval by ID."""
        try:
            query = select(Approval).where(
                and_(
                    Approval.approval_id == approval_id,
                    Approval.tenant_id == tenant_id,
                )
            )
            
            result = await self.session.execute(query)
            approval = result.scalar_one_or_none()
            
            if approval:
                return ApprovalDetail.from_orm(approval)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get approval {approval_id}: {e}")
            raise
    
    async def get_approval_by_clarification(
        self,
        clarification_id: str,
        tenant_id: UUID,
    ) -> Optional[ApprovalDetail]:
        """Get an approval by clarification ID."""
        try:
            query = select(Approval).where(
                and_(
                    Approval.clarification_id == clarification_id,
                    Approval.tenant_id == tenant_id,
                )
            ).order_by(desc(Approval.created_at))
            
            result = await self.session.execute(query)
            approval = result.scalar_one_or_none()
            
            if approval:
                return ApprovalDetail.from_orm(approval)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get approval for clarification {clarification_id}: {e}")
            raise
    
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
        try:
            query = select(Approval).where(Approval.tenant_id == tenant_id)
            
            if status:
                query = query.where(Approval.status == status)
            
            if approver_id:
                query = query.where(
                    or_(
                        func.json_array_elements_text(Approval.required_approvers).op('@>')\
                            (f'"{approver_id}"'),
                        func.json_array_elements_text(Approval.approved_by).op('@>')\
                            (f'"{approver_id}"'),
                        Approval.rejected_by == approver_id,
                    )
                )
            
            if run_id:
                query = query.where(Approval.run_id == run_id)
            
            query = query.order_by(desc(Approval.created_at)).limit(limit).offset(offset)
            
            result = await self.session.execute(query)
            approvals = result.scalars().all()
            
            return [ApprovalSummary.from_orm(approval) for approval in approvals]
            
        except Exception as e:
            logger.error(f"Failed to list approvals: {e}")
            raise
    
    async def list_pending_approvals(
        self,
        tenant_id: UUID,
        approver_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ApprovalSummary]:
        """List pending approvals for an approver."""
        try:
            query = select(Approval).where(
                and_(
                    Approval.tenant_id == tenant_id,
                    Approval.status == ApprovalStatus.PENDING,
                )
            )
            
            if approver_id:
                query = query.where(
                    func.json_array_elements_text(Approval.required_approvers)\
                        .op('@>')(f'"{approver_id}"')
                )
            
            # Filter out expired approvals
            now = datetime.now(timezone.utc)
            query = query.where(
                or_(
                    Approval.expires_at.is_(None),
                    Approval.expires_at > now,
                )
            )
            
            query = query.order_by(
                Approval.priority.desc(),
                Approval.created_at.asc(),
            ).limit(limit).offset(offset)
            
            result = await self.session.execute(query)
            approvals = result.scalars().all()
            
            return [ApprovalSummary.from_orm(approval) for approval in approvals]
            
        except Exception as e:
            logger.error(f"Failed to list pending approvals: {e}")
            raise
    
    async def update_approval(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        update_data: ApprovalUpdate,
    ) -> Optional[ApprovalDetail]:
        """Update an approval."""
        try:
            query = select(Approval).where(
                and_(
                    Approval.approval_id == approval_id,
                    Approval.tenant_id == tenant_id,
                )
            )
            
            result = await self.session.execute(query)
            approval = result.scalar_one_or_none()
            
            if not approval:
                return None
            
            # Update fields
            if update_data.title is not None:
                approval.title = update_data.title
            if update_data.description is not None:
                approval.description = update_data.description
            if update_data.priority is not None:
                approval.priority = update_data.priority
            if update_data.required_approvers is not None:
                approval.required_approvers = update_data.required_approvers
            if update_data.expires_at is not None:
                approval.expires_at = update_data.expires_at
            
            approval.updated_at = datetime.now(timezone.utc)
            
            await self.session.commit()
            await self.session.refresh(approval)
            
            return ApprovalDetail.from_orm(approval)
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update approval {approval_id}: {e}")
            raise
    
    async def approve_request(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        approver_id: str,
        reason: Optional[str] = None,
    ) -> Optional[ApprovalDetail]:
        """Approve a request."""
        try:
            query = select(Approval).where(
                and_(
                    Approval.approval_id == approval_id,
                    Approval.tenant_id == tenant_id,
                    Approval.status == ApprovalStatus.PENDING,
                )
            )
            
            result = await self.session.execute(query)
            approval = result.scalar_one_or_none()
            
            if not approval:
                return None
            
            # Check if approver is authorized
            if approver_id not in approval.required_approvers:
                raise ValueError(f"Approver {approver_id} is not authorized for this approval")
            
            # Check if already approved by this approver
            if approver_id in approval.approved_by:
                raise ValueError(f"Approver {approver_id} has already approved this request")
            
            # Add approver
            approval.approved_by = approval.approved_by + [approver_id]
            approval.approval_reason = reason
            approval.updated_at = datetime.now(timezone.utc)
            
            # Check if we have all required approvals
            if approval.requires_all_approvers:
                # Need all approvers
                if set(approval.approved_by) == set(approval.required_approvers):
                    approval.status = ApprovalStatus.APPROVED
                    approval.completed_at = datetime.now(timezone.utc)
            else:
                # Need at least one approver
                approval.status = ApprovalStatus.APPROVED
                approval.completed_at = datetime.now(timezone.utc)
            
            await self.session.commit()
            await self.session.refresh(approval)
            
            logger.info(f"Approval {approval_id} approved by {approver_id}")
            return ApprovalDetail.from_orm(approval)
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to approve request {approval_id}: {e}")
            raise
    
    async def reject_request(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        approver_id: str,
        reason: Optional[str] = None,
    ) -> Optional[ApprovalDetail]:
        """Reject a request."""
        try:
            query = select(Approval).where(
                and_(
                    Approval.approval_id == approval_id,
                    Approval.tenant_id == tenant_id,
                    Approval.status == ApprovalStatus.PENDING,
                )
            )
            
            result = await self.session.execute(query)
            approval = result.scalar_one_or_none()
            
            if not approval:
                return None
            
            # Check if approver is authorized
            if approver_id not in approval.required_approvers:
                raise ValueError(f"Approver {approver_id} is not authorized for this approval")
            
            # Reject the request
            approval.status = ApprovalStatus.REJECTED
            approval.rejected_by = approver_id
            approval.rejection_reason = reason
            approval.completed_at = datetime.now(timezone.utc)
            approval.updated_at = datetime.now(timezone.utc)
            
            await self.session.commit()
            await self.session.refresh(approval)
            
            logger.info(f"Approval {approval_id} rejected by {approver_id}")
            return ApprovalDetail.from_orm(approval)
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to reject request {approval_id}: {e}")
            raise
    
    async def cancel_approval(
        self,
        approval_id: UUID,
        tenant_id: UUID,
    ) -> Optional[ApprovalDetail]:
        """Cancel an approval request."""
        try:
            query = select(Approval).where(
                and_(
                    Approval.approval_id == approval_id,
                    Approval.tenant_id == tenant_id,
                    Approval.status == ApprovalStatus.PENDING,
                )
            )
            
            result = await self.session.execute(query)
            approval = result.scalar_one_or_none()
            
            if not approval:
                return None
            
            approval.status = ApprovalStatus.CANCELLED
            approval.completed_at = datetime.now(timezone.utc)
            approval.updated_at = datetime.now(timezone.utc)
            
            await self.session.commit()
            await self.session.refresh(approval)
            
            logger.info(f"Approval {approval_id} cancelled")
            return ApprovalDetail.from_orm(approval)
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to cancel approval {approval_id}: {e}")
            raise
    
    async def expire_old_approvals(self) -> int:
        """Expire old approval requests."""
        try:
            now = datetime.now(timezone.utc)
            
            query = select(Approval).where(
                and_(
                    Approval.status == ApprovalStatus.PENDING,
                    Approval.expires_at <= now,
                )
            )
            
            result = await self.session.execute(query)
            expired_approvals = result.scalars().all()
            
            for approval in expired_approvals:
                approval.status = ApprovalStatus.EXPIRED
                approval.completed_at = now
                approval.updated_at = now
            
            await self.session.commit()
            
            count = len(expired_approvals)
            if count > 0:
                logger.info(f"Expired {count} old approval requests")
            
            return count
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to expire old approvals: {e}")
            raise


class NotificationRepository:
    """Repository for notification database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_notification(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        notification_data: NotificationCreate,
    ) -> NotificationDetail:
        """Create a new notification."""
        try:
            notification = ApprovalNotification(
                approval_id=approval_id,
                tenant_id=tenant_id,
                channel=notification_data.channel,
                recipient=notification_data.recipient,
                notification_type=notification_data.notification_type,
                subject=notification_data.subject,
                message_content=notification_data.message_content,
                notification_data=notification_data.notification_data,
            )
            
            self.session.add(notification)
            await self.session.commit()
            await self.session.refresh(notification)
            
            return NotificationDetail.from_orm(notification)
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to create notification: {e}")
            raise
    
    async def mark_notification_sent(
        self,
        notification_id: UUID,
        sent_at: Optional[datetime] = None,
    ) -> Optional[NotificationDetail]:
        """Mark notification as sent."""
        try:
            query = select(ApprovalNotification).where(
                ApprovalNotification.notification_id == notification_id
            )
            
            result = await self.session.execute(query)
            notification = result.scalar_one_or_none()
            
            if not notification:
                return None
            
            notification.sent_at = sent_at or datetime.now(timezone.utc)
            
            await self.session.commit()
            await self.session.refresh(notification)
            
            return NotificationDetail.from_orm(notification)
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to mark notification {notification_id} as sent: {e}")
            raise
    
    async def mark_notification_failed(
        self,
        notification_id: UUID,
        failure_reason: str,
        failed_at: Optional[datetime] = None,
    ) -> Optional[NotificationDetail]:
        """Mark notification as failed."""
        try:
            query = select(ApprovalNotification).where(
                ApprovalNotification.notification_id == notification_id
            )
            
            result = await self.session.execute(query)
            notification = result.scalar_one_or_none()
            
            if not notification:
                return None
            
            notification.failed_at = failed_at or datetime.now(timezone.utc)
            notification.failure_reason = failure_reason
            
            await self.session.commit()
            await self.session.refresh(notification)
            
            return NotificationDetail.from_orm(notification)
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to mark notification {notification_id} as failed: {e}")
            raise
