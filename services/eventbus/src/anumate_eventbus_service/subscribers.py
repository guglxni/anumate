"""
CloudEvents Event Subscribers for Anumate Services  
==================================================

Provides standardized event subscription capabilities with automatic routing,
filtering, and dead letter handling for all Anumate microservices.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable, Set
from abc import ABC, abstractmethod

from .eventbus_core import CloudEvent, EventType, EventBusService, EventSubscription
from .publishers import EventContext

logger = logging.getLogger(__name__)


class EventHandler(ABC):
    """Abstract base class for event handlers."""
    
    @abstractmethod
    async def handle(self, event: CloudEvent) -> None:
        """Handle a CloudEvent."""
        pass
        
    @abstractmethod
    def get_supported_event_types(self) -> Set[str]:
        """Get the event types this handler supports."""
        pass


class BaseEventSubscriber:
    """Base class for service-specific event subscribers."""
    
    def __init__(self, service_name: str, event_bus: EventBusService):
        self.service_name = service_name
        self.event_bus = event_bus
        self.handlers: Dict[str, EventHandler] = {}
        self.subscriptions: List[str] = []
        
    def register_handler(self, handler: EventHandler):
        """Register an event handler."""
        for event_type in handler.get_supported_event_types():
            self.handlers[event_type] = handler
            logger.info(f"Registered handler for {event_type} in {self.service_name}")
            
    async def start(self):
        """Start subscribing to events."""
        if not self.handlers:
            logger.warning(f"No handlers registered for {self.service_name}")
            return
            
        # Group handlers by event types for efficient subscriptions
        event_types = set(self.handlers.keys())
        
        # Create subscription
        subscription = EventSubscription(
            event_types=event_types,
            queue_group=f"{self.service_name}_queue",
            durable_name=f"{self.service_name}_consumer",
            max_inflight=50,
            ack_wait=30,
            max_deliver=3
        )
        
        # Subscribe with router handler
        subscription_id = await self.event_bus.subscribe(
            subscription,
            self._route_event,
            consumer_name=f"{self.service_name}_subscriber"
        )
        
        self.subscriptions.append(subscription_id)
        logger.info(f"Started event subscriber for {self.service_name}")
        
    async def stop(self):
        """Stop all subscriptions."""
        for subscription_id in self.subscriptions:
            await self.event_bus.unsubscribe(subscription_id)
        self.subscriptions.clear()
        logger.info(f"Stopped event subscriber for {self.service_name}")
        
    async def _route_event(self, event: CloudEvent):
        """Route event to appropriate handler."""
        try:
            handler = self.handlers.get(event.type)
            if not handler:
                logger.warning(f"No handler found for event type {event.type} in {self.service_name}")
                return
                
            await handler.handle(event)
            logger.debug(f"Successfully handled {event.type} event {event.id}")
            
        except Exception as e:
            logger.error(f"Error handling event {event.id} in {self.service_name}: {e}")
            raise


# Registry Service Event Handlers

class CapsuleCreatedHandler(EventHandler):
    """Handler for capsule created events."""
    
    def __init__(self, registry_service):
        self.registry_service = registry_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.CAPSULE_CREATED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle capsule created event."""
        data = event.data
        logger.info(f"Processing capsule created: {data.get('name')} v{data.get('version')}")
        
        # Update registry indexes, notify watchers, etc.
        # await self.registry_service.index_capsule(data)


class PolicyViolationHandler(EventHandler):
    """Handler for policy violation events."""
    
    def __init__(self, registry_service):
        self.registry_service = registry_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.POLICY_VIOLATED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle policy violation event."""
        data = event.data
        logger.warning(f"Policy violation detected: {data.get('policy_name')}")
        
        # Mark capsule as non-compliant, send notifications, etc.
        # await self.registry_service.mark_policy_violation(data)


# Policy Service Event Handlers

class ExecutionStartedHandler(EventHandler):
    """Handler for execution started events."""
    
    def __init__(self, policy_service):
        self.policy_service = policy_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.EXECUTION_STARTED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle execution started event."""
        data = event.data
        execution_id = data.get('execution_id')
        plan_id = data.get('plan_id')
        
        logger.info(f"Evaluating policies for execution {execution_id}")
        
        # Evaluate policies for the execution
        # await self.policy_service.evaluate_execution_policies(execution_id, plan_id)


class CapsulePublishedHandler(EventHandler):
    """Handler for capsule published events."""
    
    def __init__(self, policy_service):
        self.policy_service = policy_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.CAPSULE_PUBLISHED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle capsule published event."""
        data = event.data
        capsule_id = data.get('capsule_id')
        
        logger.info(f"Evaluating publication policies for capsule {capsule_id}")
        
        # Evaluate publication policies
        # await self.policy_service.evaluate_publication_policies(capsule_id)


# Plan Compiler Event Handlers

class PlanCompilationRequestHandler(EventHandler):
    """Handler for plan compilation requests."""
    
    def __init__(self, compiler_service):
        self.compiler_service = compiler_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.CAPSULE_CREATED, EventType.CAPSULE_UPDATED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle capsule events that might require plan compilation."""
        data = event.data
        capsule_id = data.get('capsule_id')
        
        logger.info(f"Triggering plan compilation for capsule {capsule_id}")
        
        # Trigger plan compilation
        # await self.compiler_service.compile_plan(capsule_id)


# GhostRun Service Event Handlers

class PreflightTriggerHandler(EventHandler):
    """Handler for events that trigger preflight checks."""
    
    def __init__(self, ghostrun_service):
        self.ghostrun_service = ghostrun_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.PLAN_COMPILED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle plan compiled events to trigger preflight."""
        data = event.data
        plan_id = data.get('plan_id')
        
        logger.info(f"Triggering preflight check for plan {plan_id}")
        
        # Trigger preflight check
        # await self.ghostrun_service.start_preflight(plan_id)


# Orchestrator Service Event Handlers

class ExecutionTriggerHandler(EventHandler):
    """Handler for events that trigger execution."""
    
    def __init__(self, orchestrator_service):
        self.orchestrator_service = orchestrator_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.PREFLIGHT_COMPLETED, EventType.APPROVAL_GRANTED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle events that should trigger execution."""
        if event.type == EventType.PREFLIGHT_COMPLETED:
            data = event.data
            plan_id = data.get('plan_id')
            results = data.get('results', {})
            
            # Check if preflight passed
            if results.get('status') == 'success':
                logger.info(f"Preflight passed, ready to execute plan {plan_id}")
                # await self.orchestrator_service.prepare_execution(plan_id)
                
        elif event.type == EventType.APPROVAL_GRANTED:
            data = event.data
            execution_id = data.get('execution_id')
            
            logger.info(f"Approval granted, executing plan for {execution_id}")
            # await self.orchestrator_service.start_execution(execution_id)


class PolicyViolationExecutionHandler(EventHandler):
    """Handler for policy violations during execution."""
    
    def __init__(self, orchestrator_service):
        self.orchestrator_service = orchestrator_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.POLICY_VIOLATED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle policy violations during execution."""
        data = event.data
        resource_id = data.get('resource_id')
        
        logger.warning(f"Policy violation detected for resource {resource_id}")
        
        # Pause or stop execution if needed
        # await self.orchestrator_service.handle_policy_violation(resource_id, data)


# Approval Service Event Handlers

class ApprovalRequestHandler(EventHandler):
    """Handler for events that require approval."""
    
    def __init__(self, approval_service):
        self.approval_service = approval_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.EXECUTION_STARTED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle execution started events to check for approval requirements."""
        data = event.data
        execution_id = data.get('execution_id')
        plan_id = data.get('plan_id')
        
        logger.info(f"Checking approval requirements for execution {execution_id}")
        
        # Check if approval is required
        # approval_required = await self.approval_service.check_approval_required(plan_id)
        # if approval_required:
        #     await self.approval_service.request_approval(execution_id, plan_id)


# Capability Token Service Event Handlers

class TokenValidationHandler(EventHandler):
    """Handler for events requiring token validation."""
    
    def __init__(self, token_service):
        self.token_service = token_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.EXECUTION_STARTED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle execution started events to validate tokens."""
        data = event.data
        execution_id = data.get('execution_id')
        
        logger.info(f"Validating capability tokens for execution {execution_id}")
        
        # Validate tokens
        # await self.token_service.validate_execution_tokens(execution_id)


class TokenExpirationHandler(EventHandler):
    """Handler for token expiration events."""
    
    def __init__(self, token_service):
        self.token_service = token_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.TOKEN_EXPIRED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle token expiration events."""
        data = event.data
        token_id = data.get('token_id')
        
        logger.info(f"Processing token expiration for {token_id}")
        
        # Clean up expired tokens
        # await self.token_service.cleanup_expired_token(token_id)


# Receipt Service Event Handlers

class ReceiptGenerationHandler(EventHandler):
    """Handler for events that trigger receipt generation."""
    
    def __init__(self, receipt_service):
        self.receipt_service = receipt_service
        
    def get_supported_event_types(self) -> Set[str]:
        return {EventType.EXECUTION_COMPLETED}
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle execution completed events to generate receipts."""
        data = event.data
        execution_id = data.get('execution_id')
        results = data.get('results', {})
        
        logger.info(f"Generating receipt for execution {execution_id}")
        
        # Generate execution receipt
        # await self.receipt_service.generate_execution_receipt(execution_id, results)


# Audit Service Event Handlers

class AuditEventHandler(EventHandler):
    """Handler for all events that should be audited."""
    
    def __init__(self, audit_service):
        self.audit_service = audit_service
        
    def get_supported_event_types(self) -> Set[str]:
        # Audit all event types
        return {
            EventType.CAPSULE_CREATED, EventType.CAPSULE_UPDATED, EventType.CAPSULE_DELETED,
            EventType.CAPSULE_PUBLISHED, EventType.POLICY_CREATED, EventType.POLICY_UPDATED,
            EventType.POLICY_VIOLATED, EventType.POLICY_ENFORCED, EventType.PLAN_COMPILED,
            EventType.PREFLIGHT_STARTED, EventType.PREFLIGHT_COMPLETED, EventType.PREFLIGHT_FAILED,
            EventType.EXECUTION_STARTED, EventType.EXECUTION_COMPLETED, EventType.EXECUTION_FAILED,
            EventType.APPROVAL_REQUESTED, EventType.APPROVAL_GRANTED, EventType.APPROVAL_REJECTED,
            EventType.TOKEN_ISSUED, EventType.TOKEN_VERIFIED, EventType.TOKEN_EXPIRED,
            EventType.RECEIPT_CREATED, EventType.RECEIPT_VERIFIED
        }
        
    async def handle(self, event: CloudEvent) -> None:
        """Handle all events for auditing."""
        logger.debug(f"Auditing event {event.type}: {event.id}")
        
        # Create audit record
        audit_data = {
            "event_id": event.id,
            "event_type": event.type,
            "source": event.source,
            "subject": event.subject,
            "tenant_id": event.tenantid,
            "correlation_id": event.correlationid,
            "event_time": event.time.isoformat() if event.time else None,
            "data": event.data
        }
        
        # await self.audit_service.create_audit_record(audit_data)


# Service-Specific Subscribers

class CapsuleRegistryEventSubscriber(BaseEventSubscriber):
    """Event subscriber for Capsule Registry service."""
    
    def __init__(self, event_bus: EventBusService, registry_service=None):
        super().__init__("registry", event_bus)
        
        # Register handlers
        self.register_handler(CapsuleCreatedHandler(registry_service))
        self.register_handler(PolicyViolationHandler(registry_service))


class PolicyEventSubscriber(BaseEventSubscriber):
    """Event subscriber for Policy service."""
    
    def __init__(self, event_bus: EventBusService, policy_service=None):
        super().__init__("policy", event_bus)
        
        # Register handlers
        self.register_handler(ExecutionStartedHandler(policy_service))
        self.register_handler(CapsulePublishedHandler(policy_service))


class PlanCompilerEventSubscriber(BaseEventSubscriber):
    """Event subscriber for Plan Compiler service."""
    
    def __init__(self, event_bus: EventBusService, compiler_service=None):
        super().__init__("plan-compiler", event_bus)
        
        # Register handlers
        self.register_handler(PlanCompilationRequestHandler(compiler_service))


class GhostRunEventSubscriber(BaseEventSubscriber):
    """Event subscriber for GhostRun service."""
    
    def __init__(self, event_bus: EventBusService, ghostrun_service=None):
        super().__init__("ghostrun", event_bus)
        
        # Register handlers
        self.register_handler(PreflightTriggerHandler(ghostrun_service))


class OrchestratorEventSubscriber(BaseEventSubscriber):
    """Event subscriber for Orchestrator service."""
    
    def __init__(self, event_bus: EventBusService, orchestrator_service=None):
        super().__init__("orchestrator", event_bus)
        
        # Register handlers
        self.register_handler(ExecutionTriggerHandler(orchestrator_service))
        self.register_handler(PolicyViolationExecutionHandler(orchestrator_service))


class ApprovalEventSubscriber(BaseEventSubscriber):
    """Event subscriber for Approval service."""
    
    def __init__(self, event_bus: EventBusService, approval_service=None):
        super().__init__("approvals", event_bus)
        
        # Register handlers
        self.register_handler(ApprovalRequestHandler(approval_service))


class CapabilityTokenEventSubscriber(BaseEventSubscriber):
    """Event subscriber for Capability Token service."""
    
    def __init__(self, event_bus: EventBusService, token_service=None):
        super().__init__("captokens", event_bus)
        
        # Register handlers
        self.register_handler(TokenValidationHandler(token_service))
        self.register_handler(TokenExpirationHandler(token_service))


class ReceiptEventSubscriber(BaseEventSubscriber):
    """Event subscriber for Receipt service."""
    
    def __init__(self, event_bus: EventBusService, receipt_service=None):
        super().__init__("receipt", event_bus)
        
        # Register handlers
        self.register_handler(ReceiptGenerationHandler(receipt_service))


class AuditEventSubscriber(BaseEventSubscriber):
    """Event subscriber for Audit service."""
    
    def __init__(self, event_bus: EventBusService, audit_service=None):
        super().__init__("audit", event_bus)
        
        # Register handlers
        self.register_handler(AuditEventHandler(audit_service))


class EventSubscriberFactory:
    """Factory for creating service-specific event subscribers."""
    
    def __init__(self, event_bus: EventBusService):
        self.event_bus = event_bus
        
    def create_registry_subscriber(self, registry_service=None) -> CapsuleRegistryEventSubscriber:
        """Create capsule registry event subscriber."""
        return CapsuleRegistryEventSubscriber(self.event_bus, registry_service)
        
    def create_policy_subscriber(self, policy_service=None) -> PolicyEventSubscriber:
        """Create policy event subscriber."""
        return PolicyEventSubscriber(self.event_bus, policy_service)
        
    def create_plan_compiler_subscriber(self, compiler_service=None) -> PlanCompilerEventSubscriber:
        """Create plan compiler event subscriber."""
        return PlanCompilerEventSubscriber(self.event_bus, compiler_service)
        
    def create_ghostrun_subscriber(self, ghostrun_service=None) -> GhostRunEventSubscriber:
        """Create ghostrun event subscriber.""" 
        return GhostRunEventSubscriber(self.event_bus, ghostrun_service)
        
    def create_orchestrator_subscriber(self, orchestrator_service=None) -> OrchestratorEventSubscriber:
        """Create orchestrator event subscriber."""
        return OrchestratorEventSubscriber(self.event_bus, orchestrator_service)
        
    def create_approval_subscriber(self, approval_service=None) -> ApprovalEventSubscriber:
        """Create approval event subscriber."""
        return ApprovalEventSubscriber(self.event_bus, approval_service)
        
    def create_capability_token_subscriber(self, token_service=None) -> CapabilityTokenEventSubscriber:
        """Create capability token event subscriber."""
        return CapabilityTokenEventSubscriber(self.event_bus, token_service)
        
    def create_receipt_subscriber(self, receipt_service=None) -> ReceiptEventSubscriber:
        """Create receipt event subscriber."""
        return ReceiptEventSubscriber(self.event_bus, receipt_service)
        
    def create_audit_subscriber(self, audit_service=None) -> AuditEventSubscriber:
        """Create audit event subscriber."""
        return AuditEventSubscriber(self.event_bus, audit_service)
