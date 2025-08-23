"""Main GhostRun service implementation."""

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID, uuid4

from .models import (
    GhostRunRequest,
    GhostRunStatus,
    PreflightReport,
    SimulationMetrics,
    SimulationStatus,
    ExecutablePlan,
)
from .simulation_engine import SimulationEngine
from .event_publisher import event_publisher
from .report_storage import report_storage


class GhostRunService:
    """Main service for managing GhostRun simulations."""
    
    def __init__(self) -> None:
        self.simulation_engine = SimulationEngine()
        self.active_runs: Dict[UUID, GhostRunStatus] = {}
        self.completed_runs: Dict[UUID, GhostRunStatus] = {}
        
    async def start_simulation(
        self, 
        tenant_id: UUID,
        plan: ExecutablePlan, 
        request: GhostRunRequest
    ) -> GhostRunStatus:
        """Start a new GhostRun simulation."""
        
        run_id = uuid4()
        
        # Create initial status
        status = GhostRunStatus(
            run_id=run_id,
            tenant_id=tenant_id,
            plan_hash=plan.plan_hash,
            status=SimulationStatus.PENDING,
            progress=0.0,
            created_at=datetime.now(timezone.utc)
        )
        
        # Store in active runs
        self.active_runs[run_id] = status
        
        # Publish simulation started event
        await event_publisher.publish_simulation_started(status)
        
        # Start simulation in background
        asyncio.create_task(self._run_simulation(run_id, plan, request))
        
        return status
    
    async def get_simulation_status(self, run_id: UUID) -> Optional[GhostRunStatus]:
        """Get status of a simulation run."""
        
        # Check active runs first
        if run_id in self.active_runs:
            return self.active_runs[run_id]
        
        # Check completed runs
        if run_id in self.completed_runs:
            return self.completed_runs[run_id]
        
        return None
    
    async def cancel_simulation(self, run_id: UUID) -> bool:
        """Cancel a running simulation."""
        
        if run_id not in self.active_runs:
            return False
        
        status = self.active_runs[run_id]
        
        if status.status in [SimulationStatus.PENDING, SimulationStatus.RUNNING]:
            status.status = SimulationStatus.CANCELLED
            status.completed_at = status.created_at  # Use created_at as placeholder
            
            # Move to completed runs
            self.completed_runs[run_id] = status
            del self.active_runs[run_id]
            
            return True
        
        return False
    
    async def get_preflight_report(self, run_id: UUID) -> Optional[PreflightReport]:
        """Get preflight report for a completed simulation."""
        
        # First try to get from storage
        report = await report_storage.get_report(run_id)
        if report:
            return report
        
        # Fallback to in-memory status
        status = await self.get_simulation_status(run_id)
        if status and status.status == SimulationStatus.COMPLETED:
            return status.report
        
        return None
    
    async def list_simulations(
        self, 
        tenant_id: UUID, 
        status_filter: Optional[SimulationStatus] = None
    ) -> list[GhostRunStatus]:
        """List simulations for a tenant."""
        
        all_runs = list(self.active_runs.values()) + list(self.completed_runs.values())
        
        # Filter by tenant
        tenant_runs = [run for run in all_runs if run.tenant_id == tenant_id]
        
        # Filter by status if specified
        if status_filter:
            tenant_runs = [run for run in tenant_runs if run.status == status_filter]
        
        # Sort by creation time (newest first)
        tenant_runs.sort(key=lambda x: x.created_at, reverse=True)
        
        return tenant_runs
    
    async def _run_simulation(
        self, 
        run_id: UUID, 
        plan: ExecutablePlan, 
        request: GhostRunRequest
    ) -> None:
        """Execute the simulation in the background."""
        
        status = self.active_runs[run_id]
        
        try:
            # Update status to running
            status.status = SimulationStatus.RUNNING
            status.started_at = datetime.now(timezone.utc)
            status.current_step = "Initializing simulation"
            status.progress = 0.1
            
            # Run the simulation
            await self._execute_simulation_phases(status, plan, request)
            
            # Mark as completed
            status.status = SimulationStatus.COMPLETED
            status.completed_at = datetime.now(timezone.utc)
            status.progress = 1.0
            status.current_step = None
            
            # Store report and publish completion event
            if status.report:
                await report_storage.store_report(run_id, status.report)
                await event_publisher.publish_preflight_completed(status, status.report)
            
        except Exception as e:
            # Handle simulation errors
            status.status = SimulationStatus.FAILED
            status.completed_at = datetime.now(timezone.utc)
            status.error_message = str(e)
            status.progress = 0.0
            status.current_step = None
            
            # Publish failure event
            await event_publisher.publish_simulation_failed(status)
        
        finally:
            # Move to completed runs
            if run_id in self.active_runs:
                self.completed_runs[run_id] = self.active_runs[run_id]
                del self.active_runs[run_id]
    
    async def _execute_simulation_phases(
        self, 
        status: GhostRunStatus, 
        plan: ExecutablePlan, 
        request: GhostRunRequest
    ) -> None:
        """Execute simulation phases with progress updates."""
        
        # Phase 1: Plan validation
        status.current_step = "Validating plan structure"
        status.progress = 0.2
        await asyncio.sleep(0.1)  # Simulate work
        
        # Phase 2: Dependency analysis
        status.current_step = "Analyzing dependencies"
        status.progress = 0.3
        await asyncio.sleep(0.1)
        
        # Phase 3: Risk assessment
        status.current_step = "Assessing risks"
        status.progress = 0.4
        await asyncio.sleep(0.1)
        
        # Phase 4: Connector simulation
        status.current_step = "Simulating connector calls"
        status.progress = 0.6
        await asyncio.sleep(0.2)
        
        # Phase 5: Performance analysis
        status.current_step = "Analyzing performance"
        status.progress = 0.8
        await asyncio.sleep(0.1)
        
        # Phase 6: Report generation
        status.current_step = "Generating preflight report"
        status.progress = 0.9
        
        # Run actual simulation
        report, metrics = await self.simulation_engine.simulate_plan(plan, request)
        
        # Store results
        status.report = report
        status.simulation_metrics = {
            "total_duration_ms": metrics.total_duration_ms,
            "steps_simulated": metrics.steps_simulated,
            "connectors_mocked": metrics.connectors_mocked,
            "api_calls_simulated": metrics.api_calls_simulated,
            "simulation_efficiency": metrics.simulation_efficiency
        }
    
    async def cleanup_old_runs(self, max_age_hours: int = 24) -> int:
        """Clean up old completed simulation runs."""
        
        current_time = time.time()
        cutoff_time = current_time - (max_age_hours * 3600)
        
        # Find old runs to remove
        old_run_ids = []
        for run_id, status in self.completed_runs.items():
            # Convert datetime to timestamp for comparison
            run_time = status.created_at.timestamp()
            if run_time < cutoff_time:
                old_run_ids.append(run_id)
        
        # Remove old runs
        for run_id in old_run_ids:
            del self.completed_runs[run_id]
        
        return len(old_run_ids)
    
    async def get_simulation_metrics(self) -> Dict[str, any]:
        """Get overall simulation service metrics."""
        
        total_runs = len(self.active_runs) + len(self.completed_runs)
        active_count = len(self.active_runs)
        completed_count = len(self.completed_runs)
        
        # Calculate success rate
        successful_runs = sum(
            1 for status in self.completed_runs.values()
            if status.status == SimulationStatus.COMPLETED
        )
        success_rate = successful_runs / max(1, completed_count)
        
        # Calculate average simulation time
        completed_with_times = [
            status for status in self.completed_runs.values()
            if status.started_at and status.completed_at
        ]
        
        if completed_with_times:
            total_duration = sum(
                (status.completed_at - status.started_at).total_seconds()
                for status in completed_with_times
            )
            avg_duration = total_duration / len(completed_with_times)
        else:
            avg_duration = 0.0
        
        return {
            "total_simulations": total_runs,
            "active_simulations": active_count,
            "completed_simulations": completed_count,
            "success_rate": success_rate,
            "average_duration_seconds": avg_duration,
            "service_uptime": time.time()  # Simplified uptime
        }


# Global service instance
ghostrun_service = GhostRunService()