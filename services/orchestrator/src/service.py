"""Main orchestrator service for ExecutablePlan execution."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

try:
    from anumate_infrastructure.event_bus import EventBus
    from anumate_infrastructure import RedisManager
except ImportError:
    # Fallback for development/testing
    EventBus = None
    RedisManager = None

from .capability_validator import CapabilityValidator
from .clarifications_bridge import ClarificationsBridge
try:
    from .execution_monitor import ExecutionMonitor
except ImportError:
    from .execution_monitor_standalone import ExecutionMonitor
from .models import (
    ExecutionRequest,
    ExecutionResponse,
    ExecutionStatusModel,
    ExecutionHook,
    PortiaPlanRun,
    ExecutionMetrics,
    CapabilityValidation,
)
from .plan_transformer import PlanTransformer
from .portia_client import PortiaClient, PortiaClientError
from .retry_handler import RetryHandler

logger = logging.getLogger(__name__)


class OrchestratorServiceError(Exception):
    """Orchestrator service error."""
    pass


class OrchestratorService:
    """Main orchestrator service for plan execution."""
    
    def __init__(
        self,
        redis_manager: Optional[Any] = None,
        event_bus: Optional[Any] = None,
    ):
        """Initialize orchestrator service.
        
        Args:
            redis_manager: Redis manager for caching and idempotency
            event_bus: Event bus for notifications
        """
        self.redis_manager = redis_manager
        self.event_bus = event_bus
        
        # Initialize components
        self.plan_transformer = PlanTransformer()
        self.capability_validator = CapabilityValidator()
        self.clarifications_bridge = ClarificationsBridge(event_bus=event_bus)
        self.retry_handler = RetryHandler(redis_manager=redis_manager)
        self.execution_monitor = ExecutionMonitor(
            redis_manager=redis_manager,
            event_bus=event_bus,
        )
        
        # Execution tracking
        self._active_executions: Dict[str, PortiaPlanRun] = {}
    
    async def execute_plan(
        self,
        request: ExecutionRequest,
        executable_plan: Dict[str, Any],
    ) -> ExecutionResponse:
        """Execute an ExecutablePlan via Portia Runtime.
        
        Args:
            request: Execution request
            executable_plan: ExecutablePlan data
            
        Returns:
            Execution response
            
        Raises:
            OrchestratorServiceError: If execution fails
        """
        try:
            # Check idempotency if enabled
            if not request.dry_run:
                idempotency_key = await self.retry_handler.generate_idempotency_key(
                    tenant_id=request.tenant_id,
                    request_data=request.model_dump(),
                )
                
                cached_response = await self.retry_handler.check_idempotency(idempotency_key)
                if cached_response:
                    logger.info(f"Returning cached response for tenant {request.tenant_id}")
                    return ExecutionResponse(**cached_response)
            
            # PRE-EXECUTION CAPABILITY TOKEN VALIDATION
            if request.validate_capabilities:
                validation_result = await self._validate_execution_capabilities_with_tokens(
                    request, executable_plan
                )
                if not validation_result.valid:
                    raise OrchestratorServiceError(
                        f"Pre-execution capability validation failed: {validation_result.error_message}"
                    )
                
                # Track capabilities that will be used
                logger.info(f"Validated capabilities for execution: {validation_result.capabilities}")
            
            # Execute pre-execution hooks
            await self._execute_hooks(request.hooks, "pre_execution", {
                "request": request.model_dump(),
                "plan": executable_plan,
            })
            
            # Transform ExecutablePlan to Portia format
            portia_plan = self.plan_transformer.transform_executable_plan(
                executable_plan=executable_plan,
                tenant_id=request.tenant_id,
                triggered_by=str(request.triggered_by),
            )
            
            # Execute plan via Portia
            response = await self._execute_via_portia(
                request=request,
                portia_plan=portia_plan,
            )
            
            # START EXECUTION MONITORING
            if response.success and response.run_id:
                await self.execution_monitor.start_monitoring(
                    run_id=response.run_id,
                    tenant_id=request.tenant_id,
                    plan_hash=request.plan_hash,
                    triggered_by=request.triggered_by,
                )
                logger.info(f"Started monitoring execution {response.run_id}")
            
            # Store idempotency result if successful
            if not request.dry_run and response.success:
                await self.retry_handler.store_idempotency_result(
                    idempotency_key=idempotency_key,
                    result=response.model_dump(),
                )
            
            # Execute post-execution hooks
            await self._execute_hooks(request.hooks, "post_execution", {
                "request": request.model_dump(),
                "response": response.model_dump(),
            })
            
            return response
            
        except Exception as e:
            error_msg = f"Plan execution failed: {e}"
            logger.error(error_msg)
            
            # Create error response
            error_response = ExecutionResponse(
                success=False,
                error_message=error_msg,
                error_code="EXECUTION_FAILED",
                correlation_id=request.correlation_id,
            )
            
            # Execute error hooks
            await self._execute_hooks(request.hooks, "on_error", {
                "request": request.model_dump(),
                "error": error_msg,
            })
            
            return error_response  
  
    async def get_execution_status(
        self,
        run_id: str,
        tenant_id: UUID,
    ) -> Optional[ExecutionStatusModel]:
        """Get execution status for a run.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            
        Returns:
            Execution status or None if not found
        """
        try:
            async with PortiaClient() as portia_client:
                # Get run status from Portia
                portia_run = await portia_client.get_run(run_id)
                
                if not portia_run:
                    return None
                
                # Get any pending clarifications
                clarifications = await portia_client.get_clarifications(run_id)
                
                # Get execution metrics from monitor
                metrics = await self.execution_monitor.get_execution_metrics(run_id)
                
                # Convert to ExecutionStatusModel
                status_model = ExecutionStatusModel(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    status=portia_run.status,
                    progress=portia_run.progress,
                    current_step=portia_run.current_step,
                    started_at=portia_run.started_at,
                    completed_at=portia_run.completed_at,
                    results=portia_run.results,
                    error_message=portia_run.error_message,
                    pending_clarifications=clarifications,
                )
                
                # Add metrics if available
                if metrics:
                    status_model.estimated_completion = self._calculate_estimated_completion(
                        metrics, portia_run
                    )
                
                return status_model
                
        except Exception as e:
            logger.error(f"Failed to get execution status for {run_id}: {e}")
            return None
    
    async def pause_execution(self, run_id: str, tenant_id: UUID) -> bool:
        """Pause a running execution.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            
        Returns:
            True if paused successfully
        """
        try:
            async with PortiaClient() as portia_client:
                success = await portia_client.pause_run(run_id)
                
                if success and self.event_bus:
                    await self.event_bus.publish(
                        subject="execution.paused",
                        event_type="execution.paused",
                        source="anumate.orchestrator",
                        data={"run_id": run_id},
                    )
                
                return success
                
        except Exception as e:
            logger.error(f"Failed to pause execution {run_id}: {e}")
            return False
    
    async def resume_execution(self, run_id: str, tenant_id: UUID) -> bool:
        """Resume a paused execution.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            
        Returns:
            True if resumed successfully
        """
        try:
            async with PortiaClient() as portia_client:
                success = await portia_client.resume_run(run_id)
                
                if success and self.event_bus:
                    await self.event_bus.publish(
                        subject="execution.resumed",
                        event_type="execution.resumed",
                        source="anumate.orchestrator",
                        data={"run_id": run_id},
                    )
                
                return success
                
        except Exception as e:
            logger.error(f"Failed to resume execution {run_id}: {e}")
            return False
    
    async def cancel_execution(self, run_id: str, tenant_id: UUID) -> bool:
        """Cancel a running execution.
        
        Args:
            run_id: Portia run ID
            tenant_id: Tenant ID
            
        Returns:
            True if cancelled successfully
        """
        try:
            async with PortiaClient() as portia_client:
                success = await portia_client.cancel_run(run_id)
                
                if success:
                    # Stop monitoring the cancelled execution
                    await self.execution_monitor.stop_monitoring(run_id)
                    
                    if self.event_bus:
                        await self.event_bus.publish(
                            subject="execution.cancelled",
                            event_type="execution.cancelled",
                            source="anumate.orchestrator",
                            data={"run_id": run_id},
                        )
                
                return success
                
        except Exception as e:
            logger.error(f"Failed to cancel execution {run_id}: {e}")
            return False
    
    async def get_execution_metrics(self, run_id: str) -> Optional[ExecutionMetrics]:
        """Get execution metrics for a run.
        
        Args:
            run_id: Portia run ID
            
        Returns:
            Execution metrics or None if not found
        """
        return await self.execution_monitor.get_execution_metrics(run_id)
    
    async def _validate_execution_capabilities(
        self,
        request: ExecutionRequest,
        executable_plan: Dict[str, Any],
    ) -> None:
        """Validate capabilities for execution.
        
        Args:
            request: Execution request
            executable_plan: ExecutablePlan data
            
        Raises:
            OrchestratorServiceError: If validation fails
        """
        # Extract required capabilities from security context
        security_context = executable_plan.get('security_context', {})
        required_capabilities = security_context.get('required_capabilities', [])
        allowed_tools = security_context.get('allowed_tools', [])
        
        if required_capabilities:
            validation = await self.capability_validator.validate_execution_capabilities(
                tenant_id=request.tenant_id,
                required_capabilities=required_capabilities,
                user_id=request.triggered_by,
            )
            
            if not validation.valid:
                raise OrchestratorServiceError(
                    f"Capability validation failed: {validation.error_message}"
                )
        
        # Validate tool allowlist for each step
        flows = executable_plan.get('flows', [])
        for flow in flows:
            for step in flow.get('steps', []):
                tool = step.get('tool')
                if tool and allowed_tools:
                    is_allowed = await self.capability_validator.validate_tool_allowlist(
                        tenant_id=request.tenant_id,
                        allowed_tools=allowed_tools,
                        requested_tool=tool,
                    )
                    
                    if not is_allowed:
                        raise OrchestratorServiceError(
                            f"Tool '{tool}' not allowed for tenant {request.tenant_id}"
                        )
    
    async def _execute_via_portia(
        self,
        request: ExecutionRequest,
        portia_plan: Any,
    ) -> ExecutionResponse:
        """Execute plan via Portia Runtime.
        
        Args:
            request: Execution request
            portia_plan: Portia plan
            
        Returns:
            Execution response
        """
        async with PortiaClient() as portia_client:
            # Create plan in Portia
            created_plan = await portia_client.create_plan(portia_plan)
            
            # Create and start execution
            portia_run = await portia_client.create_run(
                plan_id=created_plan.plan_id,
                parameters=request.parameters,
                variables=request.variables,
                triggered_by=str(request.triggered_by),
            )
            
            # Track active execution
            self._active_executions[portia_run.run_id] = portia_run
            
            return ExecutionResponse(
                success=True,
                run_id=portia_run.run_id,
                status=portia_run.status,
                correlation_id=request.correlation_id,
            )
    
    async def _execute_hooks(
        self,
        hooks: List[ExecutionHook],
        hook_type: str,
        context: Dict[str, Any],
    ) -> None:
        """Execute hooks of specified type.
        
        Args:
            hooks: List of execution hooks
            hook_type: Type of hook to execute
            context: Hook execution context
        """
        for hook in hooks:
            if hook.hook_type == hook_type and hook.enabled:
                try:
                    await self._execute_single_hook(hook, context)
                except Exception as e:
                    logger.error(f"Hook execution failed for {hook.hook_type}: {e}")
    
    async def _execute_single_hook(
        self,
        hook: ExecutionHook,
        context: Dict[str, Any],
    ) -> None:
        """Execute a single hook.
        
        Args:
            hook: Execution hook
            context: Hook execution context
        """
        # For now, implement basic hook types
        if hook.hook_type == "pre_execution":
            logger.info("Executing pre-execution hook")
            # Add capability validation, logging, etc.
            
        elif hook.hook_type == "post_execution":
            logger.info("Executing post-execution hook")
            # Add result processing, notifications, etc.
            
        elif hook.hook_type == "on_error":
            logger.info("Executing error hook")
            # Add error handling, cleanup, etc.
            
        else:
            logger.warning(f"Unknown hook type: {hook.hook_type}")
    
    async def _validate_execution_capabilities_with_tokens(
        self,
        request: ExecutionRequest,
        executable_plan: Dict[str, Any],
    ) -> CapabilityValidation:
        """Enhanced capability validation with token verification.
        
        Args:
            request: Execution request
            executable_plan: ExecutablePlan data
            
        Returns:
            Capability validation result
            
        Raises:
            OrchestratorServiceError: If validation fails
        """
        # Extract required capabilities from security context
        security_context = executable_plan.get('security_context', {})
        required_capabilities = security_context.get('required_capabilities', [])
        allowed_tools = security_context.get('allowed_tools', [])
        
        if not required_capabilities:
            return CapabilityValidation(valid=True, capabilities=[])
        
        # Validate capabilities with token
        validation = await self.capability_validator.validate_execution_capabilities(
            tenant_id=request.tenant_id,
            required_capabilities=required_capabilities,
            user_id=request.triggered_by,
        )
        
        if not validation.valid:
            return validation
        
        # Check token expiry
        if await self.capability_validator.check_capability_expiry(validation):
            return CapabilityValidation(
                valid=False,
                error_message="Capability token is expired or close to expiry"
            )
        
        # Validate tool allowlist for each step
        flows = executable_plan.get('flows', [])
        for flow in flows:
            for step in flow.get('steps', []):
                tool = step.get('tool')
                if tool and allowed_tools:
                    is_allowed = await self.capability_validator.validate_tool_allowlist(
                        tenant_id=request.tenant_id,
                        allowed_tools=allowed_tools,
                        requested_tool=tool,
                    )
                    
                    if not is_allowed:
                        return CapabilityValidation(
                            valid=False,
                            error_message=f"Tool '{tool}' not allowed for tenant {request.tenant_id}"
                        )
        
        return validation
    
    def _calculate_estimated_completion(
        self,
        metrics: ExecutionMetrics,
        portia_run: PortiaPlanRun,
    ) -> Optional[datetime]:
        """Calculate estimated completion time based on progress.
        
        Args:
            metrics: Execution metrics
            portia_run: Portia run data
            
        Returns:
            Estimated completion time or None
        """
        if not portia_run.started_at or portia_run.progress <= 0:
            return None
        
        # Calculate elapsed time
        now = datetime.now(timezone.utc)
        elapsed = (now - portia_run.started_at).total_seconds()
        
        # Estimate total time based on progress
        if portia_run.progress > 0:
            estimated_total = elapsed / portia_run.progress
            remaining = estimated_total - elapsed
            
            if remaining > 0:
                return now + timedelta(seconds=remaining)
        
        return None