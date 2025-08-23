"""
Enhanced Approval Service with Workflow Engine Integration

Integrates the workflow engine with the existing approval service to provide
enterprise-grade approval workflows with multi-step processes, escalation,
timeout handling, and comprehensive audit trails.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union
from uuid import UUID, uuid4

from .models import ApprovalDetail, ApprovalStatus
# from .service import ApprovalService  # Avoid circular import
from .workflow_manager import WorkflowManager
from .workflow_engine import WorkflowExecution, AuditLogEntry
from .repository import ApprovalRepository
from .notifications import NotificationService

logger = logging.getLogger(__name__)


class EnhancedApprovalService:
    """Enhanced approval service with workflow engine capabilities."""
    
    def __init__(
        self,
        approval_repository: ApprovalRepository,
        notification_service: NotificationService,
        event_publisher=None
    ):
        """Initialize enhanced approval service."""
        self.approval_repository = approval_repository
        self.notification_service = notification_service
        self.event_publisher = event_publisher
        
        # Initialize workflow manager
        self.workflow_manager = WorkflowManager(
            approval_repository=approval_repository,
            event_publisher=event_publisher,
            notification_service=notification_service
        )
        
        # Legacy service for backward compatibility (simplified to avoid import issues)
        self.legacy_service = None  # Will be initialized when needed
        
    async def create_approval_request(
        self,
        tenant_id: UUID,
        clarification_id: str,
        clarification: Dict[str, Any],
        requester_contacts: Dict[str, str],
        workflow_type: str = "simple",
        priority: str = "medium",
        custom_approvers: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ApprovalDetail:
        """
        Create approval request with automatic workflow assignment.
        
        Args:
            tenant_id: Tenant ID
            clarification_id: Clarification ID from Portia
            clarification: Clarification details
            requester_contacts: Contact info for requester
            workflow_type: Type of workflow ('simple', 'two_step', 'security_review')
            priority: Priority level ('low', 'medium', 'high', 'urgent')
            custom_approvers: Custom list of approvers
            context: Additional context for workflow
        
        Returns:
            ApprovalDetail: Created approval with workflow
        """
        try:
            # Determine approvers from clarification or use custom
            approvers = custom_approvers or clarification.get("approvers", [])
            if not approvers:
                approvers = ["admin@anumate.io"]  # Default fallback
            
            # Create approval with workflow
            approval_id = await self.workflow_manager.create_approval_with_workflow(
                tenant_id=tenant_id,
                clarification_id=clarification_id,
                clarification=clarification,
                workflow_type=workflow_type,
                custom_approvers=approvers,
                priority=priority,
                context={
                    "requester_contacts": requester_contacts,
                    "required_approvals": clarification.get("required_approvals", 1),
                    **(context or {})
                }
            )
            
            # Get the created approval details
            approval_detail = ApprovalDetail(
                id=approval_id,
                tenant_id=tenant_id,
                title=clarification.get("question", "Approval Required"),
                description=f"Clarification: {clarification.get('question', 'N/A')}",
                status=ApprovalStatus.PENDING_APPROVAL,
                priority=priority,
                clarification_id=clarification_id,
                required_approvers=approvers,
                required_approvals=clarification.get("required_approvals", 1),
                received_approvals=0,
                plan_context=clarification.get("context", {}),
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
                workflow_type=workflow_type
            )
            
            logger.info(f"Created approval {approval_id} with {workflow_type} workflow")
            return approval_detail
            
        except Exception as e:
            logger.error(f"Failed to create approval with workflow: {e}")
            raise
    
    async def approve_request(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        response: Dict[str, Any],
        requester_contacts: Dict[str, str]
    ) -> Optional[ApprovalDetail]:
        """
        Approve a request through the workflow engine.
        
        Args:
            approval_id: Approval ID
            tenant_id: Tenant ID
            response: Approval response data
            requester_contacts: Requester contact information
        
        Returns:
            Updated approval details or None if not found
        """
        try:
            approver_id = response.get("approver_id")
            approved = response.get("approved", True)
            comments = response.get("comments", "")
            
            # Process through workflow engine
            result = await self.workflow_manager.process_workflow_response(
                approval_id=approval_id,
                approver_id=approver_id,
                approved=approved,
                comments=comments,
                metadata=response.get("metadata", {})
            )
            
            if not result["workflow_updated"]:
                logger.warning(f"No workflow found for approval {approval_id}, using legacy approval")
                return await self.legacy_service.approve_request(
                    approval_id, tenant_id, response, requester_contacts
                )
            
            # Get updated approval status
            approval_detail = await self.get_approval(approval_id, tenant_id)
            if not approval_detail:
                logger.error(f"Could not retrieve approval {approval_id} after processing")
                return None
            
            # Send notifications based on result
            await self._handle_approval_notifications(
                approval_detail, result, requester_contacts
            )
            
            logger.info(f"Processed approval response for {approval_id}: {approved}")
            return approval_detail
            
        except Exception as e:
            logger.error(f"Failed to approve request {approval_id}: {e}")
            raise
    
    async def reject_request(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        response: Dict[str, Any],
        requester_contacts: Dict[str, str]
    ) -> Optional[ApprovalDetail]:
        """
        Reject a request through the workflow engine.
        
        Args:
            approval_id: Approval ID
            tenant_id: Tenant ID
            response: Rejection response data
            requester_contacts: Requester contact information
        
        Returns:
            Updated approval details or None if not found
        """
        try:
            approver_id = response.get("approver_id")
            comments = response.get("comments", "")
            
            # Process rejection through workflow engine
            result = await self.workflow_manager.process_workflow_response(
                approval_id=approval_id,
                approver_id=approver_id,
                approved=False,
                comments=comments,
                metadata=response.get("metadata", {})
            )
            
            if not result["workflow_updated"]:
                logger.warning(f"No workflow found for approval {approval_id}, using legacy rejection")
                return await self.legacy_service.reject_request(
                    approval_id, tenant_id, response, requester_contacts
                )
            
            # Get updated approval status
            approval_detail = await self.get_approval(approval_id, tenant_id)
            
            # Send rejection notifications
            await self._handle_rejection_notifications(
                approval_detail, result, requester_contacts
            )
            
            logger.info(f"Processed rejection for {approval_id}")
            return approval_detail
            
        except Exception as e:
            logger.error(f"Failed to reject request {approval_id}: {e}")
            raise
    
    async def delegate_approval(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        current_approver: str,
        delegate_to: str,
        reason: Optional[str] = None
    ) -> Optional[ApprovalDetail]:
        """
        Delegate an approval to another user through workflow engine.
        
        Args:
            approval_id: Approval ID
            tenant_id: Tenant ID
            current_approver: Current approver delegating
            delegate_to: User to delegate to
            reason: Reason for delegation
        
        Returns:
            Updated approval details or None if failed
        """
        try:
            # Process delegation through workflow engine
            success = await self.workflow_manager.delegate_workflow_step(
                approval_id=approval_id,
                current_approver=current_approver,
                delegate_to=delegate_to,
                delegation_reason=reason
            )
            
            if not success:
                logger.warning(f"Workflow delegation failed for {approval_id}")
                return None
            
            # Get updated approval
            approval_detail = await self.get_approval(approval_id, tenant_id)
            
            # Send delegation notifications
            await self._handle_delegation_notifications(
                approval_detail, current_approver, delegate_to, reason
            )
            
            logger.info(f"Delegated approval {approval_id} from {current_approver} to {delegate_to}")
            return approval_detail
            
        except Exception as e:
            logger.error(f"Failed to delegate approval {approval_id}: {e}")
            raise
    
    async def escalate_approval(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        escalation_reason: str,
        escalated_by: str,
        escalate_to: List[str]
    ) -> Optional[ApprovalDetail]:
        """
        Manually escalate an approval.
        
        Args:
            approval_id: Approval ID
            tenant_id: Tenant ID
            escalation_reason: Reason for escalation
            escalated_by: User performing escalation
            escalate_to: Users to escalate to
        
        Returns:
            Updated approval details or None if failed
        """
        try:
            success = await self.workflow_manager.escalate_approval(
                approval_id=approval_id,
                escalation_reason=escalation_reason,
                escalated_by=escalated_by,
                escalate_to=escalate_to
            )
            
            if not success:
                logger.warning(f"Escalation failed for approval {approval_id}")
                return None
            
            approval_detail = await self.get_approval(approval_id, tenant_id)
            
            # Send escalation notifications
            await self._handle_escalation_notifications(
                approval_detail, escalation_reason, escalated_by, escalate_to
            )
            
            logger.info(f"Escalated approval {approval_id} to {escalate_to}")
            return approval_detail
            
        except Exception as e:
            logger.error(f"Failed to escalate approval {approval_id}: {e}")
            raise
    
    async def get_approval(
        self,
        approval_id: UUID,
        tenant_id: UUID
    ) -> Optional[ApprovalDetail]:
        """Get approval details with workflow status."""
        try:
            # Get basic approval details
            approval = await self.approval_repository.get_approval(approval_id, tenant_id)
            if not approval:
                return None
            
            # Get workflow status if available
            workflow_status = await self.workflow_manager.get_workflow_status(approval_id)
            
            # Enhance approval with workflow information
            if workflow_status:
                approval.workflow_instance_id = workflow_status.instance_id
                approval.workflow_current_step = workflow_status.current_step
                approval.workflow_status = workflow_status.status
                approval.workflow_step_statuses = workflow_status.step_statuses
            
            return approval
            
        except Exception as e:
            logger.error(f"Failed to get approval {approval_id}: {e}")
            return None
    
    async def get_pending_approvals(
        self,
        tenant_id: UUID,
        approver_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[ApprovalDetail]:
        """Get pending approvals for a user with workflow information."""
        try:
            # Get pending approvals from workflow manager
            workflow_approvals = await self.workflow_manager.get_pending_approvals_by_user(
                user_id=approver_id,
                tenant_id=tenant_id
            )
            
            # Convert to approval details
            approvals = []
            for workflow_approval in workflow_approvals[offset:offset+limit]:
                approval_id = UUID(workflow_approval["approval_id"])
                approval_detail = await self.get_approval(approval_id, tenant_id)
                if approval_detail:
                    approvals.append(approval_detail)
            
            logger.info(f"Retrieved {len(approvals)} pending approvals for {approver_id}")
            return approvals
            
        except Exception as e:
            logger.error(f"Failed to get pending approvals: {e}")
            return []
    
    async def get_workflow_audit_trail(
        self,
        approval_id: UUID,
        tenant_id: UUID
    ) -> List[AuditLogEntry]:
        """Get complete audit trail for an approval."""
        try:
            audit_trail = await self.workflow_manager.get_workflow_audit_trail(approval_id)
            logger.info(f"Retrieved {len(audit_trail)} audit entries for {approval_id}")
            return audit_trail
            
        except Exception as e:
            logger.error(f"Failed to get audit trail: {e}")
            return []
    
    async def handle_timeouts_and_escalations(self) -> Dict[str, int]:
        """Handle all workflow timeouts and escalations."""
        try:
            result = await self.workflow_manager.handle_workflow_timeouts()
            logger.info(f"Processed {result['processed_count']} timeout/escalation events")
            return result
            
        except Exception as e:
            logger.error(f"Failed to handle timeouts and escalations: {e}")
            raise
    
    async def _handle_approval_notifications(
        self,
        approval: ApprovalDetail,
        result: Dict[str, Any],
        requester_contacts: Dict[str, str]
    ):
        """Handle notifications for approval responses."""
        try:
            if result.get("approved"):
                # Check if workflow is complete
                if approval.status == ApprovalStatus.APPROVED:
                    # Notify requester of final approval
                    await self.notification_service.send_approval_granted(
                        approval=approval,
                        approver_id=result["approver_id"],
                        requester_contacts=requester_contacts
                    )
                else:
                    # Notify of step completion, more approvals needed
                    await self.notification_service.send_approval_step_completed(
                        approval=approval,
                        approver_id=result["approver_id"],
                        requester_contacts=requester_contacts
                    )
            
        except Exception as e:
            logger.error(f"Failed to send approval notifications: {e}")
    
    async def _handle_rejection_notifications(
        self,
        approval: ApprovalDetail,
        result: Dict[str, Any],
        requester_contacts: Dict[str, str]
    ):
        """Handle notifications for rejection responses."""
        try:
            await self.notification_service.send_approval_rejected(
                approval=approval,
                rejector_id=result["approver_id"],
                rejection_reason=result.get("comments", "No reason provided"),
                requester_contacts=requester_contacts
            )
            
        except Exception as e:
            logger.error(f"Failed to send rejection notifications: {e}")
    
    async def _handle_delegation_notifications(
        self,
        approval: ApprovalDetail,
        current_approver: str,
        delegate_to: str,
        reason: Optional[str]
    ):
        """Handle notifications for delegations."""
        try:
            # Notify the delegate
            await self.notification_service.send_approval_delegated(
                approval=approval,
                delegated_from=current_approver,
                delegated_to=delegate_to,
                reason=reason
            )
            
        except Exception as e:
            logger.error(f"Failed to send delegation notifications: {e}")
    
    async def _handle_escalation_notifications(
        self,
        approval: ApprovalDetail,
        escalation_reason: str,
        escalated_by: str,
        escalate_to: List[str]
    ):
        """Handle notifications for escalations."""
        try:
            # Notify escalated approvers
            for escalated_approver in escalate_to:
                await self.notification_service.send_approval_escalated(
                    approval=approval,
                    escalated_by=escalated_by,
                    escalated_to=escalated_approver,
                    reason=escalation_reason
                )
            
        except Exception as e:
            logger.error(f"Failed to send escalation notifications: {e}")


# Backward compatibility wrapper
class ApprovalServiceWrapper:
    """Wrapper to maintain backward compatibility while using enhanced service."""
    
    def __init__(self, enhanced_service: EnhancedApprovalService):
        self.enhanced_service = enhanced_service
    
    async def create_approval_request(self, tenant_id: UUID, clarification_id: str, clarification: Dict, requester_contacts: Dict):
        """Backward compatible create approval request."""
        return await self.enhanced_service.create_approval_request(
            tenant_id=tenant_id,
            clarification_id=clarification_id,
            clarification=clarification,
            requester_contacts=requester_contacts
        )
    
    async def approve_request(self, approval_id: UUID, tenant_id: UUID, response: Dict, requester_contacts: Dict):
        """Backward compatible approve request."""
        return await self.enhanced_service.approve_request(
            approval_id=approval_id,
            tenant_id=tenant_id,
            response=response,
            requester_contacts=requester_contacts
        )
    
    async def reject_request(self, approval_id: UUID, tenant_id: UUID, response: Dict, requester_contacts: Dict):
        """Backward compatible reject request."""
        return await self.enhanced_service.reject_request(
            approval_id=approval_id,
            tenant_id=tenant_id,
            response=response,
            requester_contacts=requester_contacts
        )
    
    async def delegate_approval(self, approval_id: UUID, tenant_id: UUID, current_approver: str, delegate_to: str):
        """Backward compatible delegate approval."""
        return await self.enhanced_service.delegate_approval(
            approval_id=approval_id,
            tenant_id=tenant_id,
            current_approver=current_approver,
            delegate_to=delegate_to
        )
    
    async def get_approval(self, approval_id: UUID, tenant_id: UUID):
        """Backward compatible get approval."""
        return await self.enhanced_service.get_approval(approval_id, tenant_id)
    
    async def get_pending_approvals(self, tenant_id: UUID, approver_id: str, limit: int = 50, offset: int = 0):
        """Backward compatible get pending approvals."""
        return await self.enhanced_service.get_pending_approvals(tenant_id, approver_id, limit, offset)
