"""Execution API routes for orchestrator service."""

import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
# Import from dependencies for demo
from dependencies import TenantContext
# Tracing simplified for demo

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from dependencies import get_orchestrator_service, get_tenant_id, get_tenant_context_dep

# Import from api.models explicitly to avoid conflict with src.models
import importlib.util
spec = importlib.util.spec_from_file_location("api_models", os.path.join(os.path.dirname(__file__), '..', 'models.py'))
api_models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api_models)

ExecutePlanRequest = api_models.ExecutePlanRequest
ExecutePlanResponse = api_models.ExecutePlanResponse  
ExecutionStatusResponse = api_models.ExecutionStatusResponse
ExecutionControlResponse = api_models.ExecutionControlResponse
ExecutionMetricsResponse = api_models.ExecutionMetricsResponse
ErrorResponse = api_models.ErrorResponse
from src.models import ExecutionRequest, ExecutionHook, ClarificationStatus
from src.service import OrchestratorService, OrchestratorServiceError
from src.execute_via_portia import execute_via_portia, ExecutionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["execution"])


@router.post(
    "/execute/portia",
    summary="Execute capsule via Portia with human-in-loop approval and MCP support",
    description="Execute a capsule YAML via Portia Runtime with clarifications bridged to Approvals service. Supports MCP engines for Razorpay integration.",
    responses={
        200: {"description": "Execution completed successfully"},
        400: {"description": "Invalid request"},
        403: {"description": "Capability verification failed"},
        500: {"description": "Internal server error"},
    }
)
async def execute_portia_endpoint(
    request_data: dict = Body(...),
    request: Request = None,
) -> dict:
    """Execute capsule via Portia with human-in-loop clarifications → approvals workflow and MCP support.
    
    Expected JSON payload:
    {
        "capsule_yaml": "string",        # The capsule YAML content (optional for MCP engines)
        "capsule_id": "string",          # The capsule identifier (optional for MCP engines)
        "plan_hash": "string",           # The plan hash for deterministic identification
        "require_approval": true,        # Whether to require human approval for clarifications (default: true)
        "capability_token": "string",    # Optional token for capability verification
        "engine": "string",              # Optional engine: "razorpay_mcp_payment_link", "razorpay_mcp_refund"
        "razorpay": {                    # Razorpay parameters (required for MCP engines)
            "amount": 1000,              # Amount in paise (for payment links)
            "currency": "INR",           # Currency
            "description": "Payment",    # Description
            "customer": {                # Optional customer info
                "name": "John Doe",
                "email": "john@example.com"
            },
            "payment_id": "pay_xxx"      # Required for refunds
        }
    }
    
    MCP Engine Examples:
    
    Payment Link:
    {
        "plan_hash": "payment_link_123",
        "engine": "razorpay_mcp_payment_link",
        "require_approval": true,
        "razorpay": {
            "amount": 1000,
            "currency": "INR", 
            "description": "Demo payment link",
            "customer": {"name": "Judge", "email": "judge@example.com"}
        }
    }
    
    Refund:
    {
        "plan_hash": "refund_456",
        "engine": "razorpay_mcp_refund",
        "require_approval": true,
        "razorpay": {
            "payment_id": "pay_test_123",
            "amount": 500
        }
    }
    
    Returns:
    {
        "plan_id": "string",            # Created Portia plan ID (traditional flow)
        "plan_run_id": "string",        # Created plan run ID
        "status": "string",             # Final execution status
        "receipt_id": "string",         # Written receipt ID (if successful)
        "mcp": {                        # MCP-specific results (for MCP engines)
            "tool": "razorpay.payment_links.create",
            "id": "plink_test_123",
            "short_url": "https://rzp.io/i/abc",
            "status": "created"
        },
        "approvals_count": number,      # Number of approvals processed
        "duration_seconds": number      # Total execution time
    }
    
    Raises:
        HTTPException: If execution fails at any step
    """
    try:
        # Extract required fields
        plan_hash = request_data.get("plan_hash")
        if not plan_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "MISSING_PLAN_HASH",
                    "message": "plan_hash is required",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        
        # Extract optional fields
        capsule_yaml = request_data.get("capsule_yaml")
        capsule_id = request_data.get("capsule_id")
        require_approval = request_data.get("require_approval", True)
        capability_token = request_data.get("capability_token")
        engine = request_data.get("engine")
        razorpay = request_data.get("razorpay", {})
        
        # Extract idempotency key from headers if present
        idempotency_key = request.headers.get("Idempotency-Key") if request else None
        
        # Idempotency handling - combine plan_hash with idempotency key if provided
        execution_key = f"{plan_hash}_{idempotency_key}" if idempotency_key else plan_hash
        logger.info(f"Executing via Portia: engine={engine}, plan_hash={plan_hash}, idem_key={idempotency_key}")
        
        # Simple idempotency cache (in production, use Redis/database)
        if not hasattr(execute_portia_endpoint, '_idempotency_cache'):
            execute_portia_endpoint._idempotency_cache = {}
            
        # Check if this exact execution was already completed
        if execution_key in execute_portia_endpoint._idempotency_cache:
            cached_result = execute_portia_endpoint._idempotency_cache[execution_key]
            logger.info(f"Returning cached idempotent result for key: {execution_key}")
            return cached_result
        
        # MCP engine validation
        if engine:
            if not engine.startswith("razorpay_mcp_"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "INVALID_ENGINE",
                        "message": f"Unsupported engine: {engine}. Supported: razorpay_mcp_payment_link, razorpay_mcp_refund",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
            
            # Validate Razorpay parameters based on engine
            if engine == "razorpay_mcp_payment_link":
                if not razorpay.get("amount"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "MISSING_AMOUNT",
                            "message": "razorpay.amount is required for payment link creation",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                if not razorpay.get("description"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "MISSING_DESCRIPTION",
                            "message": "razorpay.description is required for payment link creation",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
            
            elif engine == "razorpay_mcp_refund":
                if not razorpay.get("payment_id"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "MISSING_PAYMENT_ID",
                            "message": "razorpay.payment_id is required for refund creation",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
        
        # Traditional flow validation
        else:
            if not capsule_yaml:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "MISSING_CAPSULE_YAML", 
                        "message": "capsule_yaml is required for traditional execution (or specify an engine)",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
        
        # Execute via Portia with enhanced MCP support
        result = await execute_via_portia(
            capsule_yaml=capsule_yaml,
            capsule_id=capsule_id,
            plan_hash=plan_hash,
            require_approval=require_approval,
            capability_token=capability_token,
            engine=engine,
            razorpay=razorpay,
            tenant_id=request_data.get("tenant_id", "demo-tenant"),
            actor=request_data.get("actor", "system")
        )
        
        logger.info(f"Portia execution completed: {result}")
        
        # Cache successful result for idempotency
        if execution_key:
            execute_portia_endpoint._idempotency_cache[execution_key] = result
            logger.info(f"Cached result for idempotency key: {execution_key}")
        
        return result
        
    except ExecutionError as e:
        logger.error(f"Portia execution error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "EXECUTION_ERROR",
                "message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Portia execution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR", 
                "message": "An unexpected error occurred during Portia execution",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


@router.post(
    "/execute",
    response_model=ExecutePlanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute ExecutablePlan",
    description="Execute an ExecutablePlan via Portia Runtime",
    responses={
        202: {"description": "Execution initiated successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        403: {"model": ErrorResponse, "description": "Insufficient capabilities"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
# Tracing will be handled by middleware
async def execute_plan(
    request: ExecutePlanRequest,
    tenant_id: Annotated[UUID, Depends(get_tenant_id)],
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context_dep)],
) -> ExecutePlanResponse:
    """Execute an ExecutablePlan via Portia Runtime.
    
    Args:
        request: Execution request
        tenant_id: Tenant ID from header
        orchestrator: Orchestrator service
        tenant_context: Tenant context
        
    Returns:
        Execution response
        
    Raises:
        HTTPException: If execution fails
    """
    try:
        # Set tenant context
        tenant_context.set_tenant_id(tenant_id)
        
        # Convert API request to service request
        execution_request = ExecutionRequest(
            plan_hash=request.plan_hash,
            tenant_id=tenant_id,
            parameters=request.parameters,
            variables=request.variables,
            dry_run=request.dry_run,
            async_execution=request.async_execution,
            validate_capabilities=request.validate_capabilities,
            timeout=request.timeout,
            triggered_by=request.triggered_by,
            correlation_id=request.correlation_id,
            hooks=[],  # Default empty hooks for now
        )
        
        # Execute plan
        response = await orchestrator.execute_plan(
            request=execution_request,
            executable_plan=request.executable_plan,
        )
        
        # Convert service response to API response
        return ExecutePlanResponse(
            success=response.success,
            run_id=response.run_id,
            status=response.status,
            estimated_duration=response.estimated_duration,
            error_message=response.error_message,
            error_code=response.error_code,
            created_at=response.created_at,
            correlation_id=response.correlation_id,
        )
        
    except OrchestratorServiceError as e:
        logger.error(f"Orchestrator service error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ORCHESTRATOR_ERROR",
                "message": str(e),
                "correlation_id": request.correlation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error executing plan: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "correlation_id": request.correlation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


@router.get(
    "/executions/{run_id}",
    response_model=ExecutionStatusResponse,
    summary="Get execution status",
    description="Get the current status of a running execution",
    responses={
        200: {"description": "Execution status retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Execution not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
# Tracing will be handled by middleware
async def get_execution_status(
    run_id: str,
    tenant_id: Annotated[UUID, Depends(get_tenant_id)],
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context_dep)],
) -> ExecutionStatusResponse:
    """Get execution status for a run.
    
    Args:
        run_id: Portia run ID
        tenant_id: Tenant ID from header
        orchestrator: Orchestrator service
        tenant_context: Tenant context
        
    Returns:
        Execution status
        
    Raises:
        HTTPException: If execution not found or error occurs
    """
    try:
        # Set tenant context
        tenant_context.set_tenant_id(tenant_id)
        
        # Get execution status
        status_result = await orchestrator.get_execution_status(
            run_id=run_id,
            tenant_id=tenant_id,
        )
        
        if not status_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "EXECUTION_NOT_FOUND",
                    "message": f"Execution with run_id '{run_id}' not found",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        
        # Convert clarifications to API format
        clarifications = [
            ClarificationResponse(
                clarification_id=c.clarification_id,
                title=c.title,
                description=c.description,
                clarification_type=c.clarification_type,
                required_approvers=c.required_approvers,
                status=c.status,
                requested_at=c.requested_at,
                responded_at=c.responded_at,
                timeout_at=c.timeout_at,
                approver_id=c.approver_id,
                response_reason=c.response_reason,
            )
            for c in status_result.pending_clarifications
        ]
        
        return ExecutionStatusResponse(
            run_id=status_result.run_id,
            tenant_id=status_result.tenant_id,
            status=status_result.status,
            progress=status_result.progress,
            current_step=status_result.current_step,
            started_at=status_result.started_at,
            completed_at=status_result.completed_at,
            estimated_completion=status_result.estimated_completion,
            results=status_result.results,
            error_message=status_result.error_message,
            pending_clarifications=clarifications,
            last_updated=status_result.last_updated,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution status for {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Failed to retrieve execution status",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


@router.post(
    "/executions/{run_id}/pause",
    response_model=ExecutionControlResponse,
    summary="Pause execution",
    description="Pause a running execution",
    responses={
        200: {"description": "Execution paused successfully"},
        404: {"model": ErrorResponse, "description": "Execution not found"},
        409: {"model": ErrorResponse, "description": "Execution cannot be paused"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
# Tracing will be handled by middleware
async def pause_execution(
    run_id: str,
    tenant_id: Annotated[UUID, Depends(get_tenant_id)],
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context_dep)],
) -> ExecutionControlResponse:
    """Pause a running execution.
    
    Args:
        run_id: Portia run ID
        tenant_id: Tenant ID from header
        orchestrator: Orchestrator service
        tenant_context: Tenant context
        
    Returns:
        Control operation response
        
    Raises:
        HTTPException: If operation fails
    """
    try:
        # Set tenant context
        tenant_context.set_tenant_id(tenant_id)
        
        # Pause execution
        success = await orchestrator.pause_execution(
            run_id=run_id,
            tenant_id=tenant_id,
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "PAUSE_FAILED",
                    "message": f"Failed to pause execution '{run_id}'. It may not be running or may not support pausing.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        
        return ExecutionControlResponse(
            success=True,
            run_id=run_id,
            status="paused",  # Assuming paused status
            message="Execution paused successfully",
            timestamp=datetime.now(timezone.utc),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing execution {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Failed to pause execution",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


@router.post(
    "/executions/{run_id}/resume",
    response_model=ExecutionControlResponse,
    summary="Resume execution",
    description="Resume a paused execution",
    responses={
        200: {"description": "Execution resumed successfully"},
        404: {"model": ErrorResponse, "description": "Execution not found"},
        409: {"model": ErrorResponse, "description": "Execution cannot be resumed"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
# Tracing will be handled by middleware
async def resume_execution(
    run_id: str,
    tenant_id: Annotated[UUID, Depends(get_tenant_id)],
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context_dep)],
) -> ExecutionControlResponse:
    """Resume a paused execution.
    
    Args:
        run_id: Portia run ID
        tenant_id: Tenant ID from header
        orchestrator: Orchestrator service
        tenant_context: Tenant context
        
    Returns:
        Control operation response
        
    Raises:
        HTTPException: If operation fails
    """
    try:
        # Set tenant context
        tenant_context.set_tenant_id(tenant_id)
        
        # Resume execution
        success = await orchestrator.resume_execution(
            run_id=run_id,
            tenant_id=tenant_id,
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "RESUME_FAILED",
                    "message": f"Failed to resume execution '{run_id}'. It may not be paused or may have completed.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        
        return ExecutionControlResponse(
            success=True,
            run_id=run_id,
            status="running",  # Assuming running status
            message="Execution resumed successfully",
            timestamp=datetime.now(timezone.utc),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming execution {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Failed to resume execution",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


@router.post(
    "/executions/{run_id}/cancel",
    response_model=ExecutionControlResponse,
    summary="Cancel execution",
    description="Cancel a running or paused execution",
    responses={
        200: {"description": "Execution cancelled successfully"},
        404: {"model": ErrorResponse, "description": "Execution not found"},
        409: {"model": ErrorResponse, "description": "Execution cannot be cancelled"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
# Tracing will be handled by middleware
async def cancel_execution(
    run_id: str,
    tenant_id: Annotated[UUID, Depends(get_tenant_id)],
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context_dep)],
) -> ExecutionControlResponse:
    """Cancel a running or paused execution.
    
    Args:
        run_id: Portia run ID
        tenant_id: Tenant ID from header
        orchestrator: Orchestrator service
        tenant_context: Tenant context
        
    Returns:
        Control operation response
        
    Raises:
        HTTPException: If operation fails
    """
    try:
        # Set tenant context
        tenant_context.set_tenant_id(tenant_id)
        
        # Cancel execution
        success = await orchestrator.cancel_execution(
            run_id=run_id,
            tenant_id=tenant_id,
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "CANCEL_FAILED",
                    "message": f"Failed to cancel execution '{run_id}'. It may have already completed or failed.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        
        return ExecutionControlResponse(
            success=True,
            run_id=run_id,
            status="cancelled",  # Assuming cancelled status
            message="Execution cancelled successfully",
            timestamp=datetime.now(timezone.utc),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling execution {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Failed to cancel execution",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


@router.get(
    "/executions/{run_id}/metrics",
    response_model=ExecutionMetricsResponse,
    summary="Get execution metrics",
    description="Get detailed metrics and statistics for an execution",
    responses={
        200: {"description": "Execution metrics retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Execution not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
# Tracing will be handled by middleware
async def get_execution_metrics(
    run_id: str,
    tenant_id: Annotated[UUID, Depends(get_tenant_id)],
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context_dep)],
) -> ExecutionMetricsResponse:
    """Get execution metrics for a run.
    
    Args:
        run_id: Portia run ID
        tenant_id: Tenant ID from header
        orchestrator: Orchestrator service
        tenant_context: Tenant context
        
    Returns:
        Execution metrics
        
    Raises:
        HTTPException: If execution not found or error occurs
    """
    try:
        # Set tenant context
        tenant_context.set_tenant_id(tenant_id)
        
        # Get execution metrics
        metrics = await orchestrator.get_execution_metrics(run_id)
        
        if not metrics:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "METRICS_NOT_FOUND",
                    "message": f"Metrics for execution '{run_id}' not found",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        
        return ExecutionMetricsResponse(
            run_id=metrics.run_id,
            tenant_id=metrics.tenant_id,
            total_duration=metrics.total_duration,
            step_durations=metrics.step_durations,
            cpu_usage=metrics.cpu_usage,
            memory_usage=metrics.memory_usage,
            steps_completed=metrics.steps_completed,
            steps_failed=metrics.steps_failed,
            retry_count=metrics.retry_count,
            capabilities_used=metrics.capabilities_used,
            progress=metrics.progress,
            current_step=metrics.current_step,
            status=metrics.status,
            error_message=metrics.error_message,
            recorded_at=metrics.recorded_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution metrics for {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Failed to retrieve execution metrics",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )