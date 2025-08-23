"""Bridge between Portia Clarifications and Anumate Approvals service."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import httpx
try:
    from anumate_infrastructure.event_bus import EventBus
except ImportError:
    EventBus = None

from .models import Clarification, ClarificationStatus
from .portia_client import PortiaClient

# Mock trace_async decorator for development
def trace_async(name):
    """Mock trace_async decorator for development."""
    def decorator(func):
        return func
    return decorator

logger = logging.getLogger(__name__)


class ClarificationsBridgeError(Exception):
    """Clarifications bridge error."""
    pass


class ClarificationsBridge:
    """Bridge between Portia Clarifications and Anumate Approvals."""
    
    def __init__(
        self,
        approvals_base_url: Optional[str] = None,
        event_bus: Optional[Any] = None,
    ):
        """Initialize clarifications bridge.
        
        Args:
            approvals_base_url: Approvals service base URL
            event_publisher: Event publisher for notifications
        """
        # For now, use placeholder URL since Approvals service isn't implemented yet
        self.approvals_base_url = approvals_base_url or "http://localhost:8004"
        self.event_publisher = event_bus  # Use event_bus parameter
        self.timeout = 30.0
    
    @trace_async("clarifications_bridge.create_approval_request")
    async def create_approval_request(
        self,
        clarification: Clarification,
        tenant_id: UUID,
        plan_context: Dict[str, Any],
    ) -> str:
        """Create an approval request from a Portia clarification.
        
        Args:
            clarification: Portia clarification
            tenant_id: Tenant ID
            plan_context: Additional plan context
            
        Returns:
            Approval request ID
            
        Raises:
            ClarificationsBridgeError: If approval creation fails
        """
        try:
            # For now, implement mock approval creation
            approval_id = await self._mock_create_approval(
                clarification=clarification,
                tenant_id=tenant_id,
                plan_context=plan_context,
            )
            
            # Publish approval request event
            if self.event_publisher:
                await self._publish_approval_requested_event(
                    approval_id=approval_id,
                    clarification=clarification,
                    tenant_id=tenant_id,
                )
            
            logger.info(f"Created approval request {approval_id} for clarification {clarification.clarification_id}")
            return approval_id
            
        except Exception as e:
            error_msg = f"Failed to create approval request: {e}"
            logger.error(error_msg)
            raise ClarificationsBridgeError(error_msg) from e
    
    @trace_async("clarifications_bridge.poll_approval_status")
    async def poll_approval_status(
        self,
        approval_id: str,
        tenant_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Poll approval status from Approvals service.
        
        Args:
            approval_id: Approval request ID
            tenant_id: Tenant ID
            
        Returns:
            Approval status data or None if not found
        """
        try:
            # For now, implement mock approval polling
            return await self._mock_poll_approval(approval_id, tenant_id)
            
        except Exception as e:
            logger.error(f"Failed to poll approval status for {approval_id}: {e}")
            return None
    
    @trace_async("clarifications_bridge.respond_to_clarification")
    async def respond_to_clarification(
        self,
        portia_client: PortiaClient,
        clarification_id: str,
        approved: bool,
        approver_id: str,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Clarification:
        """Respond to a Portia clarification with approval decision.
        
        Args:
            portia_client: Portia client instance
            clarification_id: Clarification ID
            approved: Whether approved
            approver_id: Approver user ID
            reason: Approval/rejection reason
            metadata: Additional metadata
            
        Returns:
            Updated clarification
            
        Raises:
            ClarificationsBridgeError: If response fails
        """
        try:
            # Send response to Portia
            clarification = await portia_client.respond_to_clarification(
                clarification_id=clarification_id,
                approved=approved,
                approver_id=approver_id,
                reason=reason,
                metadata=metadata,
            )
            
            # Publish approval response event
            if self.event_publisher:
                await self._publish_approval_responded_event(
                    clarification=clarification,
                    approved=approved,
                    approver_id=approver_id,
                )
            
            logger.info(f"Responded to clarification {clarification_id}: {'approved' if approved else 'rejected'}")
            return clarification
            
        except Exception as e:
            error_msg = f"Failed to respond to clarification {clarification_id}: {e}"
            logger.error(error_msg)
            raise ClarificationsBridgeError(error_msg) from e
    
    async def _mock_create_approval(
        self,
        clarification: Clarification,
        tenant_id: UUID,
        plan_context: Dict[str, Any],
    ) -> str:
        """Mock approval creation for development."""
        # Generate mock approval ID
        approval_id = str(uuid4())
        
        # In a real implementation, this would call the Approvals service
        logger.info(f"Mock: Created approval request {approval_id}")
        logger.info(f"  Title: {clarification.title}")
        logger.info(f"  Description: {clarification.description}")
        logger.info(f"  Required approvers: {clarification.required_approvers}")
        
        return approval_id
    
    async def _mock_poll_approval(
        self,
        approval_id: str,
        tenant_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Mock approval polling for development."""
        # In development, simulate auto-approval after a short delay
        return {
            "approval_id": approval_id,
            "status": "approved",
            "approver_id": "system",
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "reason": "Auto-approved in development mode",
        }
    
    async def _publish_approval_requested_event(
        self,
        approval_id: str,
        clarification: Clarification,
        tenant_id: UUID,
    ) -> None:
        """Publish approval requested event."""
        if not self.event_publisher:
            return
        
        event_data = {
            "approval_id": approval_id,
            "clarification_id": clarification.clarification_id,
            "run_id": clarification.run_id,
            "title": clarification.title,
            "description": clarification.description,
            "required_approvers": clarification.required_approvers,
            "tenant_id": str(tenant_id),
        }
        
        await self.event_publisher.publish(
            event_type="approval.requested",
            data=event_data,
            tenant_id=tenant_id,
        )
    
    async def _publish_approval_responded_event(
        self,
        clarification: Clarification,
        approved: bool,
        approver_id: str,
    ) -> None:
        """Publish approval responded event."""
        if not self.event_publisher:
            return
        
        event_data = {
            "clarification_id": clarification.clarification_id,
            "run_id": clarification.run_id,
            "approved": approved,
            "approver_id": approver_id,
            "response_reason": clarification.response_reason,
            "responded_at": clarification.responded_at.isoformat() if clarification.responded_at else None,
        }
        
        # Extract tenant_id from run_id or clarification metadata
        # For now, we'll need to pass this in or extract from context
        tenant_id = UUID("00000000-0000-0000-0000-000000000000")  # Placeholder
        
        await self.event_publisher.publish(
            event_type="approval.responded",
            data=event_data,
            tenant_id=tenant_id,
        )