"""Policy API endpoints."""

from typing import Annotated, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..dependencies import (
    get_policy_service,
    get_current_tenant,
    get_current_user
)
from ..models import (
    Policy,
    PolicyCreateRequest,
    PolicyUpdateRequest,
    PolicyEvaluateRequest,
    PolicyTestRequest,
    PolicyListResponse,
    PolicyEvaluationResult,
    PolicyTestReport,
    PolicyValidationResult
)
from src.policy_service import PolicyService

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=Policy,
    status_code=status.HTTP_201_CREATED,
    summary="Create new Policy",
    description="Create a new Policy from DSL source code"
)
async def create_policy(
    request: PolicyCreateRequest,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[UUID, Depends(get_current_user)]
) -> Policy:
    """Create a new Policy."""
    try:
        logger.info("Creating new policy", 
                   name=request.name,
                   user_id=str(current_user))
        
        policy_data = await service.create_policy(
            name=request.name,
            source_code=request.source_code,
            created_by=current_user,
            description=request.description,
            metadata=request.metadata,
            enabled=request.enabled
        )
        
        logger.info("Policy created successfully", 
                   policy_id=str(policy_data["policy_id"]),
                   name=request.name)
        
        return Policy(**policy_data)
        
    except ValueError as e:
        logger.warning("Policy creation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Unexpected error creating policy", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "",
    response_model=PolicyListResponse,
    summary="List Policies",
    description="List Policies with pagination and optional filtering"
)
async def list_policies(
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    name: Annotated[Optional[str], Query(description="Filter by name (partial match)")] = None,
    enabled_only: Annotated[bool, Query(description="Show only enabled policies")] = False
) -> PolicyListResponse:
    """List Policies with pagination and filtering."""
    try:
        logger.debug("Listing policies", 
                    tenant_id=str(current_tenant),
                    page=page, 
                    page_size=page_size,
                    name_filter=name,
                    enabled_only=enabled_only)
        
        policies_data, total = await service.list_policies(
            page=page,
            page_size=page_size,
            name_filter=name,
            enabled_only=enabled_only
        )
        
        policies = [Policy(**policy_data) for policy_data in policies_data]
        
        logger.debug("Listed policies successfully", 
                    count=len(policies),
                    total=total)
        
        return PolicyListResponse(
            policies=policies,
            total=total,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error("Error listing policies", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/{policy_id}",
    response_model=Policy,
    summary="Get Policy by ID",
    description="Get a specific Policy by its ID"
)
async def get_policy(
    policy_id: UUID,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> Policy:
    """Get a specific Policy by ID."""
    try:
        logger.debug("Fetching policy", 
                    policy_id=str(policy_id),
                    tenant_id=str(current_tenant))
        
        policy_data = await service.get_policy(policy_id)
        
        if policy_data is None:
            logger.warning("Policy not found", policy_id=str(policy_id))
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy {policy_id} not found"
            )
        
        logger.debug("Policy fetched successfully", 
                    policy_id=str(policy_id))
        
        return Policy(**policy_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching policy", 
                    policy_id=str(policy_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.put(
    "/{policy_id}",
    response_model=Policy,
    summary="Update Policy",
    description="Update an existing Policy"
)
async def update_policy(
    policy_id: UUID,
    request: PolicyUpdateRequest,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> Policy:
    """Update an existing Policy."""
    try:
        logger.info("Updating policy", 
                   policy_id=str(policy_id),
                   tenant_id=str(current_tenant))
        
        policy_data = await service.update_policy(
            policy_id=policy_id,
            name=request.name,
            description=request.description,
            source_code=request.source_code,
            metadata=request.metadata,
            enabled=request.enabled
        )
        
        logger.info("Policy updated successfully", 
                   policy_id=str(policy_id))
        
        return Policy(**policy_data)
        
    except ValueError as e:
        logger.warning("Policy update failed", 
                      policy_id=str(policy_id),
                      error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating policy", 
                    policy_id=str(policy_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Policy",
    description="Soft delete a Policy (sets active=false)"
)
async def delete_policy(
    policy_id: UUID,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> None:
    """Soft delete a Policy."""
    try:
        logger.info("Deleting policy", 
                   policy_id=str(policy_id),
                   tenant_id=str(current_tenant))
        
        success = await service.delete_policy(policy_id)
        
        if not success:
            logger.warning("Policy not found for deletion", 
                          policy_id=str(policy_id))
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy {policy_id} not found"
            )
        
        logger.info("Policy deleted successfully", 
                   policy_id=str(policy_id))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting policy", 
                    policy_id=str(policy_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/{policy_id}/evaluate",
    response_model=PolicyEvaluationResult,
    summary="Evaluate Policy against data",
    description="Evaluate a Policy against input data and return the result"
)
async def evaluate_policy(
    policy_id: UUID,
    request: PolicyEvaluateRequest,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> PolicyEvaluationResult:
    """Evaluate a Policy against input data."""
    try:
        logger.info("Evaluating policy", 
                   policy_id=str(policy_id),
                   tenant_id=str(current_tenant))
        
        result_data = await service.evaluate_policy(
            policy_id=policy_id,
            data=request.data,
            context=request.context
        )
        
        logger.info("Policy evaluated successfully", 
                   policy_id=str(policy_id),
                   allowed=result_data["allowed"])
        
        return PolicyEvaluationResult(**result_data)
        
    except ValueError as e:
        logger.warning("Policy evaluation failed", 
                      policy_id=str(policy_id),
                      error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error evaluating policy", 
                    policy_id=str(policy_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/{policy_id}/test",
    response_model=PolicyTestReport,
    summary="Test Policy with sample data",
    description="Test a Policy with provided test cases and return the test report"
)
async def test_policy(
    policy_id: UUID,
    request: PolicyTestRequest,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> PolicyTestReport:
    """Test a Policy with provided test cases."""
    try:
        logger.info("Testing policy", 
                   policy_id=str(policy_id),
                   tenant_id=str(current_tenant),
                   test_count=len(request.test_cases))
        
        result_data = await service.test_policy(
            policy_id=policy_id,
            test_cases=request.test_cases,
            suite_name=request.suite_name
        )
        
        logger.info("Policy tested successfully", 
                   policy_id=str(policy_id),
                   total_tests=result_data["total_tests"],
                   passed_tests=result_data["passed_tests"])
        
        return PolicyTestReport(**result_data)
        
    except ValueError as e:
        logger.warning("Policy testing failed", 
                      policy_id=str(policy_id),
                      error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error testing policy", 
                    policy_id=str(policy_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


# Additional utility endpoints

@router.post(
    "/validate",
    response_model=PolicyValidationResult,
    summary="Validate Policy DSL source code",
    description="Validate Policy DSL source code without creating a policy"
)
async def validate_policy_source(
    source_code: str,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> PolicyValidationResult:
    """Validate Policy DSL source code without creating a policy."""
    try:
        logger.debug("Validating policy source code", 
                    tenant_id=str(current_tenant))
        
        result_data = await service.validate_policy_source(source_code)
        
        logger.debug("Policy source code validation completed", 
                    valid=result_data["is_valid"],
                    issue_count=len(result_data["issues"]))
        
        return PolicyValidationResult(**result_data)
        
    except Exception as e:
        logger.error("Error validating policy source code", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )