"""
Anumate CloudEvents Event Bus Service
=====================================

Enterprise-grade event bus service providing CloudEvents v1.0 compliant
event-driven architecture for the Anumate platform.

Features:
- CloudEvents v1.0 compliant event publishing and subscribing
- NATS JetStream for reliable event streaming
- Event routing and filtering
- Dead letter handling for failed events
- Event replay capabilities
- Redis-backed event tracking and metrics
- REST API for event bus management
- Service-specific publishers and subscribers
"""

from .eventbus_core import (
    EventBusService, 
    EventBusConfig,
    CloudEvent,
    EventType,
    EventSubscription
)

from .publishers import (
    EventPublisherFactory,
    EventContext,
    BaseEventPublisher,
    CapsuleRegistryEventPublisher,
    PolicyEventPublisher, 
    PlanCompilerEventPublisher,
    GhostRunEventPublisher,
    OrchestratorEventPublisher,
    ApprovalEventPublisher,
    CapabilityTokenEventPublisher,
    ReceiptEventPublisher,
    AuditEventPublisher
)

from .subscribers import (
    EventSubscriberFactory,
    EventHandler,
    BaseEventSubscriber,
    CapsuleRegistryEventSubscriber,
    PolicyEventSubscriber,
    PlanCompilerEventSubscriber,
    GhostRunEventSubscriber,
    OrchestratorEventSubscriber,
    ApprovalEventSubscriber,
    CapabilityTokenEventSubscriber,
    ReceiptEventSubscriber,
    AuditEventSubscriber
)

from .app import app

__version__ = "1.0.0"
__all__ = [
    # Core
    "EventBusService",
    "EventBusConfig", 
    "CloudEvent",
    "EventType",
    "EventSubscription",
    
    # Publishers
    "EventPublisherFactory",
    "EventContext",
    "BaseEventPublisher",
    "CapsuleRegistryEventPublisher",
    "PolicyEventPublisher",
    "PlanCompilerEventPublisher", 
    "GhostRunEventPublisher",
    "OrchestratorEventPublisher",
    "ApprovalEventPublisher",
    "CapabilityTokenEventPublisher",
    "ReceiptEventPublisher",
    "AuditEventPublisher",
    
    # Subscribers
    "EventSubscriberFactory",
    "EventHandler",
    "BaseEventSubscriber",
    "CapsuleRegistryEventSubscriber",
    "PolicyEventSubscriber",
    "PlanCompilerEventSubscriber",
    "GhostRunEventSubscriber", 
    "OrchestratorEventSubscriber",
    "ApprovalEventSubscriber",
    "CapabilityTokenEventSubscriber",
    "ReceiptEventSubscriber",
    "AuditEventSubscriber",
    
    # FastAPI app
    "app"
]
