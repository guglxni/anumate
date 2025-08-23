"""Capsule approval workflow integration."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID

import structlog
from anumate_infrastructure.event_bus import EventBus
from anumate_infrastructure.database import DatabaseManager

from .models import Capsule, ApprovalStatus

logger = structlog.get_logger(__name__)


class ApprovalWorkflowManager:
    """Manages Capsule approval workflows."""
    
    def __init__(self, db_manager: DatabaseManager, event_bus: Optional[EventBus] = None):
        """Initialize approval workflow manager."""
        self.db = db_manager
        self.event_bus = event_bus
    
    async def create_approval_request(
        self, 
        capsule: Capsule, 
        requester_id: UUID,
        approval_metadata: Optional[Dict[str, Any]] = None
    ) -> ApprovalStatus:
        """Create a new approval request for a Capsule."""
        logger.info("Creating approval request", 
                   capsule_id=str(capsule.capsule_id),
                   requester_id=str(requester_id))
        
        approval = ApprovalStatus(
            status="pending",
            approval_metadata=approval_metadata or {}
        )
        
        # Store approval request in database
        query = """
            INSERT INTO capsule_approvals (
                capsule_id, requester_id, status, approval_metadata, created_at
            ) VALUES ($1, $2, $3, $4, $5)
            RETURNING approval_id
        """
        
        approval_id = await self.db.fetchval(
            query,
            capsule.capsule_id,
            requester_id,
            approval.status,
            approval.approval_metadata,
            datetime.now(timezone.utc)
        )
        
        # Emit approval request event
        if self.event_bus:
            await self.event_bus.publish("capsule.approval.requested", {
                "approval_id": str(approval_id),
                "capsule_id": str(capsule.capsule_id),
                "capsule_name": capsule.name,
                "capsule_version": capsule.version,
                "requester_id": str(requester_id),
                "metadata": approval.approval_metadata
            })
        
        logger.info("Approval request created", 
                   approval_id=str(approval_id),
                   capsule_id=str(capsule.capsule_id))
        
        return approval
    
    async def approve_capsule(
        self, 
        capsule_id: UUID, 
        approver_id: UUID,
        approval_comments: Optional[str] = None
    ) -> bool:
        """Approve a Capsule."""
        logger.info("Approving capsule", 
                   capsule_id=str(capsule_id),
                   approver_id=str(approver_id))
        
        approved_at = datetime.now(timezone.utc)
        
        # Update approval status
        query = """
            UPDATE capsule_approvals 
            SET status = 'approved', 
                approver_id = $2, 
                approved_at = $3,
                approval_metadata = approval_metadata || $4
            WHERE capsule_id = $1 AND status = 'pending'
            RETURNING approval_id
        """
        
        approval_metadata = {"comments": approval_comments} if approval_comments else {}
        
        approval_id = await self.db.fetchval(
            query,
            capsule_id,
            approver_id,
            approved_at,
            approval_metadata
        )
        
        if not approval_id:
            logger.warning("No pending approval found for capsule", 
                          capsule_id=str(capsule_id))
            return False
        
        # Update capsule validation status
        await self.db.execute(
            "UPDATE capsules SET validation_status = 'approved' WHERE capsule_id = $1",
            capsule_id
        )
        
        # Emit approval event
        if self.event_bus:
            await self.event_bus.publish("capsule.approval.approved", {
                "approval_id": str(approval_id),
                "capsule_id": str(capsule_id),
                "approver_id": str(approver_id),
                "approved_at": approved_at.isoformat(),
                "comments": approval_comments
            })
        
        logger.info("Capsule approved successfully", 
                   capsule_id=str(capsule_id),
                   approval_id=str(approval_id))
        
        return True
    
    async def reject_capsule(
        self, 
        capsule_id: UUID, 
        approver_id: UUID,
        rejection_reason: str
    ) -> bool:
        """Reject a Capsule."""
        logger.info("Rejecting capsule", 
                   capsule_id=str(capsule_id),
                   approver_id=str(approver_id))
        
        # Update approval status
        query = """
            UPDATE capsule_approvals 
            SET status = 'rejected', 
                approver_id = $2, 
                approved_at = $3,
                rejection_reason = $4
            WHERE capsule_id = $1 AND status = 'pending'
            RETURNING approval_id
        """
        
        rejected_at = datetime.now(timezone.utc)
        
        approval_id = await self.db.fetchval(
            query,
            capsule_id,
            approver_id,
            rejected_at,
            rejection_reason
        )
        
        if not approval_id:
            logger.warning("No pending approval found for capsule", 
                          capsule_id=str(capsule_id))
            return False
        
        # Update capsule validation status
        await self.db.execute(
            "UPDATE capsules SET validation_status = 'rejected' WHERE capsule_id = $1",
            capsule_id
        )
        
        # Emit rejection event
        if self.event_bus:
            await self.event_bus.publish("capsule.approval.rejected", {
                "approval_id": str(approval_id),
                "capsule_id": str(capsule_id),
                "approver_id": str(approver_id),
                "rejected_at": rejected_at.isoformat(),
                "rejection_reason": rejection_reason
            })
        
        logger.info("Capsule rejected", 
                   capsule_id=str(capsule_id),
                   approval_id=str(approval_id))
        
        return True
    
    async def get_approval_status(self, capsule_id: UUID) -> Optional[ApprovalStatus]:
        """Get the current approval status for a Capsule."""
        logger.debug("Getting approval status", capsule_id=str(capsule_id))
        
        query = """
            SELECT status, approver_id, approved_at, rejection_reason, approval_metadata
            FROM capsule_approvals 
            WHERE capsule_id = $1 
            ORDER BY created_at DESC 
            LIMIT 1
        """
        
        result = await self.db.fetchrow(query, capsule_id)
        
        if not result:
            logger.debug("No approval record found", capsule_id=str(capsule_id))
            return None
        
        return ApprovalStatus(
            status=result["status"],
            approver_id=result["approver_id"],
            approved_at=result["approved_at"],
            rejection_reason=result["rejection_reason"],
            approval_metadata=result["approval_metadata"] or {}
        )
    
    async def list_pending_approvals(
        self, 
        page: int = 1, 
        page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """List all pending approval requests."""
        logger.debug("Listing pending approvals", page=page, page_size=page_size)
        
        offset = (page - 1) * page_size
        
        query = """
            SELECT 
                ca.approval_id,
                ca.capsule_id,
                ca.requester_id,
                ca.created_at,
                ca.approval_metadata,
                c.name,
                c.version,
                c.tenant_id
            FROM capsule_approvals ca
            JOIN capsules c ON ca.capsule_id = c.capsule_id
            WHERE ca.status = 'pending'
            ORDER BY ca.created_at ASC
            LIMIT $1 OFFSET $2
        """
        
        results = await self.db.fetch(query, page_size, offset)
        
        approvals = []
        for row in results:
            approvals.append({
                "approval_id": row["approval_id"],
                "capsule_id": row["capsule_id"],
                "capsule_name": row["name"],
                "capsule_version": row["version"],
                "tenant_id": row["tenant_id"],
                "requester_id": row["requester_id"],
                "created_at": row["created_at"],
                "metadata": row["approval_metadata"]
            })
        
        logger.debug("Listed pending approvals", count=len(approvals))
        return approvals
    
    async def get_approval_history(self, capsule_id: UUID) -> List[Dict[str, Any]]:
        """Get the approval history for a Capsule."""
        logger.debug("Getting approval history", capsule_id=str(capsule_id))
        
        query = """
            SELECT 
                approval_id,
                status,
                requester_id,
                approver_id,
                created_at,
                approved_at,
                rejection_reason,
                approval_metadata
            FROM capsule_approvals 
            WHERE capsule_id = $1 
            ORDER BY created_at DESC
        """
        
        results = await self.db.fetch(query, capsule_id)
        
        history = []
        for row in results:
            history.append({
                "approval_id": row["approval_id"],
                "status": row["status"],
                "requester_id": row["requester_id"],
                "approver_id": row["approver_id"],
                "created_at": row["created_at"],
                "approved_at": row["approved_at"],
                "rejection_reason": row["rejection_reason"],
                "metadata": row["approval_metadata"]
            })
        
        logger.debug("Retrieved approval history", 
                    capsule_id=str(capsule_id), 
                    record_count=len(history))
        
        return history
    
    async def check_approval_required(self, capsule: Capsule) -> bool:
        """Check if approval is required for a Capsule based on policies."""
        logger.debug("Checking if approval required", 
                    capsule_id=str(capsule.capsule_id))
        
        # Basic approval logic - can be extended with more sophisticated rules
        approval_required = False
        
        # Check if capsule has sensitive tools or policies
        sensitive_tools = {"kubectl", "terraform", "aws-cli", "docker"}
        if any(tool in sensitive_tools for tool in capsule.definition.tools):
            approval_required = True
            logger.debug("Approval required due to sensitive tools", 
                        capsule_id=str(capsule.capsule_id))
        
        # Check if capsule has production policies
        production_policies = {"production", "prod", "critical"}
        if any(policy in production_policies for policy in capsule.definition.policies):
            approval_required = True
            logger.debug("Approval required due to production policies", 
                        capsule_id=str(capsule.capsule_id))
        
        # Check metadata for approval requirements
        if capsule.definition.metadata.get("requires_approval", False):
            approval_required = True
            logger.debug("Approval required due to metadata flag", 
                        capsule_id=str(capsule.capsule_id))
        
        return approval_required
    
    async def auto_approve_if_eligible(self, capsule: Capsule, requester_id: UUID) -> bool:
        """Auto-approve a Capsule if it meets auto-approval criteria."""
        logger.debug("Checking auto-approval eligibility", 
                    capsule_id=str(capsule.capsule_id))
        
        # Basic auto-approval logic
        auto_approve = True
        
        # Don't auto-approve if it has sensitive tools
        sensitive_tools = {"kubectl", "terraform", "aws-cli"}
        if any(tool in sensitive_tools for tool in capsule.definition.tools):
            auto_approve = False
        
        # Don't auto-approve if it has production policies
        production_policies = {"production", "prod", "critical"}
        if any(policy in production_policies for policy in capsule.definition.policies):
            auto_approve = False
        
        # Check metadata
        if capsule.definition.metadata.get("requires_manual_approval", False):
            auto_approve = False
        
        if auto_approve:
            logger.info("Auto-approving capsule", 
                       capsule_id=str(capsule.capsule_id))
            
            # Create and immediately approve
            await self.create_approval_request(capsule, requester_id)
            return await self.approve_capsule(capsule.capsule_id, requester_id, "Auto-approved")
        
        return False