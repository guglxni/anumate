"""Standalone execution monitor without external dependencies."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Set
from uuid import UUID

from models import ExecutionMetrics, ExecutionStatusEnum


class ExecutionMonitorError(Exception):
    """Execution monitor error."""
    pass


class ExecutionMonitor:
    """Standalone execution monitor for testing."""
    
    def __init__(self, redis_manager=None, event_bus=None):
        """Initialize execution monitor.
        
        Args:
            redis_manager: Redis manager instance (optional)
            event_bus: Event bus instance (optional)
        """
        self.redis_manager = redis_manager
        self.event_bus = event_bus
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._monitored_executions: Set[str] = set()
        self._execution_metrics: Dict[str, ExecutionMetrics] = {}
        self._polling_interval = 2.0  # seconds
    
    async def start_monitoring(
        self,
        run_id: str,
        tenant_id: UUID,
        plan_hash: str,
        triggered_by: UUID
    ) -> None:
        """Start monitoring an execution.
        
        Args:
            run_id: Execution run ID
            tenant_id: Tenant ID
            plan_hash: Plan hash
            triggered_by: User who triggered execution
        """
        if run_id in self._monitored_executions:
            return
        
        # Initialize metrics
        self._execution_metrics[run_id] = ExecutionMetrics(
            run_id=run_id,
            tenant_id=tenant_id
        )
        
        # Add to monitored set
        self._monitored_executions.add(run_id)
        
        # Start monitoring task
        task = asyncio.create_task(self._monitor_execution(run_id))
        self._monitoring_tasks[run_id] = task
        
        # Publish started event
        if self.event_bus:
            await self.event_bus.publish(
                subject="execution.started",
                event_type="execution.started",
                source="anumate.orchestrator",
                data={
                    "run_id": run_id,
                    "tenant_id": str(tenant_id),
                    "plan_hash": plan_hash,
                    "triggered_by": str(triggered_by),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    
    async def stop_monitoring(self, run_id: str) -> None:
        """Stop monitoring an execution.
        
        Args:
            run_id: Execution run ID
        """
        # Cancel monitoring task
        if run_id in self._monitoring_tasks:
            task = self._monitoring_tasks.pop(run_id)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Remove from monitored set
        self._monitored_executions.discard(run_id)
        
        # Clean up metrics
        if run_id in self._execution_metrics:
            del self._execution_metrics[run_id]
    
    async def get_execution_metrics(self, run_id: str) -> Optional[ExecutionMetrics]:
        """Get execution metrics.
        
        Args:
            run_id: Execution run ID
            
        Returns:
            Execution metrics or None if not found
        """
        return self._execution_metrics.get(run_id)
    
    async def update_progress(
        self,
        run_id: str,
        progress: float,
        current_step: Optional[str] = None,
        step_metrics: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update execution progress.
        
        Args:
            run_id: Execution run ID
            progress: Progress value (0.0 to 1.0)
            current_step: Current step name
            step_metrics: Step-specific metrics
        """
        if run_id not in self._execution_metrics:
            return
        
        metrics = self._execution_metrics[run_id]
        
        # Handle step change
        if current_step and current_step != metrics.current_step:
            if metrics.current_step:
                # Complete previous step
                step_duration = (datetime.now(timezone.utc) - metrics.step_start_time).total_seconds()
                metrics.step_durations[metrics.current_step] = step_duration
                metrics.steps_completed += 1
            
            # Start new step
            metrics.current_step = current_step
            metrics.step_start_time = datetime.now(timezone.utc)
        
        # Update progress
        metrics.progress = progress
        
        # Update step metrics
        if step_metrics:
            metrics.step_metrics.update(step_metrics)
        
        # Store in Redis if available
        if self.redis_manager:
            await self.redis_manager.setex(
                f"execution:progress:{run_id}",
                86400,  # 24 hours TTL
                metrics.model_dump()
            )
    
    async def _monitor_execution(self, run_id: str) -> None:
        """Monitor execution progress.
        
        Args:
            run_id: Execution run ID
        """
        try:
            while run_id in self._monitored_executions:
                # In a real implementation, this would poll Portia
                # For testing, we just sleep
                await asyncio.sleep(self._polling_interval)
                
                # Check if execution is still active
                if run_id not in self._monitored_executions:
                    break
        
        except asyncio.CancelledError:
            # Monitoring was cancelled
            pass
        except Exception as e:
            # Handle monitoring errors
            if self.event_bus:
                await self.event_bus.publish(
                    subject="execution.monitor_error",
                    event_type="execution.monitor_error", 
                    source="anumate.orchestrator",
                    data={
                        "run_id": run_id,
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
    
    async def handle_execution_completion(
        self,
        run_id: str,
        tenant_id: UUID,
        plan_hash: str,
        triggered_by: UUID,
        status: str,
        results: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Handle execution completion.
        
        Args:
            run_id: Execution run ID
            tenant_id: Tenant ID
            plan_hash: Plan hash
            triggered_by: User who triggered execution
            status: Final execution status
            results: Execution results
            error_message: Error message if failed
        """
        metrics = self._execution_metrics.get(run_id)
        
        # Publish completion event
        if self.event_bus:
            event_data = {
                "run_id": run_id,
                "tenant_id": str(tenant_id),
                "plan_hash": plan_hash,
                "triggered_by": str(triggered_by),
                "status": status,
                "success": status == ExecutionStatusEnum.COMPLETED,
                "error_message": error_message,
                "results": results or {},
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            
            if metrics:
                event_data.update({
                    "total_duration_seconds": metrics.total_duration,
                    "steps_completed": metrics.steps_completed,
                    "steps_failed": metrics.steps_failed,
                    "retry_count": metrics.retry_count,
                    "capabilities_used": metrics.capabilities_used,
                })
            
            await self.event_bus.publish(
                subject="execution.completed",
                event_type="execution.completed",
                source="anumate.orchestrator",
                data=event_data
            )
        
        # Handle failure
        if status == ExecutionStatusEnum.FAILED:
            await self.handle_execution_failure(run_id, tenant_id, error_message, metrics)
        
        # Stop monitoring
        await self.stop_monitoring(run_id)
    
    async def handle_execution_failure(
        self,
        run_id: str,
        tenant_id: UUID,
        error_message: Optional[str],
        metrics: Optional[ExecutionMetrics]
    ) -> None:
        """Handle execution failure.
        
        Args:
            run_id: Execution run ID
            tenant_id: Tenant ID
            error_message: Error message
            metrics: Execution metrics
        """
        # Publish failure event
        if self.event_bus:
            await self.event_bus.publish(
                subject="execution.failed",
                event_type="execution.failed",
                source="anumate.orchestrator",
                data={
                    "run_id": run_id,
                    "tenant_id": str(tenant_id),
                    "error_message": error_message,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "steps_completed": metrics.steps_completed if metrics else 0,
                    "steps_failed": metrics.steps_failed if metrics else 1,
                }
            )
        
        # Attempt rollback
        await self.attempt_rollback(run_id, tenant_id)
    
    async def attempt_rollback(self, run_id: str, tenant_id: UUID) -> None:
        """Attempt execution rollback.
        
        Args:
            run_id: Execution run ID
            tenant_id: Tenant ID
        """
        # Publish rollback event
        if self.event_bus:
            await self.event_bus.publish(
                subject="execution.rollback_attempted",
                event_type="execution.rollback_attempted",
                source="anumate.orchestrator",
                data={
                    "run_id": run_id,
                    "tenant_id": str(tenant_id),
                    "rollback_started_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        
        # In a real implementation, this would perform actual rollback operations
        # For now, we just log the attempt
        pass