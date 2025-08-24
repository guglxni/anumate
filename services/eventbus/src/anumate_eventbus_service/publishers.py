"""
CloudEvents Event Publishers for Anumate Services
=================================================

Provides standardized event publishing capabilities for all Anumate microservices.
Each service gets its own publisher with automatic CloudEvents formatting and routing.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .eventbus_core import CloudEvent, EventType, EventBusService

logger = logging.getLogger(__name__)


@dataclass 
class EventContext:
    """Context information for event publishing."""
    tenant_id: Optional[str] = None
    correlation_id: Optional[str] = None
    trace_context: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None


class BaseEventPublisher:
    """Base class for service-specific event publishers."""
    
    def __init__(self, service_name: str, event_bus: EventBusService, base_source: str):
        self.service_name = service_name
        self.event_bus = event_bus
        self.base_source = base_source
        
    def _create_event(
        self, 
        event_type: str,
        data: Dict[str, Any],
        context: Optional[EventContext] = None,
        subject: Optional[str] = None
    ) -> CloudEvent:
        """Create a CloudEvent with standard attributes."""
        return CloudEvent(
            type=event_type,
            source=f"{self.base_source}/{self.service_name}",
            data=data,
            subject=subject,
            tenantid=context.tenant_id if context else None,
            correlationid=context.correlation_id if context else None,
            tracecontext=context.trace_context if context else None
        )
        
    async def publish_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        context: Optional[EventContext] = None,
        subject: Optional[str] = None
    ) -> str:
        """Publish an event."""
        event = self._create_event(event_type, data, context, subject)
        return await self.event_bus.publish_event(event)


class CapsuleRegistryEventPublisher(BaseEventPublisher):
    """Event publisher for Capsule Registry service."""
    
    def __init__(self, event_bus: EventBusService):
        super().__init__("registry", event_bus, "https://anumate.com/services")
        
    async def publish_capsule_created(
        self,
        capsule_id: str,
        capsule_name: str,
        version: str,
        author: str,
        context: Optional[EventContext] = None
    ) -> str:
        """Publish capsule created event."""
        data = {
            "capsule_id": capsule_id,
            "name": capsule_name,
            "version": version,
            "author": author,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.CAPSULE_CREATED,
            data,
            context,
            subject=f"capsule.{capsule_id}"
        )
        
    async def publish_capsule_updated(
        self,
        capsule_id: str,
        capsule_name: str,
        version: str,
        changes: List[str],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish capsule updated event."""
        data = {
            "capsule_id": capsule_id,
            "name": capsule_name,
            "version": version,
            "changes": changes,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.CAPSULE_UPDATED,
            data,
            context,
            subject=f"capsule.{capsule_id}"
        )
        
    async def publish_capsule_published(
        self,
        capsule_id: str,
        capsule_name: str,
        version: str,
        registry_url: str,
        context: Optional[EventContext] = None
    ) -> str:
        """Publish capsule published event."""
        data = {
            "capsule_id": capsule_id,
            "name": capsule_name,
            "version": version,
            "registry_url": registry_url,
            "published_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.CAPSULE_PUBLISHED,
            data,
            context,
            subject=f"capsule.{capsule_id}"
        )


class PolicyEventPublisher(BaseEventPublisher):
    """Event publisher for Policy service."""
    
    def __init__(self, event_bus: EventBusService):
        super().__init__("policy", event_bus, "https://anumate.com/services")
        
    async def publish_policy_created(
        self,
        policy_id: str,
        policy_name: str,
        policy_type: str,
        rules: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish policy created event."""
        data = {
            "policy_id": policy_id,
            "name": policy_name,
            "type": policy_type,
            "rules": rules,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.POLICY_CREATED,
            data,
            context,
            subject=f"policy.{policy_id}"
        )
        
    async def publish_policy_violated(
        self,
        policy_id: str,
        policy_name: str,
        violation_details: Dict[str, Any],
        resource_id: str,
        context: Optional[EventContext] = None
    ) -> str:
        """Publish policy violation event."""
        data = {
            "policy_id": policy_id,
            "policy_name": policy_name,
            "violation_details": violation_details,
            "resource_id": resource_id,
            "violated_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.POLICY_VIOLATED,
            data,
            context,
            subject=f"policy.{policy_id}.violation"
        )
        
    async def publish_policy_enforced(
        self,
        policy_id: str,
        enforcement_action: str,
        resource_id: str,
        enforcement_result: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish policy enforcement event."""
        data = {
            "policy_id": policy_id,
            "enforcement_action": enforcement_action,
            "resource_id": resource_id,
            "enforcement_result": enforcement_result,
            "enforced_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.POLICY_ENFORCED,
            data,
            context,
            subject=f"policy.{policy_id}.enforcement"
        )


class PlanCompilerEventPublisher(BaseEventPublisher):
    """Event publisher for Plan Compiler service."""
    
    def __init__(self, event_bus: EventBusService):
        super().__init__("plan-compiler", event_bus, "https://anumate.com/services")
        
    async def publish_plan_compiled(
        self,
        plan_id: str,
        capsule_id: str,
        compilation_result: Dict[str, Any],
        execution_graph: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish plan compiled event."""
        data = {
            "plan_id": plan_id,
            "capsule_id": capsule_id,
            "compilation_result": compilation_result,
            "execution_graph": execution_graph,
            "compiled_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.PLAN_COMPILED,
            data,
            context,
            subject=f"plan.{plan_id}"
        )
        
    async def publish_plan_compilation_failed(
        self,
        plan_id: str,
        capsule_id: str,
        error_details: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish plan compilation failed event."""
        data = {
            "plan_id": plan_id,
            "capsule_id": capsule_id,
            "error_details": error_details,
            "failed_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.PLAN_COMPILATION_FAILED,
            data,
            context,
            subject=f"plan.{plan_id}.error"
        )


class GhostRunEventPublisher(BaseEventPublisher):
    """Event publisher for GhostRun service."""
    
    def __init__(self, event_bus: EventBusService):
        super().__init__("ghostrun", event_bus, "https://anumate.com/services")
        
    async def publish_preflight_started(
        self,
        preflight_id: str,
        plan_id: str,
        preflight_config: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish preflight started event."""
        data = {
            "preflight_id": preflight_id,
            "plan_id": plan_id,
            "config": preflight_config,
            "started_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.PREFLIGHT_STARTED,
            data,
            context,
            subject=f"preflight.{preflight_id}"
        )
        
    async def publish_preflight_completed(
        self,
        preflight_id: str,
        plan_id: str,
        results: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish preflight completed event."""
        data = {
            "preflight_id": preflight_id,
            "plan_id": plan_id,
            "results": results,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.PREFLIGHT_COMPLETED,
            data,
            context,
            subject=f"preflight.{preflight_id}"
        )


class OrchestratorEventPublisher(BaseEventPublisher):
    """Event publisher for Orchestrator service."""
    
    def __init__(self, event_bus: EventBusService):
        super().__init__("orchestrator", event_bus, "https://anumate.com/services")
        
    async def publish_execution_started(
        self,
        execution_id: str,
        plan_id: str,
        execution_config: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish execution started event."""
        data = {
            "execution_id": execution_id,
            "plan_id": plan_id,
            "config": execution_config,
            "started_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.EXECUTION_STARTED,
            data,
            context,
            subject=f"execution.{execution_id}"
        )
        
    async def publish_execution_completed(
        self,
        execution_id: str,
        plan_id: str,
        results: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish execution completed event."""
        data = {
            "execution_id": execution_id,
            "plan_id": plan_id,
            "results": results,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.EXECUTION_COMPLETED,
            data,
            context,
            subject=f"execution.{execution_id}"
        )
        
    async def publish_execution_failed(
        self,
        execution_id: str,
        plan_id: str,
        error_details: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish execution failed event."""
        data = {
            "execution_id": execution_id,
            "plan_id": plan_id,
            "error_details": error_details,
            "failed_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.EXECUTION_FAILED,
            data,
            context,
            subject=f"execution.{execution_id}.error"
        )


class ApprovalEventPublisher(BaseEventPublisher):
    """Event publisher for Approval service."""
    
    def __init__(self, event_bus: EventBusService):
        super().__init__("approvals", event_bus, "https://anumate.com/services")
        
    async def publish_approval_requested(
        self,
        approval_id: str,
        execution_id: str,
        approval_details: Dict[str, Any],
        approvers: List[str],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish approval requested event."""
        data = {
            "approval_id": approval_id,
            "execution_id": execution_id,
            "approval_details": approval_details,
            "approvers": approvers,
            "requested_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.APPROVAL_REQUESTED,
            data,
            context,
            subject=f"approval.{approval_id}"
        )
        
    async def publish_approval_granted(
        self,
        approval_id: str,
        execution_id: str,
        approver: str,
        approval_notes: str,
        context: Optional[EventContext] = None
    ) -> str:
        """Publish approval granted event."""
        data = {
            "approval_id": approval_id,
            "execution_id": execution_id,
            "approver": approver,
            "approval_notes": approval_notes,
            "granted_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.APPROVAL_GRANTED,
            data,
            context,
            subject=f"approval.{approval_id}"
        )


class CapabilityTokenEventPublisher(BaseEventPublisher):
    """Event publisher for Capability Token service."""
    
    def __init__(self, event_bus: EventBusService):
        super().__init__("captokens", event_bus, "https://anumate.com/services")
        
    async def publish_token_issued(
        self,
        token_id: str,
        capabilities: List[str],
        expires_at: datetime,
        context: Optional[EventContext] = None
    ) -> str:
        """Publish token issued event."""
        data = {
            "token_id": token_id,
            "capabilities": capabilities,
            "expires_at": expires_at.isoformat(),
            "issued_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.TOKEN_ISSUED,
            data,
            context,
            subject=f"token.{token_id}"
        )
        
    async def publish_token_verified(
        self,
        token_id: str,
        verification_result: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish token verified event."""
        data = {
            "token_id": token_id,
            "verification_result": verification_result,
            "verified_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.TOKEN_VERIFIED,
            data,
            context,
            subject=f"token.{token_id}.verification"
        )


class ReceiptEventPublisher(BaseEventPublisher):
    """Event publisher for Receipt service."""
    
    def __init__(self, event_bus: EventBusService):
        super().__init__("receipt", event_bus, "https://anumate.com/services")
        
    async def publish_receipt_created(
        self,
        receipt_id: str,
        execution_id: str,
        receipt_data: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish receipt created event."""
        data = {
            "receipt_id": receipt_id,
            "execution_id": execution_id,
            "receipt_data": receipt_data,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.RECEIPT_CREATED,
            data,
            context,
            subject=f"receipt.{receipt_id}"
        )
        
    async def publish_receipt_verified(
        self,
        receipt_id: str,
        verification_result: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish receipt verified event."""
        data = {
            "receipt_id": receipt_id,
            "verification_result": verification_result,
            "verified_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.RECEIPT_VERIFIED,
            data,
            context,
            subject=f"receipt.{receipt_id}.verification"
        )


class AuditEventPublisher(BaseEventPublisher):
    """Event publisher for Audit service."""
    
    def __init__(self, event_bus: EventBusService):
        super().__init__("audit", event_bus, "https://anumate.com/services")
        
    async def publish_audit_event_captured(
        self,
        audit_id: str,
        event_data: Dict[str, Any],
        context: Optional[EventContext] = None
    ) -> str:
        """Publish audit event captured event."""
        data = {
            "audit_id": audit_id,
            "event_data": event_data,
            "captured_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.AUDIT_EVENT_CAPTURED,
            data,
            context,
            subject=f"audit.{audit_id}"
        )
        
    async def publish_audit_export_completed(
        self,
        export_id: str,
        export_format: str,
        record_count: int,
        export_location: str,
        context: Optional[EventContext] = None
    ) -> str:
        """Publish audit export completed event."""
        data = {
            "export_id": export_id,
            "format": export_format,
            "record_count": record_count,
            "export_location": export_location,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await self.publish_event(
            EventType.AUDIT_EXPORT_COMPLETED,
            data,
            context,
            subject=f"audit.export.{export_id}"
        )


class EventPublisherFactory:
    """Factory for creating service-specific event publishers."""
    
    def __init__(self, event_bus: EventBusService):
        self.event_bus = event_bus
        self._publishers = {}
        
    def get_capsule_registry_publisher(self) -> CapsuleRegistryEventPublisher:
        """Get capsule registry event publisher."""
        if "registry" not in self._publishers:
            self._publishers["registry"] = CapsuleRegistryEventPublisher(self.event_bus)
        return self._publishers["registry"]
        
    def get_policy_publisher(self) -> PolicyEventPublisher:
        """Get policy event publisher."""
        if "policy" not in self._publishers:
            self._publishers["policy"] = PolicyEventPublisher(self.event_bus)
        return self._publishers["policy"]
        
    def get_plan_compiler_publisher(self) -> PlanCompilerEventPublisher:
        """Get plan compiler event publisher."""
        if "plan-compiler" not in self._publishers:
            self._publishers["plan-compiler"] = PlanCompilerEventPublisher(self.event_bus)
        return self._publishers["plan-compiler"]
        
    def get_ghostrun_publisher(self) -> GhostRunEventPublisher:
        """Get ghostrun event publisher."""
        if "ghostrun" not in self._publishers:
            self._publishers["ghostrun"] = GhostRunEventPublisher(self.event_bus)
        return self._publishers["ghostrun"]
        
    def get_orchestrator_publisher(self) -> OrchestratorEventPublisher:
        """Get orchestrator event publisher."""
        if "orchestrator" not in self._publishers:
            self._publishers["orchestrator"] = OrchestratorEventPublisher(self.event_bus)
        return self._publishers["orchestrator"]
        
    def get_approval_publisher(self) -> ApprovalEventPublisher:
        """Get approval event publisher."""
        if "approvals" not in self._publishers:
            self._publishers["approvals"] = ApprovalEventPublisher(self.event_bus)
        return self._publishers["approvals"]
        
    def get_capability_token_publisher(self) -> CapabilityTokenEventPublisher:
        """Get capability token event publisher."""
        if "captokens" not in self._publishers:
            self._publishers["captokens"] = CapabilityTokenEventPublisher(self.event_bus)
        return self._publishers["captokens"]
        
    def get_receipt_publisher(self) -> ReceiptEventPublisher:
        """Get receipt event publisher."""
        if "receipt" not in self._publishers:
            self._publishers["receipt"] = ReceiptEventPublisher(self.event_bus)
        return self._publishers["receipt"]
        
    def get_audit_publisher(self) -> AuditEventPublisher:
        """Get audit event publisher."""
        if "audit" not in self._publishers:
            self._publishers["audit"] = AuditEventPublisher(self.event_bus)
        return self._publishers["audit"]
