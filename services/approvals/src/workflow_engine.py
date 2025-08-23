"""
Approval Workflow Engine

Enterprise-grade workflow engine for multi-step approval processes with
escalation, timeout handling, and comprehensive audit trails.

Features:
- Multi-step approval workflows
- Approval escalation chains
- Timeout handling with automatic actions
- Comprehensive audit logging
- CloudEvents integration
- Workflow state management
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from uuid import UUID, uuid4
import asyncio
import logging

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, String, Text, Integer, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID as SQLAlchemyUUID

from .models import Base, ApprovalStatus
from .repository import ApprovalRepository


logger = logging.getLogger(__name__)


class WorkflowStepType(str, Enum):
    """Types of workflow steps."""
    APPROVAL = "approval"
    REVIEW = "review"  
    NOTIFICATION = "notification"
    ESCALATION = "escalation"
    TIMEOUT = "timeout"
    CONDITION = "condition"


class WorkflowStepStatus(str, Enum):
    """Status of individual workflow steps."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    EXPIRED = "expired"


class EscalationAction(str, Enum):
    """Actions to take when escalating."""
    NOTIFY_MANAGER = "notify_manager"
    ADD_APPROVER = "add_approver"
    AUTO_APPROVE = "auto_approve"
    AUTO_REJECT = "auto_reject"
    DELEGATE = "delegate"


# Database Models
class WorkflowDefinition(Base):
    """Workflow definition template."""
    __tablename__ = "workflow_definitions"
    
    workflow_id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    
    # Workflow configuration
    steps = Column(JSONB, nullable=False)  # List of workflow steps
    escalation_rules = Column(JSONB, default=list)  # Escalation configuration
    timeout_config = Column(JSONB, default=dict)  # Timeout settings
    
    # Metadata
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(String(255))


class WorkflowInstance(Base):
    """Active workflow instance."""
    __tablename__ = "workflow_instances"
    
    instance_id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False)
    approval_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)
    
    # Current state
    current_step = Column(Integer, default=0)
    status = Column(String(50), default=WorkflowStepStatus.PENDING.value)
    
    # Step tracking
    step_states = Column(JSONB, default=list)  # Status of each step
    execution_context = Column(JSONB, default=dict)  # Runtime variables
    
    # Timing
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    
    # Results
    final_decision = Column(String(50))  # approved, rejected, expired
    completion_reason = Column(Text)


class WorkflowAuditLog(Base):
    """Comprehensive audit trail for workflow execution."""
    __tablename__ = "workflow_audit_logs"
    
    log_id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4)
    instance_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)
    approval_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)
    
    # Event details
    event_type = Column(String(100), nullable=False)  # step_started, step_completed, escalated, etc.
    step_number = Column(Integer)
    step_name = Column(String(255))
    
    # Actor information
    actor_id = Column(String(255))  # Who performed the action
    actor_type = Column(String(50))  # user, system, escalation
    
    # Event data
    event_data = Column(JSONB, default=dict)  # Additional event context
    previous_state = Column(JSONB)  # State before the event
    new_state = Column(JSONB)  # State after the event
    
    # Timing
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Context
    event_metadata = Column(JSONB, default=dict)  # Renamed from 'metadata' to avoid SQLAlchemy conflict


# Pydantic Models
class WorkflowStep(BaseModel):
    """Definition of a workflow step."""
    step_number: int = Field(..., description="Order of execution")
    step_name: str = Field(..., description="Human-readable step name")
    step_type: WorkflowStepType = Field(..., description="Type of workflow step")
    
    # Approval configuration
    required_approvers: List[str] = Field(default=[], description="Required approver IDs")
    approval_count: Optional[int] = Field(None, description="Number of approvals needed")
    requires_all: bool = Field(False, description="Require all approvers")
    
    # Timing
    timeout_hours: Optional[int] = Field(None, description="Step timeout in hours")
    reminder_intervals: List[int] = Field(default=[], description="Reminder intervals in hours")
    
    # Conditions
    conditions: Dict[str, Any] = Field(default_factory=dict, description="Step execution conditions")
    on_timeout: Optional[str] = Field(None, description="Action on timeout")
    
    # Metadata
    description: Optional[str] = Field(None, description="Step description")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional step data")


class EscalationRule(BaseModel):
    """Escalation rule configuration."""
    rule_name: str = Field(..., description="Escalation rule name")
    trigger_after_hours: int = Field(..., description="Hours before escalation triggers")
    escalation_action: EscalationAction = Field(..., description="Action to take")
    
    # Escalation targets
    escalate_to: List[str] = Field(default=[], description="Who to escalate to")
    notification_message: Optional[str] = Field(None, description="Custom escalation message")
    
    # Conditions
    applies_to_steps: List[int] = Field(default=[], description="Which steps this applies to")
    conditions: Dict[str, Any] = Field(default_factory=dict, description="Escalation conditions")


class WorkflowDefinitionModel(BaseModel):
    """Complete workflow definition."""
    name: str = Field(..., description="Workflow name")
    description: Optional[str] = Field(None, description="Workflow description")
    steps: List[WorkflowStep] = Field(..., description="Ordered list of workflow steps")
    escalation_rules: List[EscalationRule] = Field(default=[], description="Escalation rules")
    
    # Global settings
    default_timeout_hours: int = Field(default=72, description="Default step timeout")
    max_timeout_hours: int = Field(default=720, description="Maximum allowed timeout")
    auto_start: bool = Field(True, description="Auto-start workflow on creation")
    
    # Notifications
    completion_notifications: List[str] = Field(default=[], description="Who to notify on completion")
    
    class Config:
        schema_extra = {
            "example": {
                "name": "Standard IT Approval",
                "description": "Standard approval workflow for IT requests",
                "steps": [
                    {
                        "step_number": 1,
                        "step_name": "Team Lead Review",
                        "step_type": "approval",
                        "required_approvers": ["team-lead@company.com"],
                        "approval_count": 1,
                        "timeout_hours": 24,
                        "reminder_intervals": [12]
                    },
                    {
                        "step_number": 2,
                        "step_name": "Security Review",
                        "step_type": "approval", 
                        "required_approvers": ["security-team@company.com"],
                        "approval_count": 1,
                        "timeout_hours": 48,
                        "conditions": {"priority": "high"}
                    }
                ],
                "escalation_rules": [
                    {
                        "rule_name": "Manager Escalation",
                        "trigger_after_hours": 24,
                        "escalation_action": "add_approver",
                        "escalate_to": ["manager@company.com"],
                        "applies_to_steps": [1]
                    }
                ]
            }
        }


class WorkflowExecution(BaseModel):
    """Workflow execution state."""
    instance_id: UUID = Field(..., description="Workflow instance ID")
    workflow_id: UUID = Field(..., description="Workflow definition ID")
    approval_id: UUID = Field(..., description="Associated approval ID")
    
    current_step: int = Field(..., description="Currently executing step")
    status: WorkflowStepStatus = Field(..., description="Overall workflow status")
    
    step_statuses: List[Dict[str, Any]] = Field(..., description="Status of each step")
    execution_context: Dict[str, Any] = Field(default_factory=dict, description="Runtime context")
    
    started_at: datetime = Field(..., description="Workflow start time")
    expires_at: Optional[datetime] = Field(None, description="Workflow expiration time")
    completed_at: Optional[datetime] = Field(None, description="Workflow completion time")


class AuditLogEntry(BaseModel):
    """Audit log entry."""
    log_id: UUID = Field(..., description="Audit log entry ID")
    event_type: str = Field(..., description="Type of event")
    actor_id: Optional[str] = Field(None, description="Who performed the action")
    step_number: Optional[int] = Field(None, description="Step number")
    timestamp: datetime = Field(..., description="When the event occurred")
    event_data: Dict[str, Any] = Field(default_factory=dict, description="Event details")


class WorkflowEngine:
    """Core workflow engine for approval processes."""
    
    def __init__(
        self, 
        repository: ApprovalRepository,
        event_publisher=None,
        notification_service=None
    ):
        """Initialize the workflow engine."""
        self.repository = repository
        self.event_publisher = event_publisher
        self.notification_service = notification_service
        
    async def create_workflow_definition(
        self, 
        tenant_id: UUID,
        workflow_def: WorkflowDefinitionModel,
        created_by: str
    ) -> UUID:
        """Create a new workflow definition."""
        try:
            # Validate workflow definition
            self._validate_workflow_definition(workflow_def)
            
            # Create database entry
            db_workflow = WorkflowDefinition(
                tenant_id=tenant_id,
                name=workflow_def.name,
                description=workflow_def.description,
                steps=[step.dict() for step in workflow_def.steps],
                escalation_rules=[rule.dict() for rule in workflow_def.escalation_rules],
                timeout_config={
                    "default_timeout_hours": workflow_def.default_timeout_hours,
                    "max_timeout_hours": workflow_def.max_timeout_hours,
                    "completion_notifications": workflow_def.completion_notifications,
                },
                created_by=created_by,
            )
            
            # Save to database (placeholder - would use repository)
            logger.info(f"Created workflow definition: {workflow_def.name}")
            
            return db_workflow.workflow_id
            
        except Exception as e:
            logger.error(f"Failed to create workflow definition: {e}")
            raise
    
    async def start_workflow(
        self,
        workflow_id: UUID,
        approval_id: UUID, 
        tenant_id: UUID,
        context: Dict[str, Any] = None
    ) -> UUID:
        """Start a workflow instance for an approval."""
        try:
            # Load workflow definition
            workflow_def = await self._load_workflow_definition(workflow_id, tenant_id)
            if not workflow_def:
                raise ValueError(f"Workflow {workflow_id} not found")
            
            # Calculate expiration based on workflow steps
            total_timeout = self._calculate_total_timeout(workflow_def)
            expires_at = datetime.now(timezone.utc) + timedelta(hours=total_timeout)
            
            # Create workflow instance
            instance = WorkflowInstance(
                workflow_id=workflow_id,
                approval_id=approval_id,
                tenant_id=tenant_id,
                current_step=0,
                status=WorkflowStepStatus.PENDING.value,
                step_states=self._initialize_step_states(workflow_def["steps"]),
                execution_context=context or {},
                expires_at=expires_at,
            )
            
            # Save instance (placeholder)
            logger.info(f"Started workflow instance for approval {approval_id}")
            
            # Create audit log entry
            await self._create_audit_entry(
                instance.instance_id,
                approval_id,
                tenant_id,
                "workflow_started",
                actor_id="system",
                actor_type="system",
                event_data={
                    "workflow_id": str(workflow_id),
                    "context": context,
                    "expires_at": expires_at.isoformat(),
                }
            )
            
            # Start first step
            await self._execute_next_step(instance, workflow_def)
            
            return instance.instance_id
            
        except Exception as e:
            logger.error(f"Failed to start workflow: {e}")
            raise
    
    async def process_approval_response(
        self,
        approval_id: UUID,
        approver_id: str,
        approved: bool,
        comments: Optional[str] = None
    ) -> bool:
        """Process an approval response and advance workflow if needed."""
        try:
            # Find active workflow instance
            instance = await self._load_workflow_instance(approval_id)
            if not instance:
                logger.warning(f"No active workflow for approval {approval_id}")
                return False
            
            # Load workflow definition
            workflow_def = await self._load_workflow_definition(
                instance.workflow_id, 
                instance.tenant_id
            )
            
            # Process the response
            step_completed = await self._process_step_response(
                instance,
                workflow_def,
                approver_id,
                approved,
                comments
            )
            
            # Create audit entry
            await self._create_audit_entry(
                instance.instance_id,
                approval_id,
                instance.tenant_id,
                "approval_response",
                actor_id=approver_id,
                actor_type="user",
                event_data={
                    "approved": approved,
                    "comments": comments,
                    "step_number": instance.current_step,
                    "step_completed": step_completed,
                }
            )
            
            # If step completed, move to next step or complete workflow
            if step_completed:
                await self._advance_workflow(instance, workflow_def)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to process approval response: {e}")
            raise
    
    async def handle_timeouts(self) -> int:
        """Process workflow timeouts and escalations."""
        try:
            processed_count = 0
            
            # Find expired workflow instances
            expired_instances = await self._find_expired_instances()
            
            for instance in expired_instances:
                try:
                    # Load workflow definition
                    workflow_def = await self._load_workflow_definition(
                        instance.workflow_id,
                        instance.tenant_id
                    )
                    
                    # Handle timeout based on configuration
                    await self._handle_instance_timeout(instance, workflow_def)
                    processed_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to handle timeout for instance {instance.instance_id}: {e}")
            
            # Process escalations
            escalation_count = await self._process_escalations()
            
            logger.info(f"Processed {processed_count} timeouts and {escalation_count} escalations")
            return processed_count + escalation_count
            
        except Exception as e:
            logger.error(f"Failed to handle timeouts: {e}")
            raise
    
    def _validate_workflow_definition(self, workflow_def: WorkflowDefinitionModel):
        """Validate workflow definition."""
        if not workflow_def.steps:
            raise ValueError("Workflow must have at least one step")
        
        # Check step numbers are sequential
        step_numbers = [step.step_number for step in workflow_def.steps]
        if step_numbers != list(range(1, len(step_numbers) + 1)):
            raise ValueError("Step numbers must be sequential starting from 1")
        
        # Validate timeout configurations
        for step in workflow_def.steps:
            if step.timeout_hours and step.timeout_hours > workflow_def.max_timeout_hours:
                raise ValueError(f"Step timeout exceeds maximum: {step.timeout_hours}")
    
    def _initialize_step_states(self, steps: List[Dict]) -> List[Dict]:
        """Initialize step states for a workflow instance."""
        return [
            {
                "step_number": step["step_number"],
                "status": WorkflowStepStatus.PENDING.value,
                "started_at": None,
                "completed_at": None,
                "approvals_received": [],
                "approvals_needed": step.get("approval_count", len(step.get("required_approvers", []))),
            }
            for step in steps
        ]
    
    def _calculate_total_timeout(self, workflow_def: Dict) -> int:
        """Calculate total workflow timeout."""
        total = 0
        for step in workflow_def["steps"]:
            step_timeout = step.get("timeout_hours", workflow_def.get("default_timeout_hours", 72))
            total += step_timeout
        return min(total, workflow_def.get("max_timeout_hours", 720))
    
    async def _execute_next_step(self, instance: WorkflowInstance, workflow_def: Dict):
        """Execute the next step in the workflow."""
        if instance.current_step >= len(workflow_def["steps"]):
            # Workflow complete
            await self._complete_workflow(instance, "approved", "All steps completed")
            return
        
        current_step_def = workflow_def["steps"][instance.current_step]
        
        # Update step state
        instance.step_states[instance.current_step]["status"] = WorkflowStepStatus.IN_PROGRESS.value
        instance.step_states[instance.current_step]["started_at"] = datetime.now(timezone.utc).isoformat()
        
        # Create audit entry
        await self._create_audit_entry(
            instance.instance_id,
            instance.approval_id,
            instance.tenant_id,
            "step_started",
            actor_id="system",
            actor_type="system",
            step_number=instance.current_step + 1,
            event_data={
                "step_name": current_step_def["step_name"],
                "step_type": current_step_def["step_type"],
                "required_approvers": current_step_def.get("required_approvers", []),
            }
        )
        
        # Send notifications to required approvers
        if self.notification_service and current_step_def.get("required_approvers"):
            await self._notify_step_approvers(instance, current_step_def)
    
    async def _process_step_response(
        self,
        instance: WorkflowInstance,
        workflow_def: Dict,
        approver_id: str,
        approved: bool,
        comments: Optional[str]
    ) -> bool:
        """Process a response for the current step."""
        current_step_idx = instance.current_step
        current_step_def = workflow_def["steps"][current_step_idx]
        step_state = instance.step_states[current_step_idx]
        
        # Check if approver is authorized for this step
        if approver_id not in current_step_def.get("required_approvers", []):
            logger.warning(f"Approver {approver_id} not authorized for step {current_step_idx + 1}")
            return False
        
        # Check if already responded
        for existing_approval in step_state["approvals_received"]:
            if existing_approval["approver_id"] == approver_id:
                logger.warning(f"Approver {approver_id} already responded to step {current_step_idx + 1}")
                return False
        
        # Record the response
        response_record = {
            "approver_id": approver_id,
            "approved": approved,
            "comments": comments,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        step_state["approvals_received"].append(response_record)
        
        # If rejection, complete step as rejected
        if not approved:
            step_state["status"] = WorkflowStepStatus.COMPLETED.value
            step_state["completed_at"] = datetime.now(timezone.utc).isoformat()
            step_state["final_decision"] = "rejected"
            return True
        
        # Check if step is now complete (enough approvals)
        approvals_count = len([a for a in step_state["approvals_received"] if a["approved"]])
        requires_all = current_step_def.get("requires_all", False)
        required_count = current_step_def.get("approval_count", len(current_step_def.get("required_approvers", [])))
        
        if requires_all:
            step_complete = approvals_count == len(current_step_def.get("required_approvers", []))
        else:
            step_complete = approvals_count >= required_count
        
        if step_complete:
            step_state["status"] = WorkflowStepStatus.COMPLETED.value
            step_state["completed_at"] = datetime.now(timezone.utc).isoformat()
            step_state["final_decision"] = "approved"
            return True
        
        return False
    
    async def _advance_workflow(self, instance: WorkflowInstance, workflow_def: Dict):
        """Advance workflow to next step or complete."""
        current_step_state = instance.step_states[instance.current_step]
        
        # If current step was rejected, complete workflow as rejected
        if current_step_state.get("final_decision") == "rejected":
            await self._complete_workflow(
                instance, 
                "rejected", 
                f"Rejected at step {instance.current_step + 1}"
            )
            return
        
        # Move to next step
        instance.current_step += 1
        
        # Check if workflow is complete
        if instance.current_step >= len(workflow_def["steps"]):
            await self._complete_workflow(instance, "approved", "All steps completed")
            return
        
        # Execute next step
        await self._execute_next_step(instance, workflow_def)
    
    async def _complete_workflow(
        self,
        instance: WorkflowInstance,
        final_decision: str,
        reason: str
    ):
        """Complete the workflow."""
        instance.status = WorkflowStepStatus.COMPLETED.value
        instance.final_decision = final_decision
        instance.completion_reason = reason
        instance.completed_at = datetime.now(timezone.utc)
        
        # Create audit entry
        await self._create_audit_entry(
            instance.instance_id,
            instance.approval_id,
            instance.tenant_id,
            "workflow_completed",
            actor_id="system",
            actor_type="system",
            event_data={
                "final_decision": final_decision,
                "reason": reason,
                "total_steps": len(instance.step_states),
                "duration_minutes": (
                    instance.completed_at - instance.started_at
                ).total_seconds() / 60,
            }
        )
        
        # Publish CloudEvent
        if self.event_publisher:
            await self._publish_completion_event(instance, final_decision)
        
        logger.info(f"Completed workflow {instance.instance_id} with decision: {final_decision}")
    
    async def _publish_completion_event(self, instance: WorkflowInstance, decision: str):
        """Publish approval completion CloudEvent."""
        try:
            event_data = {
                "approval_id": str(instance.approval_id),
                "tenant_id": str(instance.tenant_id),
                "decision": decision,
                "workflow_id": str(instance.workflow_id),
                "instance_id": str(instance.instance_id),
                "completed_at": instance.completed_at.isoformat(),
                "duration_seconds": (
                    instance.completed_at - instance.started_at
                ).total_seconds(),
            }
            
            event_type = f"approval.{decision}"  # approval.granted, approval.rejected
            
            await self.event_publisher.publish(
                event_type=event_type,
                data=event_data,
                source="anumate.approvals.workflow",
                subject=f"approval.{instance.approval_id}",
            )
            
            logger.info(f"Published {event_type} event for approval {instance.approval_id}")
            
        except Exception as e:
            logger.error(f"Failed to publish completion event: {e}")
    
    async def _create_audit_entry(
        self,
        instance_id: UUID,
        approval_id: UUID,
        tenant_id: UUID,
        event_type: str,
        actor_id: Optional[str] = None,
        actor_type: str = "system",
        step_number: Optional[int] = None,
        event_data: Dict[str, Any] = None,
        previous_state: Dict[str, Any] = None,
        new_state: Dict[str, Any] = None,
    ):
        """Create comprehensive audit log entry."""
        try:
            audit_entry = WorkflowAuditLog(
                instance_id=instance_id,
                approval_id=approval_id,
                tenant_id=tenant_id,
                event_type=event_type,
                step_number=step_number,
                actor_id=actor_id,
                actor_type=actor_type,
                event_data=event_data or {},
                previous_state=previous_state,
                new_state=new_state,
            )
            
            # Save to database (placeholder)
            logger.debug(f"Created audit entry: {event_type} for {instance_id}")
            
        except Exception as e:
            logger.error(f"Failed to create audit entry: {e}")
    
    async def _load_workflow_definition(self, workflow_id: UUID, tenant_id: UUID) -> Optional[Dict]:
        """Load workflow definition from database."""
        # Placeholder - would query database
        return {
            "workflow_id": workflow_id,
            "tenant_id": tenant_id,
            "name": "Default Workflow",
            "steps": [
                {
                    "step_number": 1,
                    "step_name": "Initial Approval",
                    "step_type": "approval",
                    "required_approvers": ["admin@example.com"],
                    "timeout_hours": 24,
                }
            ],
            "default_timeout_hours": 24,
            "max_timeout_hours": 168,
        }
    
    async def _load_workflow_instance(self, approval_id: UUID) -> Optional[WorkflowInstance]:
        """Load active workflow instance for approval."""
        # Placeholder - would query database
        return None
    
    async def _find_expired_instances(self) -> List[WorkflowInstance]:
        """Find workflow instances that have expired."""
        # Placeholder - would query database for instances where expires_at < now
        return []
    
    async def _handle_instance_timeout(self, instance: WorkflowInstance, workflow_def: Dict):
        """Handle timeout for a specific workflow instance."""
        logger.info(f"Handling timeout for workflow instance {instance.instance_id}")
        
        # Complete workflow as expired
        await self._complete_workflow(
            instance,
            "expired",
            "Workflow timed out"
        )
    
    async def _process_escalations(self) -> int:
        """Process pending escalations."""
        # Placeholder - would implement escalation logic
        return 0
    
    async def _notify_step_approvers(self, instance: WorkflowInstance, step_def: Dict):
        """Send notifications to step approvers."""
        if not self.notification_service:
            return
        
        try:
            approvers = step_def.get("required_approvers", [])
            step_name = step_def.get("step_name", f"Step {step_def['step_number']}")
            
            for approver in approvers:
                await self.notification_service.send_approval_request(
                    approval_id=instance.approval_id,
                    approver_id=approver,
                    title=f"Approval Required: {step_name}",
                    message=f"Your approval is required for workflow step: {step_name}",
                    priority="normal",
                    contact_info={"email": approver}
                )
            
            logger.info(f"Notified {len(approvers)} approvers for step {step_def['step_number']}")
            
        except Exception as e:
            logger.error(f"Failed to notify step approvers: {e}")
