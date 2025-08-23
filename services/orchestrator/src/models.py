"""Orchestrator service data models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExecutionStatusEnum(str, Enum):
    """Execution status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ClarificationStatus(str, Enum):
    """Clarification status enumeration."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class RetryPolicy(BaseModel):
    """Retry policy configuration."""
    
    max_attempts: int = Field(default=3, description="Maximum retry attempts")
    initial_delay: float = Field(default=1.0, description="Initial delay in seconds")
    max_delay: float = Field(default=60.0, description="Maximum delay in seconds")
    exponential_base: float = Field(default=2.0, description="Exponential backoff base")
    jitter: bool = Field(default=True, description="Add random jitter to delays")


class ExecutionHook(BaseModel):
    """Execution hook configuration."""
    
    hook_type: str = Field(..., description="Hook type (pre_execution, post_step, etc.)")
    enabled: bool = Field(default=True, description="Whether hook is enabled")
    configuration: Dict[str, Any] = Field(default_factory=dict, description="Hook configuration")


class CapabilityValidation(BaseModel):
    """Capability token validation result."""
    
    valid: bool = Field(..., description="Whether capability is valid")
    token_id: Optional[str] = Field(None, description="Capability token ID")
    capabilities: List[str] = Field(default_factory=list, description="Validated capabilities")
    expires_at: Optional[datetime] = Field(None, description="Token expiration time")
    error_message: Optional[str] = Field(None, description="Validation error message")


class PortiaPlan(BaseModel):
    """Portia Plan representation."""
    
    plan_id: str = Field(..., description="Portia plan ID")
    name: str = Field(..., description="Plan name")
    description: Optional[str] = Field(None, description="Plan description")
    
    # Plan definition in Portia format
    steps: List[Dict[str, Any]] = Field(..., description="Plan steps")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Plan variables")
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(..., description="Creator identifier")
    
    # Execution configuration
    timeout: Optional[int] = Field(None, description="Plan timeout in seconds")
    retry_policy: Optional[RetryPolicy] = Field(None, description="Retry policy")


class PortiaPlanRun(BaseModel):
    """Portia PlanRun representation."""
    
    run_id: str = Field(..., description="Portia run ID")
    plan_id: str = Field(..., description="Associated plan ID")
    
    # Execution state
    status: ExecutionStatusEnum = Field(default=ExecutionStatusEnum.PENDING)
    started_at: Optional[datetime] = Field(None, description="Execution start time")
    completed_at: Optional[datetime] = Field(None, description="Execution completion time")
    
    # Execution context
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Execution parameters")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Runtime variables")
    
    # Results and progress
    results: Dict[str, Any] = Field(default_factory=dict, description="Execution results")
    progress: float = Field(default=0.0, description="Execution progress (0.0 to 1.0)")
    current_step: Optional[str] = Field(None, description="Current executing step")
    
    # Error information
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_details: Dict[str, Any] = Field(default_factory=dict, description="Detailed error info")
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    triggered_by: str = Field(..., description="User who triggered execution")


class Clarification(BaseModel):
    """Portia Clarification for approvals."""
    
    clarification_id: str = Field(..., description="Clarification ID")
    run_id: str = Field(..., description="Associated run ID")
    
    # Clarification details
    title: str = Field(..., description="Clarification title")
    description: str = Field(..., description="Clarification description")
    clarification_type: str = Field(default="approval", description="Type of clarification")
    
    # Approval context
    required_approvers: List[str] = Field(..., description="Required approver IDs")
    approval_rules: List[str] = Field(default_factory=list, description="Approval rule references")
    
    # Status and timing
    status: ClarificationStatus = Field(default=ClarificationStatus.PENDING)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    responded_at: Optional[datetime] = Field(None, description="Response timestamp")
    timeout_at: Optional[datetime] = Field(None, description="Timeout timestamp")
    
    # Response details
    approver_id: Optional[str] = Field(None, description="Approver who responded")
    response_reason: Optional[str] = Field(None, description="Approval/rejection reason")
    response_metadata: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class ExecutionRequest(BaseModel):
    """Request to execute an ExecutablePlan."""
    
    # Plan identification
    plan_hash: str = Field(..., description="ExecutablePlan hash")
    tenant_id: UUID = Field(..., description="Tenant ID")
    
    # Execution parameters
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Execution parameters")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Variable overrides")
    
    # Execution options
    dry_run: bool = Field(default=False, description="Whether to perform dry run")
    async_execution: bool = Field(default=True, description="Whether to execute asynchronously")
    
    # Hooks and validation
    hooks: List[ExecutionHook] = Field(default_factory=list, description="Execution hooks")
    validate_capabilities: bool = Field(default=True, description="Whether to validate capabilities")
    
    # Retry and timeout
    retry_policy: Optional[RetryPolicy] = Field(None, description="Custom retry policy")
    timeout: Optional[int] = Field(None, description="Execution timeout in seconds")
    
    # Metadata
    triggered_by: UUID = Field(..., description="User who triggered execution")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")


class ExecutionResponse(BaseModel):
    """Response from execution request."""
    
    success: bool = Field(..., description="Whether execution was initiated successfully")
    run_id: Optional[str] = Field(None, description="Portia run ID (if successful)")
    
    # Execution details
    status: ExecutionStatusEnum = Field(default=ExecutionStatusEnum.PENDING)
    estimated_duration: Optional[int] = Field(None, description="Estimated duration in seconds")
    
    # Error information
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_code: Optional[str] = Field(None, description="Error code")
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = Field(None, description="Correlation ID")


class ExecutionStatusModel(BaseModel):
    """Current execution status."""
    
    run_id: str = Field(..., description="Portia run ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    
    # Status information
    status: ExecutionStatusEnum = Field(..., description="Current status")
    progress: float = Field(default=0.0, description="Execution progress")
    current_step: Optional[str] = Field(None, description="Current step")
    
    # Timing information
    started_at: Optional[datetime] = Field(None, description="Start time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion")
    
    # Results and errors
    results: Dict[str, Any] = Field(default_factory=dict, description="Execution results")
    error_message: Optional[str] = Field(None, description="Error message")
    
    # Clarifications
    pending_clarifications: List[Clarification] = Field(default_factory=list, description="Pending clarifications")
    
    # Metadata
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IdempotencyKey(BaseModel):
    """Idempotency key for execution requests."""
    
    key: str = Field(..., description="Idempotency key")
    tenant_id: UUID = Field(..., description="Tenant ID")
    
    # Request fingerprint
    request_hash: str = Field(..., description="Hash of original request")
    
    # Execution tracking
    run_id: Optional[str] = Field(None, description="Associated run ID")
    status: ExecutionStatusEnum = Field(default=ExecutionStatusEnum.PENDING)
    
    # Timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(..., description="Key expiration time")
    
    # Response caching
    cached_response: Optional[ExecutionResponse] = Field(None, description="Cached response")


class ExecutionMetrics(BaseModel):
    """Execution metrics and statistics."""
    
    run_id: str = Field(..., description="Run ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    
    # Performance metrics
    total_duration: Optional[float] = Field(None, description="Total execution time in seconds")
    step_durations: Dict[str, float] = Field(default_factory=dict, description="Individual step durations")
    
    # Resource usage
    cpu_usage: Optional[float] = Field(None, description="CPU usage percentage")
    memory_usage: Optional[float] = Field(None, description="Memory usage in MB")
    
    # Execution statistics
    steps_completed: int = Field(default=0, description="Number of completed steps")
    steps_failed: int = Field(default=0, description="Number of failed steps")
    retry_count: int = Field(default=0, description="Number of retries performed")
    
    # Capability usage
    capabilities_used: List[str] = Field(default_factory=list, description="Capabilities used during execution")
    
    # Progress tracking
    progress: float = Field(default=0.0, description="Execution progress (0.0 to 1.0)")
    current_step: Optional[str] = Field(None, description="Current executing step")
    status: ExecutionStatusEnum = Field(default=ExecutionStatusEnum.PENDING, description="Current status")
    
    # Step tracking
    step_start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Current step start time")
    step_metrics: Dict[str, Any] = Field(default_factory=dict, description="Step-specific metrics")
    
    # Error tracking
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    # Timestamps
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))