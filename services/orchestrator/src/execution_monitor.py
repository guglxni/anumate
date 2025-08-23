"""Execution monitoring and progress tracking for orchestrator service."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

try:
    from anumate_infrastructure.event_bus import EventBus
    from anumate_infrastructure import RedisManager
except ImportError:
    # Fallback for development/testing
    EventBus = None
    RedisManager = None

from .models import (
    ExecutionStatusEnum,
    ExecutionMetrics,
    PortiaPlanRun,
    ExecutionStatusModel,
)
from .portia_client import PortiaClient

logger = logging.getLogger(__name__)


class ExecutionMonitorError(Exception):
    """Execution monitor error."""
    pass


class ExecutionMonitor:
    """Monitors execution progress and handles completion events."""
    
    def __init__(
        self,
        redis_manager: Optional[Any] = None,
        event_bus: Optional[Any] = None,
    ):
        """Initialize execution monitor.
        
        Args:
            redis_manager: Redis manager for progress tracking
            event_bus: Event bus for completion events
        """
        self.redis_manager = redis_manager
        self.event_bus = event_bus
        
        # Active monitoring tasks
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._monitored_executions: Set[str] = set()
        
        # Progress tracking
        self._execution_metrics: Dict[str, ExecutionMetrics] = {}
    
    async def start_monitoring(
        self,
        run_id: str,
        tenant_id: UUID,
        plan_hash: str,
        triggered_by: UUID,
    ) -> None:
        """Start monitoring an execution.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            plan_hash: Plan hash
            triggered_by: User who triggered execution
        """
        if run_id in self._monitored_executions:
            logger.warning(f"Execution {run_id} is already being monitored")
            return
        
        # Initialize metrics
        self._execution_metrics[run_id] = ExecutionMetrics(
            run_id=run_id,
            tenant_id=tenant_id,
        )
        
        # Start monitoring task
        task = asyncio.create_task(
            self._monitor_execution_progress(
                run_id=run_id,
                tenant_id=tenant_id,
                plan_hash=plan_hash,
                triggered_by=triggered_by,
            )
        )
        
        self._monitoring_tasks[run_id] = task
        self._monitored_executions.add(run_id)
        
        logger.info(f"Started monitoring execution {run_id} for tenant {tenant_id}")
    
    async def stop_monitoring(self, run_id: str) -> None:
        """Stop monitoring an execution.
        
        Args:
            run_id: Portia run ID
        """
        if run_id not in self._monitored_executions:
            return
        
        # Cancel monitoring task
        if run_id in self._monitoring_tasks:
            task = self._monitoring_tasks[run_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self._monitoring_tasks[run_id]
        
        # Clean up
        self._monitored_executions.discard(run_id)
        if run_id in self._execution_metrics:
            del self._execution_metrics[run_id]
        
        logger.info(f"Stopped monitoring execution {run_id}")
    
    async def get_execution_metrics(self, run_id: str) -> Optional[ExecutionMetrics]:
        """Get execution metrics for a run.
        
        Args:
            run_id: Portia run ID
            
        Returns:
            Execution metrics or None if not found
        """
        return self._execution_metrics.get(run_id)
    
    async def update_progress(
        self,
        run_id: str,
        progress: float,
        current_step: Optional[str] = None,
        step_metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update execution progress.
        
        Args:
            run_id: Portia run ID
            progress: Progress percentage (0.0 to 1.0)
            current_step: Current executing step
            step_metrics: Step-specific metrics
        """
        if run_id not in self._execution_metrics:
            logger.warning(f"No metrics found for execution {run_id}")
            return
        
        metrics = self._execution_metrics[run_id]
        
        # Update progress
        if current_step and current_step != metrics.current_step:
            # Step changed, record step completion
            if metrics.current_step:
                step_duration = (datetime.now(timezone.utc) - metrics.step_start_time).total_seconds()
                metrics.step_durations[metrics.current_step] = step_duration
                metrics.steps_completed += 1
            
            metrics.current_step = current_step
            metrics.step_start_time = datetime.now(timezone.utc)
        
        metrics.progress = progress
        
        # Update step metrics if provided
        if step_metrics:
            metrics.step_metrics.update(step_metrics)
        
        # Store progress in Redis for persistence
        if self.redis_manager:
            await self._store_progress_in_redis(run_id, metrics)
    
    async def _monitor_execution_progress(
        self,
        run_id: str,
        tenant_id: UUID,
        plan_hash: str,
        triggered_by: UUID,
    ) -> None:
        """Monitor execution progress until completion.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            plan_hash: Plan hash
            triggered_by: User who triggered execution
        """
        try:
            start_time = datetime.now(timezone.utc)
            last_status = None
            
            while True:
                try:
                    # Get current execution status
                    async with PortiaClient() as portia_client:
                        portia_run = await portia_client.get_run(run_id)
                    
                    if not portia_run:
                        logger.error(f"Execution {run_id} not found in Portia")
                        break
                    
                    # Update metrics
                    await self._update_execution_metrics(run_id, portia_run, start_time)
                    
                    # Check if status changed
                    if portia_run.status != last_status:
                        await self._handle_status_change(
                            run_id=run_id,
                            tenant_id=tenant_id,
                            plan_hash=plan_hash,
                            triggered_by=triggered_by,
                            old_status=last_status,
                            new_status=portia_run.status,
                            portia_run=portia_run,
                        )
                        last_status = portia_run.status
                    
                    # Check if execution is complete
                    if portia_run.status in [
                        ExecutionStatusEnum.COMPLETED,
                        ExecutionStatusEnum.FAILED,
                        ExecutionStatusEnum.CANCELLED,
                    ]:
                        await self._handle_execution_completion(
                            run_id=run_id,
                            tenant_id=tenant_id,
                            plan_hash=plan_hash,
                            triggered_by=triggered_by,
                            portia_run=portia_run,
                        )
                        break
                    
                    # Wait before next check
                    await asyncio.sleep(5.0)  # Check every 5 seconds
                    
                except asyncio.CancelledError:
                    logger.info(f"Monitoring cancelled for execution {run_id}")
                    break
                except Exception as e:
                    logger.error(f"Error monitoring execution {run_id}: {e}")
                    await asyncio.sleep(10.0)  # Wait longer on error
                    
        except Exception as e:
            logger.error(f"Fatal error monitoring execution {run_id}: {e}")
        finally:
            # Clean up monitoring
            await self.stop_monitoring(run_id)
    
    async def _update_execution_metrics(
        self,
        run_id: str,
        portia_run: PortiaPlanRun,
        start_time: datetime,
    ) -> None:
        """Update execution metrics from Portia run data.
        
        Args:
            run_id: Portia run ID
            portia_run: Portia run data
            start_time: Execution start time
        """
        if run_id not in self._execution_metrics:
            return
        
        metrics = self._execution_metrics[run_id]
        
        # Update basic metrics
        metrics.progress = portia_run.progress
        metrics.current_step = portia_run.current_step
        metrics.status = portia_run.status
        
        # Calculate duration
        if portia_run.completed_at:
            metrics.total_duration = (portia_run.completed_at - start_time).total_seconds()
        else:
            metrics.total_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        # Update error information
        if portia_run.error_message:
            metrics.error_message = portia_run.error_message
            metrics.steps_failed += 1
        
        metrics.recorded_at = datetime.now(timezone.utc)
    
    async def _handle_status_change(
        self,
        run_id: str,
        tenant_id: UUID,
        plan_hash: str,
        triggered_by: UUID,
        old_status: Optional[ExecutionStatusEnum],
        new_status: ExecutionStatusEnum,
        portia_run: PortiaPlanRun,
    ) -> None:
        """Handle execution status changes.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            plan_hash: Plan hash
            triggered_by: User who triggered execution
            old_status: Previous status
            new_status: New status
            portia_run: Portia run data
        """
        logger.info(f"Execution {run_id} status changed: {old_status} -> {new_status}")
        
        # Publish status change event
        if self.event_bus:
            await self.event_bus.publish(
                subject="execution.status_changed",
                event_type="execution.status_changed",
                source="anumate.orchestrator",
                data={
                    "run_id": run_id,
                    "tenant_id": str(tenant_id),
                    "plan_hash": plan_hash,
                    "triggered_by": str(triggered_by),
                    "old_status": old_status.value if old_status else None,
                    "new_status": new_status.value,
                    "progress": portia_run.progress,
                    "current_step": portia_run.current_step,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        
        # Handle specific status changes
        if new_status == ExecutionStatusEnum.RUNNING and old_status == ExecutionStatusEnum.PENDING:
            await self._handle_execution_started(run_id, tenant_id, plan_hash, triggered_by)
        elif new_status == ExecutionStatusEnum.PAUSED:
            await self._handle_execution_paused(run_id, tenant_id)
        elif new_status == ExecutionStatusEnum.RUNNING and old_status == ExecutionStatusEnum.PAUSED:
            await self._handle_execution_resumed(run_id, tenant_id)
    
    async def _handle_execution_started(
        self,
        run_id: str,
        tenant_id: UUID,
        plan_hash: str,
        triggered_by: UUID,
    ) -> None:
        """Handle execution started event.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            plan_hash: Plan hash
            triggered_by: User who triggered execution
        """
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
                },
            )
    
    async def _handle_execution_paused(self, run_id: str, tenant_id: UUID) -> None:
        """Handle execution paused event.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
        """
        if self.event_bus:
            await self.event_bus.publish(
                subject="execution.paused",
                event_type="execution.paused",
                source="anumate.orchestrator",
                data={
                    "run_id": run_id,
                    "paused_at": datetime.now(timezone.utc).isoformat(),
                },
            )
    
    async def _handle_execution_resumed(self, run_id: str, tenant_id: UUID) -> None:
        """Handle execution resumed event.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
        """
        if self.event_bus:
            await self.event_bus.publish(
                subject="execution.resumed",
                event_type="execution.resumed",
                source="anumate.orchestrator",
                data={
                    "run_id": run_id,
                    "resumed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
    
    async def _handle_execution_completion(
        self,
        run_id: str,
        tenant_id: UUID,
        plan_hash: str,
        triggered_by: UUID,
        portia_run: PortiaPlanRun,
    ) -> None:
        """Handle execution completion.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            plan_hash: Plan hash
            triggered_by: User who triggered execution
            portia_run: Portia run data
        """
        logger.info(f"Execution {run_id} completed with status: {portia_run.status}")
        
        # Get final metrics
        metrics = self._execution_metrics.get(run_id)
        
        # Publish execution.completed CloudEvent
        if self.event_publisher:
            await self._publish_execution_completed_event(
                run_id=run_id,
                tenant_id=tenant_id,
                plan_hash=plan_hash,
                triggered_by=triggered_by,
                portia_run=portia_run,
                metrics=metrics,
            )
        
        # Handle failure-specific actions
        if portia_run.status == ExecutionStatusEnum.FAILED:
            await self._handle_execution_failure(
                run_id=run_id,
                tenant_id=tenant_id,
                portia_run=portia_run,
                metrics=metrics,
            )
    
    async def _publish_execution_completed_event(
        self,
        run_id: str,
        tenant_id: UUID,
        plan_hash: str,
        triggered_by: UUID,
        portia_run: PortiaPlanRun,
        metrics: Optional[ExecutionMetrics],
    ) -> None:
        """Publish execution.completed CloudEvent.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            plan_hash: Plan hash
            triggered_by: User who triggered execution
            portia_run: Portia run data
            metrics: Execution metrics
        """
        event_data = {
            "run_id": run_id,
            "tenant_id": str(tenant_id),
            "plan_hash": plan_hash,
            "triggered_by": str(triggered_by),
            "status": portia_run.status.value,
            "started_at": portia_run.started_at.isoformat() if portia_run.started_at else None,
            "completed_at": portia_run.completed_at.isoformat() if portia_run.completed_at else None,
            "success": portia_run.status == ExecutionStatusEnum.COMPLETED,
            "error_message": portia_run.error_message,
            "results": portia_run.results,
        }
        
        # Add metrics if available
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
            data=event_data,
        )
    
    async def _handle_execution_failure(
        self,
        run_id: str,
        tenant_id: UUID,
        portia_run: PortiaPlanRun,
        metrics: Optional[ExecutionMetrics],
    ) -> None:
        """Handle execution failure and rollback if needed.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            portia_run: Portia run data
            metrics: Execution metrics
        """
        logger.error(f"Execution {run_id} failed: {portia_run.error_message}")
        
        # Publish failure event
        if self.event_bus:
            await self.event_bus.publish(
                subject="execution.failed",
                event_type="execution.failed",
                source="anumate.orchestrator",
                data={
                    "run_id": run_id,
                    "tenant_id": str(tenant_id),
                    "error_message": portia_run.error_message,
                    "error_details": portia_run.error_details,
                    "failed_at": portia_run.completed_at.isoformat() if portia_run.completed_at else None,
                    "steps_completed": metrics.steps_completed if metrics else 0,
                    "steps_failed": metrics.steps_failed if metrics else 1,
                },
            )
        
        # TODO: Implement rollback logic based on plan configuration
        # This would involve:
        # 1. Checking if rollback is enabled in the plan
        # 2. Executing rollback steps in reverse order
        # 3. Cleaning up any partial state changes
        # 4. Notifying relevant parties of the rollback
        
        await self._attempt_rollback(run_id, tenant_id, portia_run)
    
    async def _attempt_rollback(
        self,
        run_id: str,
        tenant_id: UUID,
        portia_run: PortiaPlanRun,
    ) -> None:
        """Attempt to rollback failed execution.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            portia_run: Portia run data
        """
        # For now, just log the rollback attempt
        # In a full implementation, this would:
        # 1. Analyze completed steps for rollback actions
        # 2. Execute compensating transactions
        # 3. Restore previous state where possible
        # 4. Generate rollback report
        
        logger.info(f"Attempting rollback for failed execution {run_id}")
        
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
                },
            )
    
    async def _store_progress_in_redis(
        self,
        run_id: str,
        metrics: ExecutionMetrics,
    ) -> None:
        """Store execution progress in Redis.
        
        Args:
            run_id: Portia run ID
            metrics: Execution metrics
        """
        if not self.redis_manager:
            return
        
        try:
            key = f"execution:progress:{run_id}"
            data = metrics.model_dump(mode='json')
            
            # Store with 24 hour expiry
            await self.redis_manager.setex(key, 86400, data)
            
        except Exception as e:
            logger.error(f"Failed to store progress in Redis for {run_id}: {e}")