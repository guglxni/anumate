"""GhostRun simulation API routes."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from api.dependencies import get_ghostrun_service, get_tenant_id
from src.models import (
    GhostRunRequest,
    GhostRunStatus,
    PreflightReport,
    SimulationStatus,
    ExecutablePlan,
)
from src.service import GhostRunService
from src.report_storage import report_storage

router = APIRouter(prefix="/v1/ghostrun", tags=["ghostrun"])


class StartSimulationRequest(BaseModel):
    """Request to start a simulation."""
    plan: ExecutablePlan
    simulation_config: GhostRunRequest


class SimulationResponse(BaseModel):
    """Response for simulation operations."""
    success: bool
    message: str
    run_id: Optional[UUID] = None
    status: Optional[GhostRunStatus] = None


@router.post("/", response_model=SimulationResponse)
async def start_ghostrun_simulation(
    request: StartSimulationRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    service: GhostRunService = Depends(get_ghostrun_service)
) -> SimulationResponse:
    """Start a new GhostRun simulation."""
    
    try:
        # Validate plan hash matches request
        if request.simulation_config.plan_hash != request.plan.plan_hash:
            raise HTTPException(
                status_code=400,
                detail="Plan hash mismatch between plan and simulation config"
            )
        
        # Start simulation
        status = await service.start_simulation(
            tenant_id=tenant_id,
            plan=request.plan,
            request=request.simulation_config
        )
        
        return SimulationResponse(
            success=True,
            message="Simulation started successfully",
            run_id=status.run_id,
            status=status
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start simulation: {str(e)}")


@router.get("/{run_id}", response_model=GhostRunStatus)
async def get_ghostrun_status(
    run_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    service: GhostRunService = Depends(get_ghostrun_service)
) -> GhostRunStatus:
    """Get GhostRun simulation status and results."""
    
    status = await service.get_simulation_status(run_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    
    # Verify tenant access
    if status.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to simulation run")
    
    return status


@router.get("/{run_id}/report", response_model=PreflightReport)
async def get_preflight_report(
    run_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    service: GhostRunService = Depends(get_ghostrun_service)
) -> PreflightReport:
    """Get preflight report for a completed simulation."""
    
    # First check if run exists and user has access
    status = await service.get_simulation_status(run_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    
    if status.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to simulation run")
    
    # Get the report
    report = await service.get_preflight_report(run_id)
    
    if not report:
        if status.status == SimulationStatus.COMPLETED:
            raise HTTPException(status_code=500, detail="Report not available for completed run")
        elif status.status == SimulationStatus.FAILED:
            raise HTTPException(status_code=400, detail="Simulation failed, no report available")
        else:
            raise HTTPException(status_code=400, detail="Simulation not yet completed")
    
    return report


@router.post("/{run_id}/cancel", response_model=SimulationResponse)
async def cancel_ghostrun_simulation(
    run_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    service: GhostRunService = Depends(get_ghostrun_service)
) -> SimulationResponse:
    """Cancel a running GhostRun simulation."""
    
    # Check if run exists and user has access
    status = await service.get_simulation_status(run_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    
    if status.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to simulation run")
    
    # Attempt to cancel
    cancelled = await service.cancel_simulation(run_id)
    
    if cancelled:
        return SimulationResponse(
            success=True,
            message="Simulation cancelled successfully",
            run_id=run_id
        )
    else:
        return SimulationResponse(
            success=False,
            message="Simulation could not be cancelled (may already be completed)",
            run_id=run_id
        )


@router.get("/", response_model=List[GhostRunStatus])
async def list_ghostrun_simulations(
    tenant_id: UUID = Depends(get_tenant_id),
    status: Optional[SimulationStatus] = Query(None, description="Filter by simulation status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    service: GhostRunService = Depends(get_ghostrun_service)
) -> List[GhostRunStatus]:
    """List GhostRun simulations for the tenant."""
    
    simulations = await service.list_simulations(tenant_id, status)
    
    # Apply limit
    return simulations[:limit]


class ServiceMetricsResponse(BaseModel):
    """Service metrics response."""
    total_simulations: int
    active_simulations: int
    completed_simulations: int
    success_rate: float
    average_duration_seconds: float
    service_uptime: float


@router.get("/metrics/service", response_model=ServiceMetricsResponse)
async def get_service_metrics(
    service: GhostRunService = Depends(get_ghostrun_service)
) -> ServiceMetricsResponse:
    """Get GhostRun service metrics."""
    
    metrics = await service.get_simulation_metrics()
    
    return ServiceMetricsResponse(**metrics)


class CleanupResponse(BaseModel):
    """Cleanup operation response."""
    success: bool
    message: str
    cleaned_runs: int


@router.post("/admin/cleanup", response_model=CleanupResponse)
async def cleanup_old_simulations(
    max_age_hours: int = Query(24, ge=1, le=168, description="Maximum age in hours"),
    service: GhostRunService = Depends(get_ghostrun_service)
) -> CleanupResponse:
    """Clean up old simulation runs (admin endpoint)."""
    
    try:
        cleaned_runs = await service.cleanup_old_runs(max_age_hours)
        cleaned_reports = await report_storage.cleanup_old_reports(max_age_hours)
        
        total_cleaned = cleaned_runs + cleaned_reports
        
        return CleanupResponse(
            success=True,
            message=f"Cleaned up {total_cleaned} old items ({cleaned_runs} runs, {cleaned_reports} reports)",
            cleaned_runs=total_cleaned
        )
        
    except Exception as e:
        return CleanupResponse(
            success=False,
            message=f"Cleanup failed: {str(e)}",
            cleaned_runs=0
        )


class ReportListResponse(BaseModel):
    """Response for listing reports."""
    reports: List[Dict[str, any]]
    total_count: int


@router.get("/reports", response_model=ReportListResponse)
async def list_preflight_reports(
    tenant_id: UUID = Depends(get_tenant_id),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results")
) -> ReportListResponse:
    """List preflight reports for the tenant."""
    
    reports = await report_storage.list_reports(tenant_id=tenant_id, limit=limit)
    
    return ReportListResponse(
        reports=reports,
        total_count=len(reports)
    )


class ReportStatisticsResponse(BaseModel):
    """Response for report statistics."""
    total_reports: int
    average_simulation_duration_ms: float
    success_rate: float
    average_steps: float
    risk_level_distribution: Dict[str, int]


@router.get("/reports/statistics", response_model=ReportStatisticsResponse)
async def get_report_statistics() -> ReportStatisticsResponse:
    """Get statistics about preflight reports."""
    
    stats = await report_storage.get_report_statistics()
    
    return ReportStatisticsResponse(**stats)


@router.delete("/{run_id}/report", response_model=SimulationResponse)
async def delete_preflight_report(
    run_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    service: GhostRunService = Depends(get_ghostrun_service)
) -> SimulationResponse:
    """Delete a preflight report."""
    
    # Check if run exists and user has access
    status = await service.get_simulation_status(run_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    
    if status.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to simulation run")
    
    # Delete the report
    deleted = await report_storage.delete_report(run_id)
    
    if deleted:
        return SimulationResponse(
            success=True,
            message="Preflight report deleted successfully",
            run_id=run_id
        )
    else:
        return SimulationResponse(
            success=False,
            message="Report not found or could not be deleted",
            run_id=run_id
        )