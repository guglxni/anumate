"""API endpoints for the Approvals service."""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.models import (
    ClarificationRequest,
    ApprovalDetail,
    ApprovalResponseRequest,
    DelegateApprovalRequest,
    ErrorResponse,
)
from src.service import ApprovalService
from dependencies import get_approval_service, get_tenant_id

try:
    from anumate_tenancy import get_tenant_id
    from anumate_http import create_http_client
except ImportError:
    # Mock implementations for development
    def get_tenant_id():
        return UUID("00000000-0000-0000-0000-000000000000")

logger = logging.getLogger(__name__)
router = APIRouter(tags=["approvals"])


def get_tenant_id():
    """Mock function for tenant ID - replace with proper implementation."""
    from uuid import uuid4
    return uuid4()


async def get_approval_service():
    """Mock function for approval service - replace with proper dependency injection."""
    return None
    reason: Optional[str] = Field(None, description="Reason for delegation")
    
    class Config:
        schema_extra = {
            "example": {
                "delegate_to": "backup-approver",
                "reason": "Primary approver unavailable"
            }
        }


class ApprovalListResponse(BaseModel):
    """Response for listing approvals."""
    approvals: List[ApprovalSummary] = Field(..., description="List of approval summaries")
    total_count: int = Field(..., description="Total number of approvals")
    has_more: bool = Field(..., description="Whether more results are available")
    page_size: int = Field(..., description="Number of items per page")
    offset: int = Field(..., description="Offset used for this page")


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[dict] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")


# Core Approval Management Endpoints
@router.post(
    "/v1/approvals", 
    response_model=ApprovalDetail,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Create Approval Request",
    description="Create a new approval request from a Portia clarification or direct request."
)
async def create_approval(
    request: CreateApprovalRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(get_approval_service),
):
    """Create a new approval request.
    
    **Requirements:**
    - POST /v1/approvals - Create new approval request from clarification
    - Approval propagation < 2s SLO (handled by notification service)
    
    **Usage:**
    This endpoint is primarily called by the ClarificationsBridge when Portia
    requires manual approval for plan execution. It can also be used directly
    for creating approval workflows.
    """
    try:
        logger.info(f"Creating approval request for tenant {tenant_id}")
        
        approval = await approval_service.create_approval_request(
            tenant_id=tenant_id,
            approval_data=request.approval_data,
            approver_contacts=request.approver_contacts,
        )
        
        logger.info(f"Created approval {approval.approval_id} for clarification {approval.clarification_id}")
        return approval
        
    except ValueError as e:
        logger.warning(f"Invalid approval request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Invalid request: {e}"
        )
    except Exception as e:
        logger.error(f"Failed to create approval: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to create approval request"
        )


@router.get(
    "/v1/approvals", 
    response_model=ApprovalListResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="List Approvals", 
    description="List approvals with optional filtering by status, approver, or run."
)
async def list_pending_approvals(
    approver_id: Optional[str] = Query(None, description="Filter by approver ID"),
    status: Optional[ApprovalStatus] = Query(None, description="Filter by approval status"),
    run_id: Optional[str] = Query(None, description="Filter by execution run ID"),
    priority: Optional[str] = Query(None, description="Filter by priority level"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(get_approval_service),
):
    """List pending approvals.
    
    **Requirements:**
    - GET /v1/approvals - List pending approvals  
    - Support filtering by approver, status, run_id
    
    **Usage:**
    Used by approval UIs to show pending approvals to users, and by the
    ClarificationsBridge to check approval status.
    """
    try:
        logger.debug(f"Listing approvals for tenant {tenant_id} with filters: "
                    f"approver_id={approver_id}, status={status}, run_id={run_id}")
        
        if status is None and approver_id is not None:
            # If approver_id is specified without status, default to pending
            approvals = await approval_service.list_pending_approvals(
                tenant_id=tenant_id,
                approver_id=approver_id,
                limit=limit,
                offset=offset,
            )
        else:
            # General listing with optional status filter
            approvals = await approval_service.list_approvals(
                tenant_id=tenant_id,
                status=status,
                approver_id=approver_id,
                run_id=run_id,
                limit=limit,
                offset=offset,
            )
        
        # In production, this would use COUNT queries for better performance
        has_more = len(approvals) == limit
        
        return ApprovalListResponse(
            approvals=approvals,
            total_count=len(approvals),  # Simplified for demo
            has_more=has_more,
            page_size=limit,
            offset=offset,
        )
        
    except Exception as e:
        logger.error(f"Failed to list approvals: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to retrieve approvals"
        )


@router.get(
    "/v1/approvals/{approval_id}", 
    response_model=ApprovalDetail,
    responses={
        404: {"model": ErrorResponse, "description": "Approval not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get Approval Details",
    description="Retrieve detailed information about a specific approval request."
)
async def get_approval_details(
    approval_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(get_approval_service),
):
    """Get approval details.
    
    **Requirements:**
    - GET /v1/approvals/{approval_id} - Get approval details
    
    **Usage:**
    Used by approval UIs to show detailed approval information, and by
    administrators to review approval requests.
    """
    try:
        logger.debug(f"Getting approval {approval_id} for tenant {tenant_id}")
        
        approval = await approval_service.get_approval(
            approval_id=approval_id,
            tenant_id=tenant_id,
        )
        
        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Approval {approval_id} not found"
            )
        
        return approval
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get approval {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to retrieve approval"
        )


@router.post(
    "/v1/approvals/{approval_id}/approve", 
    response_model=ApprovalDetail,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid approval request"},
        404: {"model": ErrorResponse, "description": "Approval not found"},
        409: {"model": ErrorResponse, "description": "Approval already processed"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Approve Request",
    description="Approve an approval request. May complete the approval if all requirements are met."
)
async def approve_request(
    approval_id: UUID,
    request: ApprovalResponseRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(get_approval_service),
):
    """Approve a request.
    
    **Requirements:**
    - POST /v1/approvals/{approval_id}/approve - Approve request
    
    **Usage:**
    Called by approvers to grant approval for a request. The system will
    automatically check if all required approvals have been received and
    update the status accordingly.
    """
    try:
        logger.info(f"Processing approval for {approval_id} by {request.response.approver_id}")
        
        # Ensure the response is marked as approved
        request.response.approved = True
        
        approval = await approval_service.approve_request(
            approval_id=approval_id,
            tenant_id=tenant_id,
            response=request.response,
            requester_contacts=request.requester_contacts,
        )
        
        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Approval {approval_id} not found or cannot be approved"
            )
        
        logger.info(f"Approval {approval_id} approved by {request.response.approver_id}, "
                   f"status: {approval.status}")
        return approval
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid approval request for {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to approve request {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to process approval"
        )


@router.post(
    "/v1/approvals/{approval_id}/reject", 
    response_model=ApprovalDetail,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid rejection request"},
        404: {"model": ErrorResponse, "description": "Approval not found"},
        409: {"model": ErrorResponse, "description": "Approval already processed"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Reject Request",
    description="Reject an approval request. This immediately sets the approval status to rejected."
)
async def reject_request(
    approval_id: UUID,
    request: ApprovalResponseRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(get_approval_service),
):
    """Reject a request.
    
    **Requirements:**
    - POST /v1/approvals/{approval_id}/reject - Reject request
    
    **Usage:**
    Called by approvers to reject a request. Rejection immediately completes
    the approval workflow with a rejected status.
    """
    try:
        logger.info(f"Processing rejection for {approval_id} by {request.response.approver_id}")
        
        # Ensure the response is marked as rejected
        request.response.approved = False
        
        approval = await approval_service.reject_request(
            approval_id=approval_id,
            tenant_id=tenant_id,
            response=request.response,
            requester_contacts=request.requester_contacts,
        )
        
        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Approval {approval_id} not found or cannot be rejected"
            )
        
        logger.info(f"Approval {approval_id} rejected by {request.response.approver_id}")
        return approval
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid rejection request for {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to reject request {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to process rejection"
        )


@router.post(
    "/v1/approvals/{approval_id}/delegate", 
    response_model=ApprovalDetail,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid delegation request"},
        404: {"model": ErrorResponse, "description": "Approval not found"},
        409: {"model": ErrorResponse, "description": "Approval cannot be delegated"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Delegate Approval",
    description="Delegate an approval request to another user. The current approver must be authorized."
)
async def delegate_approval(
    approval_id: UUID,
    request: DelegateApprovalRequest,
    current_approver: str = Query(..., description="Current approver ID making the delegation"),
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(get_approval_service),
):
    """Delegate an approval to another user.
    
    **Requirements:**
    - POST /v1/approvals/{approval_id}/delegate - Delegate approval
    
    **Usage:**
    Allows an authorized approver to delegate their approval responsibility
    to another user. Commonly used when an approver is unavailable.
    """
    try:
        logger.info(f"Delegating approval {approval_id} from {current_approver} to {request.delegate_to}")
        
        approval = await approval_service.delegate_approval(
            approval_id=approval_id,
            tenant_id=tenant_id,
            current_approver=current_approver,
            delegate_to=request.delegate_to,
        )
        
        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Approval {approval_id} not found"
            )
        
        logger.info(f"Approval {approval_id} delegated from {current_approver} to {request.delegate_to}")
        return approval
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid delegation request for {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to delegate approval {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to delegate approval"
        )


@router.put("/v1/approvals/{approval_id}", response_model=ApprovalDetail)
async def update_approval(
    approval_id: UUID,
    update_data: ApprovalUpdate,
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(),
):
    """Update an approval request."""
    try:
        from .repository import ApprovalRepository
        # This would need proper dependency injection
        # For now, it's a placeholder
        
        approval = await approval_service.approval_repo.update_approval(
            approval_id=approval_id,
            tenant_id=tenant_id,
            update_data=update_data,
        )
        
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        
        return approval
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update approval: {e}")


@router.delete("/v1/approvals/{approval_id}", response_model=ApprovalDetail)
async def cancel_approval(
    approval_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(),
):
    """Cancel an approval request."""
    try:
        approval = await approval_service.cancel_approval(
            approval_id=approval_id,
            tenant_id=tenant_id,
        )
        
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        
        return approval
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel approval: {e}")


# Integration Endpoints for ClarificationsBridge
@router.get("/v1/internal/approvals/by-clarification/{clarification_id}", response_model=ApprovalDetail)
async def get_approval_by_clarification(
    clarification_id: str,
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(),
):
    """Get approval by clarification ID (internal endpoint).
    
    This endpoint is used by the ClarificationsBridge to poll approval status.
    """
    try:
        approval = await approval_service.get_approval_by_clarification(
            clarification_id=clarification_id,
            tenant_id=tenant_id,
        )
        
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        
        return approval
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get approval: {e}")


# Administrative Endpoints
@router.post("/v1/admin/approvals/cleanup")
async def cleanup_expired_approvals(
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(),
):
    """Clean up expired approval requests."""
    try:
        count = await approval_service.cleanup_expired_approvals()
        
        return {
            "message": f"Cleaned up {count} expired approvals",
            "expired_count": count,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup approvals: {e}")


@router.post("/v1/admin/approvals/reminders")
async def send_approval_reminders(
    hours_before_expiry: int = Query(4, ge=1, le=48, description="Hours before expiry to send reminder"),
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(),
):
    """Send reminder notifications for approvals expiring soon."""
    try:
        count = await approval_service.send_approval_reminders(
            tenant_id=tenant_id,
            hours_before_expiry=hours_before_expiry,
        )
        
        return {
            "message": f"Sent {count} approval reminders",
            "reminder_count": count,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send reminders: {e}")


@router.get("/v1/approvals/statistics")
async def get_approval_statistics(
    tenant_id: UUID = Depends(get_tenant_id),
    approval_service: ApprovalService = Depends(),
):
    """Get approval statistics for the tenant."""
    try:
        stats = approval_service.get_approval_statistics(tenant_id)
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {e}")


# Health Check
@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "anumate-approvals",
    }
