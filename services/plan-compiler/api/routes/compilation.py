"""Compilation endpoints."""

import asyncio
from typing import Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
import structlog

from api.dependencies import get_plan_compiler, get_tenant_id, get_user_id
from src.compiler import PlanCompiler, CapsuleDefinition
from src.models import CompilationRequest, CompilationResult, CompilationJob

logger = structlog.get_logger(__name__)

router = APIRouter()

# In-memory job storage (in production, use Redis or database)
compilation_jobs: Dict[str, CompilationJob] = {}


class CompileRequest(BaseModel):
    """Request to compile a Capsule."""
    
    capsule_definition: Dict[str, Any]
    optimization_level: str = "standard"
    validate_dependencies: bool = True
    cache_result: bool = True
    variables: Dict[str, Any] = {}
    configuration: Dict[str, Any] = {}


class CompileResponse(BaseModel):
    """Response from compilation request."""
    
    job_id: str
    status: str
    message: str


@router.post("/compile", response_model=CompileResponse)
async def compile_capsule(
    request: CompileRequest,
    background_tasks: BackgroundTasks,
    async_compilation: bool = Query(default=True, description="Whether to compile asynchronously"),
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
    compiler: PlanCompiler = Depends(get_plan_compiler)
):
    """
    Compile a Capsule to ExecutablePlan.
    
    Supports both synchronous and asynchronous compilation:
    - async_compilation=true: Returns job_id immediately, compile in background
    - async_compilation=false: Waits for compilation to complete before returning
    """
    
    try:
        # Validate capsule definition
        if not request.capsule_definition:
            raise HTTPException(status_code=400, detail="Capsule definition is required")
        
        # Create compilation job
        job_id = str(uuid4())
        
        job = CompilationJob(
            job_id=job_id,
            tenant_id=tenant_id,
            capsule_id=request.capsule_definition.get('id', UUID('00000000-0000-0000-0000-000000000000')),
            status="pending",
            created_at=datetime.now(timezone.utc)
        )
        
        compilation_jobs[job_id] = job
        
        if async_compilation:
            # Start compilation in background
            background_tasks.add_task(
                _compile_capsule_async,
                job_id,
                request,
                tenant_id,
                user_id,
                compiler
            )
            
            logger.info(
                "Async compilation job started",
                job_id=job_id,
                tenant_id=str(tenant_id),
                user_id=str(user_id)
            )
            
            return CompileResponse(
                job_id=job_id,
                status="pending",
                message="Compilation job started asynchronously"
            )
        else:
            # Compile synchronously
            await _compile_capsule_async(job_id, request, tenant_id, user_id, compiler)
            
            # Get the completed job
            completed_job = compilation_jobs[job_id]
            
            if completed_job.status == "completed" and completed_job.result:
                logger.info(
                    "Sync compilation completed successfully",
                    job_id=job_id,
                    plan_hash=completed_job.result.plan.plan_hash if completed_job.result.plan else None
                )
                
                return CompileResponse(
                    job_id=job_id,
                    status="completed",
                    message="Compilation completed successfully"
                )
            else:
                error_msg = completed_job.error_message or "Compilation failed"
                logger.error(
                    "Sync compilation failed",
                    job_id=job_id,
                    error=error_msg
                )
                
                raise HTTPException(
                    status_code=400,
                    detail=f"Compilation failed: {error_msg}"
                )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start compilation", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start compilation: {str(e)}")


@router.get("/compile/status/{job_id}")
async def get_compilation_status(
    job_id: str,
    include_result: bool = Query(default=False, description="Whether to include compilation result"),
    tenant_id: UUID = Depends(get_tenant_id)
):
    """
    Get compilation job status.
    
    Returns job status, progress, and optionally the full compilation result.
    """
    
    if job_id not in compilation_jobs:
        raise HTTPException(status_code=404, detail="Compilation job not found")
    
    job = compilation_jobs[job_id]
    
    # Check tenant access
    if job.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to compilation job")
    
    # Create response with optional result filtering
    response_data = job.model_dump()
    
    if not include_result and job.result:
        # Remove the full result to reduce response size
        response_data["result"] = {
            "success": job.result.success,
            "compilation_time": job.result.compilation_time,
            "errors": job.result.errors,
            "warnings": job.result.warnings,
            "plan_hash": job.result.plan.plan_hash if job.result.plan else None
        }
    
    logger.info(
        "Compilation status retrieved",
        job_id=job_id,
        status=job.status,
        progress=job.progress,
        tenant_id=str(tenant_id)
    )
    
    return response_data


async def _compile_capsule_async(
    job_id: str,
    request: CompileRequest,
    tenant_id: UUID,
    user_id: UUID,
    compiler: PlanCompiler
):
    """Compile capsule asynchronously."""
    
    job = compilation_jobs[job_id]
    
    try:
        # Update job status
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.current_step = "Validating capsule definition"
        job.progress = 0.1
        
        # Parse and validate capsule definition
        try:
            capsule = CapsuleDefinition(**request.capsule_definition)
        except Exception as e:
            raise ValueError(f"Invalid capsule definition: {str(e)}")
        
        # Update progress
        job.progress = 0.2
        job.current_step = "Resolving dependencies"
        
        # Create compilation request
        compilation_request = CompilationRequest(
            capsule_id=request.capsule_definition.get('id', UUID('00000000-0000-0000-0000-000000000000')),
            optimization_level=request.optimization_level,
            validate_dependencies=request.validate_dependencies,
            cache_result=request.cache_result,
            variables=request.variables or {},
            configuration=request.configuration or {}
        )
        
        # Update progress
        job.progress = 0.4
        job.current_step = "Compiling capsule to executable plan"
        
        # Compile capsule
        result = await compiler.compile_capsule(
            capsule=capsule,
            tenant_id=tenant_id,
            compiled_by=user_id,
            request=compilation_request
        )
        
        # Update progress
        job.progress = 0.8
        job.current_step = "Finalizing compilation"
        
        # Cache the compiled plan if successful and caching is enabled
        if result.success and result.plan and request.cache_result:
            from src.cache_service import get_cache_service
            cache_service = get_cache_service()
            await cache_service.put(
                result.plan,
                tags=[
                    f"capsule:{request.capsule_definition.get('name', 'unknown')}",
                    f"optimization:{request.optimization_level}",
                    "api_compiled"
                ]
            )
            
        # Update job with result
        job.status = "completed" if result.success else "failed"
        job.progress = 1.0
        job.current_step = "Completed"
        job.completed_at = datetime.now(timezone.utc)
        job.result = result
        
        if not result.success:
            job.error_message = "; ".join(result.errors) if result.errors else "Unknown compilation error"
        
        logger.info(
            "Compilation job completed",
            job_id=job_id,
            success=result.success,
            compilation_time=result.compilation_time,
            plan_hash=result.plan.plan_hash if result.plan else None,
            tenant_id=str(tenant_id)
        )
        
    except Exception as e:
        logger.error(
            "Compilation job failed",
            job_id=job_id,
            error=str(e),
            tenant_id=str(tenant_id)
        )
        
        job.status = "failed"
        job.error_message = str(e)
        job.progress = 0.0
        job.completed_at = datetime.now(timezone.utc)
        job.current_step = "Failed"