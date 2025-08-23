"""
Workflow Management Service

Manages workflow definitions, instances, and provides high-level workflow operations
for the Approvals service integration.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union
from uuid import UUID, uuid4
import asyncio
import logging

from .workflow_engine import (
    WorkflowEngine, 
    WorkflowDefinitionModel, 
    WorkflowExecution, 
    AuditLogEntry,
    WorkflowStepType,
    EscalationAction
)
from .models import ApprovalDetail
from .repository import ApprovalRepository


logger = logging.getLogger(__name__)


class WorkflowManager:
    """High-level workflow management for approvals."""
    
    def __init__(
        self,
        approval_repository: ApprovalRepository,
        event_publisher=None,
        notification_service=None
    ):
        """Initialize workflow manager."""
        self.approval_repository = approval_repository
        self.workflow_engine = WorkflowEngine(
            repository=approval_repository,
            event_publisher=event_publisher,
            notification_service=notification_service
        )
        
        # Built-in workflow definitions
        self.built_in_workflows = self._create_built_in_workflows()
        
    def _create_built_in_workflows(self) -> Dict[str, WorkflowDefinitionModel]:
        """Create standard built-in workflow templates."""
        workflows = {}
        
        # Simple approval workflow
        workflows["simple"] = WorkflowDefinitionModel(
            name="Simple Approval",
            description="Single-step approval workflow",
            steps=[
                {
                    "step_number": 1,
                    "step_name": "Approval Required",
                    "step_type": WorkflowStepType.APPROVAL,
                    "required_approvers": [],  # Will be populated at runtime
                    "approval_count": 1,
                    "timeout_hours": 72,
                    "reminder_intervals": [24, 48]
                }
            ],
            escalation_rules=[
                {
                    "rule_name": "Auto-escalate on timeout",
                    "trigger_after_hours": 48,
                    "escalation_action": EscalationAction.NOTIFY_MANAGER,
                    "escalate_to": [],  # Will be populated at runtime
                    "applies_to_steps": [1]
                }
            ],
            default_timeout_hours=72
        )
        
        # Two-step approval workflow  
        workflows["two_step"] = WorkflowDefinitionModel(
            name="Two-Step Approval",
            description="Manager and admin approval required",
            steps=[
                {
                    "step_number": 1,
                    "step_name": "Manager Review",
                    "step_type": WorkflowStepType.APPROVAL,
                    "required_approvers": [],  # Manager will be added at runtime
                    "approval_count": 1,
                    "timeout_hours": 24,
                    "reminder_intervals": [12]
                },
                {
                    "step_number": 2,
                    "step_name": "Admin Approval",
                    "step_type": WorkflowStepType.APPROVAL,
                    "required_approvers": [],  # Admin will be added at runtime
                    "approval_count": 1,
                    "timeout_hours": 48,
                    "reminder_intervals": [24]
                }
            ],
            escalation_rules=[
                {
                    "rule_name": "Manager escalation",
                    "trigger_after_hours": 12,
                    "escalation_action": EscalationAction.ADD_APPROVER,
                    "escalate_to": [],  # Senior manager
                    "applies_to_steps": [1]
                },
                {
                    "rule_name": "Admin escalation", 
                    "trigger_after_hours": 24,
                    "escalation_action": EscalationAction.NOTIFY_MANAGER,
                    "escalate_to": [],  # Senior admin
                    "applies_to_steps": [2]
                }
            ],
            default_timeout_hours=72
        )
        
        # Security review workflow
        workflows["security_review"] = WorkflowDefinitionModel(
            name="Security Review Workflow",
            description="Multi-step security review for sensitive operations",
            steps=[
                {
                    "step_number": 1,
                    "step_name": "Security Team Review",
                    "step_type": WorkflowStepType.APPROVAL,
                    "required_approvers": [],  # Security team
                    "approval_count": 1,
                    "timeout_hours": 24,
                    "reminder_intervals": [8, 16]
                },
                {
                    "step_number": 2,
                    "step_name": "Compliance Check",
                    "step_type": WorkflowStepType.REVIEW,
                    "required_approvers": [],  # Compliance officer
                    "approval_count": 1,
                    "timeout_hours": 48,
                    "conditions": {"requires_compliance": True}
                },
                {
                    "step_number": 3,
                    "step_name": "Final Security Approval",
                    "step_type": WorkflowStepType.APPROVAL,
                    "required_approvers": [],  # Security manager
                    "approval_count": 1,
                    "timeout_hours": 24,
                    "requires_all": True
                }
            ],
            escalation_rules=[
                {
                    "rule_name": "Security escalation",
                    "trigger_after_hours": 12,
                    "escalation_action": EscalationAction.ADD_APPROVER,
                    "escalate_to": [],  # CISO
                    "applies_to_steps": [1, 3]
                }
            ],
            default_timeout_hours=96
        )
        
        return workflows
    
    async def create_approval_with_workflow(
        self,
        tenant_id: UUID,
        clarification_id: str,
        clarification: Dict[str, Any],
        workflow_type: str = "simple",
        custom_approvers: Optional[List[str]] = None,
        priority: str = "medium",
        context: Optional[Dict[str, Any]] = None
    ) -> UUID:
        """Create approval request with automatic workflow assignment."""
        try:
            # Get or create workflow definition
            workflow_def = await self._get_workflow_definition(
                workflow_type, 
                tenant_id, 
                custom_approvers,
                context
            )
            
            # Create the approval record first
            approval_id = await self._create_approval_record(
                tenant_id=tenant_id,
                clarification_id=clarification_id,
                clarification=clarification,
                priority=priority,
                workflow_type=workflow_type,
                context=context
            )
            
            # Start the workflow
            instance_id = await self.workflow_engine.start_workflow(
                workflow_id=workflow_def.workflow_id,
                approval_id=approval_id,
                tenant_id=tenant_id,
                context={
                    "clarification": clarification,
                    "priority": priority,
                    "approvers": custom_approvers or [],
                    **(context or {})
                }
            )
            
            logger.info(f"Created approval {approval_id} with workflow {workflow_type}")
            return approval_id
            
        except Exception as e:
            logger.error(f"Failed to create approval with workflow: {e}")
            raise
    
    async def process_workflow_response(
        self,
        approval_id: UUID,
        approver_id: str,
        approved: bool,
        comments: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process approval response through workflow engine."""
        try:
            # Process through workflow engine
            workflow_updated = await self.workflow_engine.process_approval_response(
                approval_id=approval_id,
                approver_id=approver_id,
                approved=approved,
                comments=comments
            )
            
            if not workflow_updated:
                logger.warning(f"No active workflow found for approval {approval_id}")
                # Fall back to simple approval update
                return await self._simple_approval_update(
                    approval_id, approver_id, approved, comments
                )
            
            # Get updated approval status
            approval = await self._get_approval_details(approval_id)
            
            return {
                "approval_id": str(approval_id),
                "status": approval.get("status", "unknown"),
                "workflow_updated": True,
                "approver_id": approver_id,
                "approved": approved,
                "comments": comments,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to process workflow response: {e}")
            raise
    
    async def get_workflow_status(self, approval_id: UUID) -> Optional[WorkflowExecution]:
        """Get current workflow execution status."""
        try:
            # Load workflow instance
            instance = await self.workflow_engine._load_workflow_instance(approval_id)
            if not instance:
                return None
            
            return WorkflowExecution(
                instance_id=instance.instance_id,
                workflow_id=instance.workflow_id,
                approval_id=approval_id,
                current_step=instance.current_step,
                status=instance.status,
                step_statuses=instance.step_states,
                execution_context=instance.execution_context,
                started_at=instance.started_at,
                expires_at=instance.expires_at,
                completed_at=instance.completed_at
            )
            
        except Exception as e:
            logger.error(f"Failed to get workflow status: {e}")
            return None
    
    async def get_workflow_audit_trail(self, approval_id: UUID) -> List[AuditLogEntry]:
        """Get complete audit trail for approval workflow."""
        try:
            # Load audit entries from database
            # Placeholder implementation
            return [
                AuditLogEntry(
                    log_id=uuid4(),
                    event_type="workflow_started",
                    actor_id="system",
                    step_number=None,
                    timestamp=datetime.now(timezone.utc),
                    event_data={"approval_id": str(approval_id)}
                )
            ]
            
        except Exception as e:
            logger.error(f"Failed to get audit trail: {e}")
            return []
    
    async def handle_workflow_timeouts(self) -> Dict[str, int]:
        """Handle all workflow timeouts and escalations."""
        try:
            # Process timeouts through workflow engine
            processed = await self.workflow_engine.handle_timeouts()
            
            # Send summary notification if configured
            if processed > 0:
                await self._notify_timeout_summary(processed)
            
            return {
                "processed_count": processed,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to handle workflow timeouts: {e}")
            raise
    
    async def escalate_approval(
        self,
        approval_id: UUID,
        escalation_reason: str,
        escalated_by: str,
        escalate_to: List[str]
    ) -> bool:
        """Manually escalate an approval."""
        try:
            # Load workflow instance
            instance = await self.workflow_engine._load_workflow_instance(approval_id)
            if not instance:
                logger.warning(f"No workflow found for approval {approval_id}")
                return False
            
            # Add escalation approvers to current step
            current_step_state = instance.step_states[instance.current_step]
            workflow_def = await self.workflow_engine._load_workflow_definition(
                instance.workflow_id,
                instance.tenant_id
            )
            
            # Update step configuration to include escalated approvers
            current_step_def = workflow_def["steps"][instance.current_step]
            current_step_def["required_approvers"].extend(escalate_to)
            
            # Create audit entry
            await self.workflow_engine._create_audit_entry(
                instance.instance_id,
                approval_id,
                instance.tenant_id,
                "manual_escalation",
                actor_id=escalated_by,
                actor_type="user",
                step_number=instance.current_step + 1,
                event_data={
                    "escalation_reason": escalation_reason,
                    "escalate_to": escalate_to,
                    "original_approvers": current_step_def.get("required_approvers", [])
                }
            )
            
            # Notify escalated approvers
            if self.workflow_engine.notification_service:
                await self.workflow_engine._notify_step_approvers(instance, current_step_def)
            
            logger.info(f"Escalated approval {approval_id} to {escalate_to}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to escalate approval: {e}")
            return False
    
    async def delegate_workflow_step(
        self,
        approval_id: UUID,
        current_approver: str,
        delegate_to: str,
        delegation_reason: Optional[str] = None
    ) -> bool:
        """Delegate current workflow step to another approver."""
        try:
            # Load workflow instance
            instance = await self.workflow_engine._load_workflow_instance(approval_id)
            if not instance:
                return False
            
            # Verify current approver is authorized
            workflow_def = await self.workflow_engine._load_workflow_definition(
                instance.workflow_id,
                instance.tenant_id
            )
            current_step_def = workflow_def["steps"][instance.current_step]
            
            if current_approver not in current_step_def.get("required_approvers", []):
                logger.warning(f"Approver {current_approver} not authorized for delegation")
                return False
            
            # Replace approver in step definition
            required_approvers = current_step_def["required_approvers"]
            if current_approver in required_approvers:
                idx = required_approvers.index(current_approver)
                required_approvers[idx] = delegate_to
            
            # Create audit entry
            await self.workflow_engine._create_audit_entry(
                instance.instance_id,
                approval_id,
                instance.tenant_id,
                "step_delegated",
                actor_id=current_approver,
                actor_type="user",
                step_number=instance.current_step + 1,
                event_data={
                    "delegated_from": current_approver,
                    "delegated_to": delegate_to,
                    "reason": delegation_reason
                }
            )
            
            # Notify the delegate
            if self.workflow_engine.notification_service:
                await self.workflow_engine._notify_step_approvers(instance, current_step_def)
            
            logger.info(f"Delegated approval step from {current_approver} to {delegate_to}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delegate workflow step: {e}")
            return False
    
    async def get_pending_approvals_by_user(
        self,
        user_id: str,
        tenant_id: UUID,
        include_delegated: bool = True
    ) -> List[Dict[str, Any]]:
        """Get all pending approvals for a specific user."""
        try:
            # This would query the database for active workflow instances
            # where the user is a required approver for the current step
            pending_approvals = []
            
            # Placeholder implementation
            logger.info(f"Retrieved pending approvals for user {user_id}")
            return pending_approvals
            
        except Exception as e:
            logger.error(f"Failed to get pending approvals: {e}")
            return []
    
    async def _get_workflow_definition(
        self,
        workflow_type: str,
        tenant_id: UUID,
        custom_approvers: Optional[List[str]],
        context: Optional[Dict[str, Any]]
    ) -> Any:
        """Get or create workflow definition."""
        # For built-in workflows, customize with provided approvers
        if workflow_type in self.built_in_workflows:
            workflow_def = self.built_in_workflows[workflow_type].copy(deep=True)
            
            # Customize approvers if provided
            if custom_approvers:
                for step in workflow_def.steps:
                    if not step.required_approvers:  # Only set if empty
                        step.required_approvers = custom_approvers[:1]  # First approver for each step
                        custom_approvers = custom_approvers[1:]  # Rotate for multi-step
            
            # Create workflow definition in database
            workflow_id = await self.workflow_engine.create_workflow_definition(
                tenant_id=tenant_id,
                workflow_def=workflow_def,
                created_by="system"
            )
            
            # Return workflow definition with ID
            class WorkflowDefWithId:
                def __init__(self, workflow_id, definition):
                    self.workflow_id = workflow_id
                    self.definition = definition
            
            return WorkflowDefWithId(workflow_id, workflow_def)
        
        # For custom workflows, this would load from database
        raise ValueError(f"Unknown workflow type: {workflow_type}")
    
    async def _create_approval_record(
        self,
        tenant_id: UUID,
        clarification_id: str,
        clarification: Dict[str, Any],
        priority: str,
        workflow_type: str,
        context: Optional[Dict[str, Any]]
    ) -> UUID:
        """Create the base approval record."""
        # This would create an approval record in the database
        approval_id = uuid4()
        
        # Placeholder - would use approval repository
        logger.info(f"Created approval record {approval_id}")
        return approval_id
    
    async def _simple_approval_update(
        self,
        approval_id: UUID,
        approver_id: str,
        approved: bool,
        comments: Optional[str]
    ) -> Dict[str, Any]:
        """Simple approval update without workflow."""
        # Fallback for approvals without active workflows
        return {
            "approval_id": str(approval_id),
            "status": "approved" if approved else "rejected",
            "workflow_updated": False,
            "approver_id": approver_id,
            "approved": approved,
            "comments": comments,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def _get_approval_details(self, approval_id: UUID) -> Dict[str, Any]:
        """Get current approval details."""
        # This would load from database
        return {
            "id": str(approval_id),
            "status": "pending_approval",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def _notify_timeout_summary(self, processed_count: int):
        """Send timeout processing summary notification."""
        if self.workflow_engine.notification_service:
            try:
                # Send to system administrators
                await self.workflow_engine.notification_service.send_notification(
                    recipient="admin@anumate.io",
                    subject="Workflow Timeout Processing Complete",
                    message=f"Processed {processed_count} workflow timeouts and escalations.",
                    channel="email",
                    priority="low"
                )
            except Exception as e:
                logger.error(f"Failed to send timeout summary: {e}")
