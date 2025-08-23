"""API models for orchestrator service."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models import ExecutionStatusEnum, ClarificationStatus


class ExecutePlanRequest(BaseModel):
    """Request to execute an ExecutablePlan."""
    
    # Plan identification
    plan_hash: str = Field(..., description="ExecutablePlan hash", min_length=1)
    executable_plan: Dict[str, Any] = Field(..., description="ExecutablePlan data")
    
    # Execution parameters
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Execution parameters")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Variable overrides")
    
    # Execution options
    dry_run: bool = Field(default=False, description="Whether to perform dry run")
    async_execution: bool = Field(default=True, description="Whether to execute asynchronously")
    validate_capabilities: bool = Field(default=True, description="Whether to validate capabilities")
    
    # Timeout and retry
    timeout: Optional[int] = Field(None, description="Execution timeout in seconds", gt=0)
    
    # Metadata
    triggered_by: UUID = Field(..., description="User who triggered execution")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")


class ExecutePlanResponse(BaseModel):
    """Response from execute plan request."""
    
    success: bool = Field(..., description="Whether execution was initiated successfully")
    run_id: Optional[str] = Field(None, description="Portia run ID (if successful)")
    
    # Execution details
    status: ExecutionStatusEnum = Field(default=ExecutionStatusEnum.PENDING)
    estimated_duration: Optional[int] = Field(None, description="Estimated duration in seconds")
    
    # Error information
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_code: Optional[str] = Field(None, description="Error code")
    
    # Metadata
    created_at: datetime = Field(..., description="Response creation time")
    correlation_id: Optional[str] = Field(None, description="Correlation ID")


class ClarificationResponse(BaseModel):
    """Clarification details."""
    
    clarification_id: str = Field(..., description="Clarification ID")
    title: str = Field(..., description="Clarification title")
    description: str = Field(..., description="Clarification description")
    clarification_type: str = Field(..., description="Type of clarification")
    
    # Approval context
    required_approvers: List[str] = Field(..., description="Required approver IDs")
    
    # Status and timing
    status: ClarificationStatus = Field(..., description="Clarification status")
    requested_at: datetime = Field(..., description="Request timestamp")
    responded_at: Optional[datetime] = Field(None, description="Response timestamp")
    timeout_at: Optional[datetime] = Field(None, description="Timeout timestamp")
    
    # Response details
    approver_id: Optional[str] = Field(None, description="Approver who responded")
    response_reason: Optional[str] = Field(None, description="Approval/rejection reason")


class ExecutionStatusResponse(BaseModel):
    """Current execution status."""
    
    run_id: str = Field(..., description="Portia run ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    
    # Status information
    status: ExecutionStatusEnum = Field(..., description="Current status")
    progress: float = Field(..., description="Execution progress (0.0 to 1.0)", ge=0.0, le=1.0)
    current_step: Optional[str] = Field(None, description="Current step")
    
    # Timing information
    started_at: Optional[datetime] = Field(None, description="Start time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion")
    
    # Results and errors
    results: Dict[str, Any] = Field(default_factory=dict, description="Execution results")
    error_message: Optional[str] = Field(None, description="Error message")
    
    # Clarifications
    pending_clarifications: List[ClarificationResponse] = Field(
        default_factory=list, 
        description="Pending clarifications"
    )
    
    # Metadata
    last_updated: datetime = Field(..., description="Last update time")


class ExecutionControlResponse(BaseModel):
    """Response from execution control operations (pause/resume/cancel)."""
    
    success: bool = Field(..., description="Whether operation was successful")
    run_id: str = Field(..., description="Portia run ID")
    status: ExecutionStatusEnum = Field(..., description="Current execution status")
    message: Optional[str] = Field(None, description="Operation result message")
    timestamp: datetime = Field(..., description="Operation timestamp")


class ExecutionMetricsResponse(BaseModel):
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
    
    # Error tracking
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    # Timestamps
    recorded_at: datetime = Field(..., description="Metrics recording time")


class ErrorResponse(BaseModel):
    """Error response model."""
    
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    correlation_id: Optional[str] = Field(None, description="Correlation ID")
    timestamp: datetime = Field(..., description="Error timestamp")