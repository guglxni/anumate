"""
Workflow API Endpoints for A.21 Implementation

Additional API endpoints to expose workflow engine capabilities including
workflow status, audit trails, escalation, and timeo        except Exception as e:
        logger.error(f"Failed to get workflow status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get workflow status"
        )


@workflow_router.post(
    "/{workflow_id}/approve-step",
    response_model=Dict[str, Any],
    responses={
        404: {"model": ErrorResponse, "description": "Workflow not found"},
        400: {"model": ErrorResponse, "description": "Invalid approval request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Approve Workflow Step",
    description="Approve the current step in a multi-step workflow and advance to the next step."
)
async def approve_workflow_step(
    workflow_id: UUID,
    approval_data: Dict[str, Any],
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Approve a step in the workflow."""
    try:
        logger.info(f"Approving step for workflow {workflow_id} by {approval_data.get('approver_id')}")
        
        # Mock step approval processing
        step_result = {
            "workflow_id": str(workflow_id),
            "step_approved": True,
            "approver_id": approval_data.get('approver_id'),
            "approved_at": datetime.utcnow().isoformat(),
            "comments": approval_data.get('comments'),
            "next_step": {
                "step_number": 3,
                "step_name": "Product Owner Approval",
                "approver": "product-owner@company.com"
            },
            "workflow_status": "pending_approval",
            "message": "Step approved successfully, workflow advanced to next step"
        }
        
        return step_result
        
    except Exception as e:
        logger.error(f"Failed to approve workflow step: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve workflow step"
        )


@workflow_router.post(
    "/{workflow_id}/escalate",
    response_model=Dict[str, Any],
    responses={
        404: {"model": ErrorResponse, "description": "Workflow not found"},
        400: {"model": ErrorResponse, "description": "Invalid escalation request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Escalate Workflow",
    description="Escalate a workflow due to timeout or manual intervention."
)
async def escalate_workflow(
    workflow_id: UUID,
    escalation_data: Dict[str, Any],
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Escalate a workflow."""
    try:
        logger.info(f"Escalating workflow {workflow_id}: {escalation_data.get('reason')}")
        
        # Mock escalation processing
        escalation_result = {
            "workflow_id": str(workflow_id),
            "escalated": True,
            "reason": escalation_data.get('reason'),
            "escalated_to": escalation_data.get('escalate_to', []),
            "escalated_at": datetime.utcnow().isoformat(),
            "original_approver": "ops-team@company.com",
            "new_approvers": escalation_data.get('escalate_to', ["manager@company.com"]),
            "message": "Workflow escalated successfully"
        }
        
        return escalation_result
        
    except Exception as e:
        logger.error(f"Failed to escalate workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to escalate workflow"
        )


@workflow_router.post(
    "/check-timeouts",
    response_model=Dict[str, Any],
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Check Workflow Timeouts",
    description="Manually trigger timeout checks and automatic escalations for all active workflows."
)
async def check_workflow_timeouts(
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Check for workflow timeouts and trigger escalations."""
    try:
        logger.info("Checking workflow timeouts for automatic escalation")
        
        # Mock timeout check results
        timeout_results = {
            "checked_workflows": 5,
            "escalated_workflows": 2,
            "escalations": [
                {
                    "workflow_id": str(UUID()),
                    "reason": "timeout_exceeded",
                    "original_approver": "ops-team@company.com",
                    "escalated_to": ["manager@company.com"],
                    "timeout_hours": 24
                },
                {
                    "workflow_id": str(UUID()),
                    "reason": "timeout_exceeded", 
                    "original_approver": "security-team@company.com",
                    "escalated_to": ["security-manager@company.com"],
                    "timeout_hours": 48
                }
            ],
            "checked_at": datetime.utcnow().isoformat(),
            "message": "Timeout check completed successfully"
        }
        
        return timeout_results
        
    except Exception as e:
        logger.error(f"Failed to check timeouts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check workflow timeouts"
        )


@workflow_router.get(
    "/audit",
    response_model=Dict[str, Any],
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get Workflow Audit Trail",
    description="Get comprehensive audit trail for all workflow activities."
)
async def get_workflow_audit_trail(
    tenant_id: UUID = Depends(get_tenant_id),
    limit: int = Query(100, description="Maximum number of audit entries"),
    offset: int = Query(0, description="Offset for pagination"),
):
    """Get workflow audit trail."""
    try:
        logger.info(f"Getting workflow audit trail for tenant {tenant_id}")
        
        # Mock audit trail
        audit_entries = [
            {
                "log_id": str(UUID()),
                "workflow_id": str(UUID()),
                "event_type": "workflow.created",
                "actor_id": "developer@company.com",
                "actor_type": "user",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "title": "Production Deployment Approval",
                    "steps": 3,
                    "approvers": ["security-team", "ops-team", "product-owner"]
                }
            },
            {
                "log_id": str(UUID()),
                "workflow_id": str(UUID()),
                "event_type": "step.approved",
                "step_number": 1,
                "step_name": "Security Review",
                "actor_id": "security-team@company.com",
                "actor_type": "user",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "approved": True,
                    "comments": "Security review passed"
                }
            },
            {
                "log_id": str(UUID()),
                "workflow_id": str(UUID()),
                "event_type": "workflow.escalated",
                "actor_id": "system",
                "actor_type": "system",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "reason": "timeout_exceeded",
                    "original_approver": "ops-team@company.com",
                    "escalated_to": ["manager@company.com"]
                }
            }
        ]
        
        return {
            "audit_entries": audit_entries[:limit],
            "total": len(audit_entries),
            "offset": offset,
            "limit": limit,
            "message": "Audit trail retrieved successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to get audit trail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit trail"
        )


@workflow_router.post(
    "/audit/search",
    response_model=Dict[str, Any],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid search criteria"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Search Workflow Audit Trail",
    description="Search audit trail with specific criteria and filters."
)
async def search_workflow_audit(
    search_criteria: Dict[str, Any],
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Search workflow audit trail with specific criteria."""
    try:
        event_types = search_criteria.get('event_types', [])
        date_from = search_criteria.get('date_from')
        date_to = search_criteria.get('date_to')
        limit = search_criteria.get('limit', 50)
        
        logger.info(f"Searching audit trail with criteria: {search_criteria}")
        
        # Mock search results
        search_results = {
            "matches": [
                {
                    "log_id": str(UUID()),
                    "workflow_id": str(UUID()),
                    "event_type": "workflow.created",
                    "timestamp": datetime.utcnow().isoformat(),
                    "actor_id": "developer@company.com",
                    "details": {"title": "Production Deployment"}
                }
            ],
            "total_matches": 1,
            "search_criteria": search_criteria,
            "searched_at": datetime.utcnow().isoformat(),
            "message": "Audit search completed successfully"
        }
        
        return search_results
        
    except Exception as e:
        logger.error(f"Failed to search audit trail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search audit trail"
        )


@workflow_router.get(
    "/audit/export",
    response_model=Dict[str, Any],
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Export Workflow Audit Trail",
    description="Export workflow audit trail in various formats (JSON, CSV, etc.)."
)
async def export_workflow_audit(
    tenant_id: UUID = Depends(get_tenant_id),
    format: str = Query("json", description="Export format (json, csv)"),
    date_from: Optional[str] = Query(None, description="Start date for export"),
    date_to: Optional[str] = Query(None, description="End date for export"),
):
    """Export workflow audit trail."""
    try:
        logger.info(f"Exporting audit trail in {format} format")
        
        # Mock export
        export_result = {
            "export_id": str(UUID()),
            "format": format,
            "records_count": 156,
            "date_range": {
                "from": date_from or (datetime.utcnow()).isoformat(),
                "to": date_to or datetime.utcnow().isoformat()
            },
            "download_url": f"/v1/workflows/audit/download/{UUID()}",
            "expires_at": datetime.utcnow().isoformat(),
            "message": f"Audit trail export prepared in {format} format"
        }
        
        return export_result
        
    except Exception as e:
        logger.error(f"Failed to export audit trail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export audit trail"
        )


@workflow_router.get(
    "/events",
    response_model=Dict[str, Any],
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get Workflow CloudEvents",
    description="Get recent CloudEvents generated by workflow activities."
)
async def get_workflow_events(
    tenant_id: UUID = Depends(get_tenant_id),
    limit: int = Query(50, description="Maximum number of events"),
):
    """Get recent workflow CloudEvents."""
    try:
        logger.info("Getting recent workflow CloudEvents")
        
        # Mock CloudEvents
        events = [
            {
                "specversion": "1.0",
                "type": "io.anumate.workflow.step.completed",
                "source": "anumate.approvals",
                "id": str(UUID()),
                "time": datetime.utcnow().isoformat() + "Z",
                "datacontenttype": "application/json",
                "data": {
                    "workflow_id": str(UUID()),
                    "step_number": 1,
                    "step_name": "Security Review",
                    "approver_id": "security-team@company.com",
                    "approved": True
                }
            },
            {
                "specversion": "1.0",
                "type": "io.anumate.workflow.escalated",
                "source": "anumate.approvals",
                "id": str(UUID()),
                "time": datetime.utcnow().isoformat() + "Z",
                "datacontenttype": "application/json",
                "data": {
                    "workflow_id": str(UUID()),
                    "reason": "timeout_exceeded",
                    "escalated_to": ["manager@company.com"]
                }
            }
        ]
        
        return {
            "events": events[:limit],
            "total": len(events),
            "limit": limit,
            "message": "CloudEvents retrieved successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to get workflow events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow events"
        )


@workflow_router.post(
    "/events/test",
    response_model=Dict[str, Any],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid test request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Test CloudEvents Integration",
    description="Test CloudEvents publishing and webhook delivery for workflow events."
)
async def test_workflow_events(
    test_request: Dict[str, Any],
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Test CloudEvents integration."""
    try:
        event_type = test_request.get('event_type')
        workflow_id = test_request.get('workflow_id')
        
        logger.info(f"Testing CloudEvents for {event_type}")
        
        # Mock event test results
        test_result = {
            "test_id": str(UUID()),
            "event_type": event_type,
            "workflow_id": workflow_id,
            "test_mode": test_request.get('test_mode', True),
            "webhook_delivery": {
                "attempted": True,
                "successful": True,
                "response_code": 200,
                "delivery_time_ms": 156
            },
            "event_published": {
                "nats_subject": f"anumate.workflow.{event_type}",
                "published_at": datetime.utcnow().isoformat(),
                "message_id": str(UUID())
            },
            "message": "CloudEvents test completed successfully"
        }
        
        return test_result
        
    except Exception as e:
        logger.error(f"Failed to test workflow events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test workflow events"
        )agement.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
import logging

from src.models import ApprovalDetail, ErrorResponse
from src.enhanced_service import EnhancedApprovalService
from src.workflow_engine import WorkflowExecution, AuditLogEntry
from dependencies import get_tenant_id, get_enhanced_approval_service

logger = logging.getLogger(__name__)

# Create workflow router
workflow_router = APIRouter(prefix="/v1/workflows", tags=["Workflows"])


@workflow_router.post(
    "/approvals",
    response_model=Dict[str, Any],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid workflow request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Create Multi-Step Approval Workflow",
    description="Create a comprehensive multi-step approval workflow with escalation and timeout handling."
)
async def create_approval_workflow(
    workflow_request: Dict[str, Any],
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new approval workflow with A.21 capabilities."""
    try:
        logger.info(f"Creating workflow for tenant {tenant_id}")
        
        # Extract workflow configuration
        workflow_id = str(UUID())
        clarification = workflow_request.get('clarification', {})
        workflow_config = workflow_request.get('workflow_config', {})
        
        # Create workflow response
        workflow_response = {
            "workflow_id": workflow_id,
            "status": "created",
            "steps": len(clarification.get('approvers', [])),
            "current_step": 1,
            "requires_all_approvers": workflow_config.get('requires_all_approvers', False),
            "timeout_hours": workflow_config.get('timeout_hours', 48),
            "escalation_enabled": workflow_config.get('escalation_enabled', True),
            "created_at": datetime.utcnow().isoformat(),
            "message": "Multi-step approval workflow created successfully"
        }
        
        logger.info(f"Workflow {workflow_id} created with {workflow_response['steps']} steps")
        return workflow_response
        
    except Exception as e:
        logger.error(f"Failed to create workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create approval workflow"
        )


@workflow_router.get(
    "/",
    response_model=Dict[str, Any],
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="List Active Workflows",
    description="Get a list of all active approval workflows with their current status."
)
async def list_workflows(
    tenant_id: UUID = Depends(get_tenant_id),
    status_filter: Optional[str] = Query(None, description="Filter by workflow status"),
):
    """List all workflows for the tenant."""
    try:
        logger.info(f"Listing workflows for tenant {tenant_id}")
        
        # Mock workflow list - in real implementation this would query the database
        workflows = [
            {
                "workflow_id": str(UUID()),
                "status": "pending_approval",
                "current_step": 2,
                "total_steps": 3,
                "created_at": datetime.utcnow().isoformat(),
                "title": "Production Deployment Approval"
            },
            {
                "workflow_id": str(UUID()),
                "status": "completed",
                "current_step": 2,
                "total_steps": 2,
                "created_at": datetime.utcnow().isoformat(),
                "title": "User Permission Change"
            }
        ]
        
        if status_filter:
            workflows = [w for w in workflows if w['status'] == status_filter]
        
        return {
            "workflows": workflows,
            "total": len(workflows),
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflows"
        )


@workflow_router.get(
    "/{workflow_id}/status",
    response_model=Dict[str, Any],
    responses={
        404: {"model": ErrorResponse, "description": "Workflow not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get Workflow Status",
    description="Get detailed status information for a specific workflow including current step and progress."
)
async def get_workflow_status(
    workflow_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get detailed status of a specific workflow."""
    try:
        logger.info(f"Getting status for workflow {workflow_id}")
        
        # Mock workflow status - in real implementation this would query the database
        workflow_status = {
            "workflow_id": str(workflow_id),
            "status": "pending_approval", 
            "current_step": 2,
            "total_steps": 3,
            "progress_percentage": 66.7,
            "steps": [
                {
                    "step_number": 1,
                    "step_name": "Security Review",
                    "status": "completed",
                    "approver": "security-team@company.com",
                    "completed_at": datetime.utcnow().isoformat()
                },
                {
                    "step_number": 2,
                    "step_name": "Operations Review",
                    "status": "pending",
                    "approver": "ops-team@company.com",
                    "due_at": (datetime.utcnow()).isoformat()
                },
                {
                    "step_number": 3,
                    "step_name": "Product Owner Approval",
                    "status": "waiting",
                    "approver": "product-owner@company.com"
                }
            ],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        return workflow_status
        
    except Exception as e:
        logger.error(f"Failed to get workflow status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get workflow status"
        )
    summary="Get Workflow Status",
    description="Retrieve current workflow execution status for an approval."
)
async def get_workflow_status(
    approval_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    service: EnhancedApprovalService = Depends(get_enhanced_approval_service),
):
    """
    Get workflow execution status.
    
    Returns detailed information about the current workflow state,
    including step statuses, progress, and timing information.
    """
    try:
        logger.debug(f"Getting workflow status for approval {approval_id}")
        
        workflow_status = await service.workflow_manager.get_workflow_status(approval_id)
        
        if not workflow_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active workflow found for approval {approval_id}"
            )
        
        return {
            "approval_id": str(approval_id),
            "workflow": {
                "instance_id": str(workflow_status.instance_id),
                "workflow_id": str(workflow_status.workflow_id),
                "current_step": workflow_status.current_step,
                "status": workflow_status.status,
                "step_statuses": workflow_status.step_statuses,
                "started_at": workflow_status.started_at.isoformat(),
                "expires_at": workflow_status.expires_at.isoformat() if workflow_status.expires_at else None,
                "completed_at": workflow_status.completed_at.isoformat() if workflow_status.completed_at else None,
                "execution_context": workflow_status.execution_context,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow status for {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow status"
        )


@workflow_router.get(
    "/{approval_id}/audit",
    response_model=List[Dict[str, Any]],
    responses={
        404: {"model": ErrorResponse, "description": "Approval not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get Audit Trail",
    description="Retrieve complete audit trail for an approval workflow."
)
async def get_audit_trail(
    approval_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    service: EnhancedApprovalService = Depends(get_enhanced_approval_service),
):
    """
    Get comprehensive audit trail.
    
    Returns all workflow events, decisions, and state changes
    for complete transparency and compliance.
    """
    try:
        logger.debug(f"Getting audit trail for approval {approval_id}")
        
        # Verify approval exists
        approval = await service.get_approval(approval_id, tenant_id)
        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Approval {approval_id} not found"
            )
        
        # Get audit trail
        audit_trail = await service.get_workflow_audit_trail(approval_id, tenant_id)
        
        # Format audit entries
        formatted_trail = [
            {
                "log_id": str(entry.log_id),
                "event_type": entry.event_type,
                "actor_id": entry.actor_id,
                "step_number": entry.step_number,
                "timestamp": entry.timestamp.isoformat(),
                "event_data": entry.event_data,
            }
            for entry in audit_trail
        ]
        
        return formatted_trail
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit trail for {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit trail"
        )


@workflow_router.post(
    "/{approval_id}/escalate",
    response_model=ApprovalDetail,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid escalation request"},
        404: {"model": ErrorResponse, "description": "Approval not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Escalate Approval",
    description="Manually escalate an approval to higher-level approvers."
)
async def escalate_approval(
    approval_id: UUID,
    escalation_request: Dict[str, Any],
    tenant_id: UUID = Depends(get_tenant_id),
    service: EnhancedApprovalService = Depends(get_enhanced_approval_service),
):
    """
    Escalate an approval.
    
    Allows authorized users to escalate approvals to higher-level
    approvers when standard workflow timing is insufficient.
    """
    try:
        escalation_reason = escalation_request.get("reason")
        escalated_by = escalation_request.get("escalated_by")
        escalate_to = escalation_request.get("escalate_to", [])
        
        if not all([escalation_reason, escalated_by, escalate_to]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: reason, escalated_by, escalate_to"
            )
        
        logger.info(f"Escalating approval {approval_id} by {escalated_by}")
        
        approval = await service.escalate_approval(
            approval_id=approval_id,
            tenant_id=tenant_id,
            escalation_reason=escalation_reason,
            escalated_by=escalated_by,
            escalate_to=escalate_to
        )
        
        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Approval {approval_id} not found or cannot be escalated"
            )
        
        logger.info(f"Successfully escalated approval {approval_id}")
        return approval
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to escalate approval {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to escalate approval"
        )


@workflow_router.post(
    "/timeouts/process",
    response_model=Dict[str, Any],
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Process Workflow Timeouts",
    description="Manually trigger processing of workflow timeouts and escalations."
)
async def process_timeouts(
    service: EnhancedApprovalService = Depends(get_enhanced_approval_service),
):
    """
    Process workflow timeouts and escalations.
    
    Triggers manual processing of expired workflows and
    automatic escalations. Typically called by scheduled jobs.
    """
    try:
        logger.info("Processing workflow timeouts and escalations")
        
        result = await service.handle_timeouts_and_escalations()
        
        return {
            "processed_count": result["processed_count"],
            "timestamp": result["timestamp"],
            "message": f"Processed {result['processed_count']} timeout/escalation events"
        }
        
    except Exception as e:
        logger.error(f"Failed to process timeouts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process workflow timeouts"
        )


@workflow_router.get(
    "/workflows/definitions",
    response_model=List[Dict[str, Any]],
    summary="List Workflow Definitions",
    description="Get available workflow templates and their configurations."
)
async def list_workflow_definitions(
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    List available workflow definitions.
    
    Returns all workflow templates that can be used for
    creating approval workflows.
    """
    try:
        # Return built-in workflow definitions
        workflows = [
            {
                "type": "simple",
                "name": "Simple Approval",
                "description": "Single-step approval workflow",
                "steps": 1,
                "default_timeout_hours": 72
            },
            {
                "type": "two_step", 
                "name": "Two-Step Approval",
                "description": "Manager and admin approval required",
                "steps": 2,
                "default_timeout_hours": 96
            },
            {
                "type": "security_review",
                "name": "Security Review Workflow", 
                "description": "Multi-step security review for sensitive operations",
                "steps": 3,
                "default_timeout_hours": 120
            }
        ]
        
        return workflows
        
    except Exception as e:
        logger.error(f"Failed to list workflow definitions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow definitions"
        )


@workflow_router.get(
    "/users/{user_id}/pending",
    response_model=List[ApprovalDetail],
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get User Pending Approvals",
    description="Get all pending approvals for a specific user with workflow information."
)
async def get_user_pending_approvals(
    user_id: str,
    tenant_id: UUID = Depends(get_tenant_id),
    limit: int = Query(default=50, description="Maximum number of approvals to return"),
    offset: int = Query(default=0, description="Number of approvals to skip"),
    include_delegated: bool = Query(default=True, description="Include delegated approvals"),
    service: EnhancedApprovalService = Depends(get_enhanced_approval_service),
):
    """
    Get pending approvals for a user.
    
    Returns all approvals waiting for the specified user's
    action, including workflow step information.
    """
    try:
        logger.debug(f"Getting pending approvals for user {user_id}")
        
        approvals = await service.get_pending_approvals(
            tenant_id=tenant_id,
            approver_id=user_id,
            limit=limit,
            offset=offset
        )
        
        logger.info(f"Retrieved {len(approvals)} pending approvals for {user_id}")
        return approvals
        
    except Exception as e:
        logger.error(f"Failed to get pending approvals for {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve pending approvals"
        )


@workflow_router.get(
    "/stats/summary",
    response_model=Dict[str, Any],
    summary="Get Workflow Statistics",
    description="Get summary statistics for workflow processing."
)
async def get_workflow_statistics(
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Get workflow processing statistics.
    
    Returns summary metrics for workflow performance,
    completion rates, and timing information.
    """
    try:
        # Placeholder for workflow statistics
        # In real implementation, this would query the database for metrics
        stats = {
            "active_workflows": 0,
            "completed_today": 0,
            "avg_completion_time_hours": 24.5,
            "approval_rate": 0.85,
            "escalation_rate": 0.12,
            "timeout_rate": 0.03,
            "workflow_types": {
                "simple": {"count": 0, "avg_time_hours": 18.2},
                "two_step": {"count": 0, "avg_time_hours": 36.4},
                "security_review": {"count": 0, "avg_time_hours": 72.1}
            },
            "last_updated": datetime.utcnow().isoformat()
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get workflow statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow statistics"
        )
