"""Plan management endpoints."""

from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import structlog

from api.dependencies import get_plan_validator, get_tenant_id
from src.validator import PlanValidator
from src.models import ExecutablePlan, PlanValidationResult, PlanCacheEntry
from src.cache_service import get_cache_service

logger = structlog.get_logger(__name__)

router = APIRouter()

# In-memory plan storage (in production, use database) - kept for backward compatibility
cached_plans: Dict[str, ExecutablePlan] = {}
plan_cache_metadata: Dict[str, PlanCacheEntry] = {}


class PlanResponse(BaseModel):
    """Response model for plan retrieval."""
    
    plan: ExecutablePlan
    cache_metadata: Optional[Dict[str, Any]] = None


@router.get("/plans/{plan_hash}", response_model=PlanResponse)
async def get_plan(
    plan_hash: str,
    include_cache_metadata: bool = Query(default=False, description="Include cache metadata in response"),
    tenant_id: UUID = Depends(get_tenant_id)
):
    """
    Retrieve a compiled ExecutablePlan by hash.
    
    Returns the cached ExecutablePlan if it exists and the tenant has access.
    Optionally includes cache metadata such as access count and last accessed time.
    """
    
    cache_service = get_cache_service()
    
    # Try to get from enhanced cache service first
    plan = await cache_service.get(plan_hash, tenant_id)
    
    if not plan:
        # Fallback to legacy cache for backward compatibility
        if plan_hash not in cached_plans:
            logger.warning(
                "Plan not found in cache",
                plan_hash=plan_hash,
                tenant_id=str(tenant_id)
            )
            raise HTTPException(status_code=404, detail="Plan not found")
        
        plan = cached_plans[plan_hash]
        
        # Check tenant access for legacy cache
        if plan.tenant_id != tenant_id:
            logger.warning(
                "Unauthorized plan access attempt",
                plan_hash=plan_hash,
                plan_tenant_id=str(plan.tenant_id),
                requesting_tenant_id=str(tenant_id)
            )
            raise HTTPException(status_code=403, detail="Access denied to plan")
    
    # Prepare response
    response_data = {"plan": plan}
    
    if include_cache_metadata:
        # Get cache statistics from enhanced cache service
        cache_stats = await cache_service.get_stats()
        response_data["cache_metadata"] = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "access_count": cache_stats.hit_count,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "cache_hit_ratio": cache_stats.hit_ratio,
            "total_cached_plans": cache_stats.total_entries
        }
    
    logger.info(
        "Plan retrieved successfully",
        plan_hash=plan_hash,
        tenant_id=str(tenant_id)
    )
    
    return PlanResponse(**response_data)


class ValidationRequest(BaseModel):
    """Request model for plan validation."""
    
    validation_level: str = "standard"  # standard, strict, security-focused
    include_performance_analysis: bool = True
    check_security_policies: bool = True
    validate_resource_requirements: bool = True


@router.post("/plans/{plan_hash}/validate", response_model=PlanValidationResult)
async def validate_plan(
    plan_hash: str,
    validation_request: Optional[ValidationRequest] = None,
    tenant_id: UUID = Depends(get_tenant_id),
    validator: PlanValidator = Depends(get_plan_validator)
):
    """
    Validate an ExecutablePlan.
    
    Performs comprehensive validation including:
    - Structural validation of the plan
    - Security policy compliance
    - Resource requirement validation
    - Performance analysis (optional)
    """
    
    if plan_hash not in cached_plans:
        logger.warning(
            "Plan validation attempted on non-existent plan",
            plan_hash=plan_hash,
            tenant_id=str(tenant_id)
        )
        raise HTTPException(status_code=404, detail="Plan not found")
    
    plan = cached_plans[plan_hash]
    
    # Check tenant access
    if plan.tenant_id != tenant_id:
        logger.warning(
            "Unauthorized plan validation attempt",
            plan_hash=plan_hash,
            plan_tenant_id=str(plan.tenant_id),
            requesting_tenant_id=str(tenant_id)
        )
        raise HTTPException(status_code=403, detail="Access denied to plan")
    
    # Use default validation request if none provided
    if validation_request is None:
        validation_request = ValidationRequest()
    
    try:
        # Perform validation with specified options
        result = await validator.validate_plan(
            plan,
            validation_level=validation_request.validation_level,
            include_performance_analysis=validation_request.include_performance_analysis,
            check_security_policies=validation_request.check_security_policies,
            validate_resource_requirements=validation_request.validate_resource_requirements
        )
        
        logger.info(
            "Plan validation completed",
            plan_hash=plan_hash,
            tenant_id=str(tenant_id),
            validation_level=validation_request.validation_level,
            valid=result.valid,
            errors_count=len(result.errors),
            warnings_count=len(result.warnings),
            security_issues_count=len(result.security_issues)
        )
        
        return result
        
    except Exception as e:
        logger.error(
            "Plan validation failed",
            plan_hash=plan_hash,
            tenant_id=str(tenant_id),
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


class PlanSummary(BaseModel):
    """Summary information for a plan in list responses."""
    
    plan_hash: str
    name: str
    version: str
    description: Optional[str]
    compiled_at: datetime
    compiled_by: UUID
    optimization_level: str
    validation_status: str
    estimated_duration: Optional[int]
    estimated_cost: Optional[float]


class PlanListResponse(BaseModel):
    """Response model for plan listing."""
    
    plans: list[PlanSummary]
    total: int
    limit: int
    offset: int
    has_more: bool


@router.get("/plans", response_model=PlanListResponse)
async def list_plans(
    tenant_id: UUID = Depends(get_tenant_id),
    limit: int = Query(default=50, ge=1, le=100, description="Number of plans to return"),
    offset: int = Query(default=0, ge=0, description="Number of plans to skip"),
    name_filter: Optional[str] = Query(default=None, description="Filter plans by name (partial match)"),
    optimization_level: Optional[str] = Query(default=None, description="Filter by optimization level"),
    validation_status: Optional[str] = Query(default=None, description="Filter by validation status")
):
    """
    List cached plans for a tenant with filtering and pagination.
    
    Returns a paginated list of plan summaries with optional filtering by:
    - Plan name (partial match)
    - Optimization level
    - Validation status
    """
    
    # Filter plans by tenant
    tenant_plans = [
        plan for plan in cached_plans.values()
        if plan.tenant_id == tenant_id
    ]
    
    # Apply filters
    if name_filter:
        tenant_plans = [
            plan for plan in tenant_plans
            if name_filter.lower() in plan.name.lower()
        ]
    
    if optimization_level:
        tenant_plans = [
            plan for plan in tenant_plans
            if plan.metadata.optimization_level == optimization_level
        ]
    
    if validation_status:
        tenant_plans = [
            plan for plan in tenant_plans
            if plan.metadata.validation_status == validation_status
        ]
    
    # Sort by compilation time (newest first)
    tenant_plans.sort(key=lambda p: p.metadata.compiled_at, reverse=True)
    
    # Apply pagination
    total_count = len(tenant_plans)
    paginated_plans = tenant_plans[offset:offset + limit]
    has_more = offset + limit < total_count
    
    # Convert to summary format
    plan_summaries = [
        PlanSummary(
            plan_hash=plan.plan_hash,
            name=plan.name,
            version=plan.version,
            description=plan.description,
            compiled_at=plan.metadata.compiled_at,
            compiled_by=plan.metadata.compiled_by,
            optimization_level=plan.metadata.optimization_level,
            validation_status=plan.metadata.validation_status,
            estimated_duration=plan.metadata.estimated_duration,
            estimated_cost=plan.metadata.estimated_cost
        )
        for plan in paginated_plans
    ]
    
    logger.info(
        "Plans listed successfully",
        tenant_id=str(tenant_id),
        total_count=total_count,
        returned_count=len(plan_summaries),
        limit=limit,
        offset=offset,
        filters={
            "name_filter": name_filter,
            "optimization_level": optimization_level,
            "validation_status": validation_status
        }
    )
    
    return PlanListResponse(
        plans=plan_summaries,
        total=total_count,
        limit=limit,
        offset=offset,
        has_more=has_more
    )


@router.get("/cache/stats")
async def get_cache_stats(
    tenant_id: UUID = Depends(get_tenant_id)
):
    """
    Get cache statistics and performance metrics.
    
    Returns comprehensive cache statistics including hit ratios, 
    entry counts, and performance metrics.
    """
    
    cache_service = get_cache_service()
    stats = await cache_service.get_stats()
    
    logger.info(
        "Cache statistics retrieved",
        tenant_id=str(tenant_id),
        hit_ratio=stats.hit_ratio,
        total_entries=stats.total_entries
    )
    
    return {
        "cache_stats": stats.model_dump(),
        "tenant_id": str(tenant_id),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.delete("/cache/invalidate/{plan_hash}")
async def invalidate_plan_cache(
    plan_hash: str,
    tenant_id: UUID = Depends(get_tenant_id)
):
    """
    Invalidate a specific plan from cache.
    
    Removes the specified plan from cache, forcing recompilation
    on next access.
    """
    
    cache_service = get_cache_service()
    
    # Verify the plan belongs to the tenant before invalidation
    plan = await cache_service.get(plan_hash, tenant_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or access denied")
    
    success = await cache_service.invalidate(plan_hash)
    
    if success:
        logger.info(
            "Plan cache invalidated",
            plan_hash=plan_hash,
            tenant_id=str(tenant_id)
        )
        return {"message": "Plan cache invalidated successfully", "plan_hash": plan_hash}
    else:
        raise HTTPException(status_code=500, detail="Failed to invalidate plan cache")


@router.delete("/cache/invalidate/tenant")
async def invalidate_tenant_cache(
    tenant_id: UUID = Depends(get_tenant_id)
):
    """
    Invalidate all cached plans for the current tenant.
    
    Removes all plans belonging to the tenant from cache.
    """
    
    cache_service = get_cache_service()
    count = await cache_service.invalidate_by_tenant(tenant_id)
    
    logger.info(
        "Tenant cache invalidated",
        tenant_id=str(tenant_id),
        invalidated_count=count
    )
    
    return {
        "message": f"Invalidated {count} cached plans for tenant",
        "tenant_id": str(tenant_id),
        "invalidated_count": count
    }