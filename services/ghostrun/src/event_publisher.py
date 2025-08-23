"""CloudEvents publisher for GhostRun service."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel

from .models import GhostRunStatus, PreflightReport, SimulationStatus

# Optional CloudEvents support
try:
    from cloudevents.http import CloudEvent
    CLOUDEVENTS_AVAILABLE = True
except ImportError:
    CLOUDEVENTS_AVAILABLE = False
    CloudEvent = None


class PreflightCompletedEvent(BaseModel):
    """Event data for preflight.completed CloudEvent."""
    
    run_id: UUID
    tenant_id: UUID
    plan_hash: str
    status: str
    execution_feasible: bool
    overall_risk_level: str
    total_estimated_duration_ms: int
    total_steps: int
    steps_with_issues: int
    high_risk_steps: int
    critical_issues_count: int
    warnings_count: int
    recommendations_count: int
    simulation_duration_ms: int
    generated_at: datetime


class EventPublisher:
    """Publishes CloudEvents for GhostRun operations."""
    
    def __init__(self, event_bus_url: Optional[str] = None) -> None:
        self.event_bus_url = event_bus_url or "nats://localhost:4222"
        self.source = "anumate.ghostrun"
    
    async def publish_preflight_completed(
        self, 
        run_status: GhostRunStatus,
        report: PreflightReport
    ) -> None:
        """Publish preflight.completed CloudEvent."""
        
        # Create event data
        event_data = PreflightCompletedEvent(
            run_id=run_status.run_id,
            tenant_id=run_status.tenant_id,
            plan_hash=run_status.plan_hash,
            status=report.overall_status,
            execution_feasible=report.execution_feasible,
            overall_risk_level=report.overall_risk_level.value,
            total_estimated_duration_ms=report.total_estimated_duration_ms,
            total_steps=report.total_steps,
            steps_with_issues=report.steps_with_issues,
            high_risk_steps=report.high_risk_steps,
            critical_issues_count=len(report.critical_issues),
            warnings_count=len(report.warnings),
            recommendations_count=len(report.recommendations),
            simulation_duration_ms=report.simulation_duration_ms,
            generated_at=report.generated_at
        )
        
        # Create CloudEvent
        if CLOUDEVENTS_AVAILABLE:
            event = CloudEvent(
                {
                    "type": "preflight.completed",
                    "source": self.source,
                    "subject": f"tenant/{run_status.tenant_id}/run/{run_status.run_id}",
                    "id": str(run_status.run_id),
                    "time": datetime.now(timezone.utc).isoformat(),
                    "datacontenttype": "application/json",
                    "specversion": "1.0"
                },
                event_data.model_dump(mode='json')
            )
        else:
            # Fallback to simple dict structure
            event = {
                "type": "preflight.completed",
                "source": self.source,
                "subject": f"tenant/{run_status.tenant_id}/run/{run_status.run_id}",
                "id": str(run_status.run_id),
                "time": datetime.now(timezone.utc).isoformat(),
                "datacontenttype": "application/json",
                "specversion": "1.0",
                "data": event_data.model_dump(mode='json')
            }
        
        # Publish event (in real implementation, would use actual event bus)
        await self._publish_event(event)
    
    async def publish_simulation_started(
        self, 
        run_status: GhostRunStatus
    ) -> None:
        """Publish simulation.started CloudEvent."""
        
        event_data = {
            "run_id": str(run_status.run_id),
            "tenant_id": str(run_status.tenant_id),
            "plan_hash": run_status.plan_hash,
            "started_at": run_status.started_at.isoformat() if run_status.started_at else None
        }
        
        if CLOUDEVENTS_AVAILABLE:
            event = CloudEvent(
                {
                    "type": "simulation.started",
                    "source": self.source,
                    "subject": f"tenant/{run_status.tenant_id}/run/{run_status.run_id}",
                    "id": f"{run_status.run_id}-started",
                    "time": datetime.now(timezone.utc).isoformat(),
                    "datacontenttype": "application/json",
                    "specversion": "1.0"
                },
                event_data
            )
        else:
            event = {
                "type": "simulation.started",
                "source": self.source,
                "subject": f"tenant/{run_status.tenant_id}/run/{run_status.run_id}",
                "id": f"{run_status.run_id}-started",
                "time": datetime.now(timezone.utc).isoformat(),
                "datacontenttype": "application/json",
                "specversion": "1.0",
                "data": event_data
            }
        
        await self._publish_event(event)
    
    async def publish_simulation_failed(
        self, 
        run_status: GhostRunStatus
    ) -> None:
        """Publish simulation.failed CloudEvent."""
        
        event_data = {
            "run_id": str(run_status.run_id),
            "tenant_id": str(run_status.tenant_id),
            "plan_hash": run_status.plan_hash,
            "error_message": run_status.error_message,
            "failed_at": run_status.completed_at.isoformat() if run_status.completed_at else None
        }
        
        if CLOUDEVENTS_AVAILABLE:
            event = CloudEvent(
                {
                    "type": "simulation.failed",
                    "source": self.source,
                    "subject": f"tenant/{run_status.tenant_id}/run/{run_status.run_id}",
                    "id": f"{run_status.run_id}-failed",
                    "time": datetime.now(timezone.utc).isoformat(),
                    "datacontenttype": "application/json",
                    "specversion": "1.0"
                },
                event_data
            )
        else:
            event = {
                "type": "simulation.failed",
                "source": self.source,
                "subject": f"tenant/{run_status.tenant_id}/run/{run_status.run_id}",
                "id": f"{run_status.run_id}-failed",
                "time": datetime.now(timezone.utc).isoformat(),
                "datacontenttype": "application/json",
                "specversion": "1.0",
                "data": event_data
            }
        
        await self._publish_event(event)
    
    async def _publish_event(self, event) -> None:
        """Publish CloudEvent to event bus."""
        
        # In a real implementation, this would publish to NATS/Kafka
        # For now, we'll just log the event
        if CLOUDEVENTS_AVAILABLE and hasattr(event, 'get'):
            print(f"Publishing CloudEvent: {event['type']} for {event['subject']}")
            print(f"Event data: {json.dumps(event.data, indent=2, default=str)}")
        else:
            print(f"Publishing Event: {event['type']} for {event['subject']}")
            print(f"Event data: {json.dumps(event.get('data', {}), indent=2, default=str)}")
        
        # TODO: Implement actual event bus publishing
        # Example with NATS:
        # import nats
        # nc = await nats.connect(self.event_bus_url)
        # await nc.publish(f"events.{event['type']}", event.data.encode())
        # await nc.close()


# Global event publisher instance
event_publisher = EventPublisher()