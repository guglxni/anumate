"""Anumate events and messaging utilities."""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

class EventPublisher:
    """Event publisher for CloudEvents."""
    
    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self.published_events = []
    
    async def publish(self, event_type: str, data: Dict[str, Any], 
                     source: str = "anumate", subject: Optional[str] = None):
        """Publish an event."""
        event = {
            "event_type": event_type,
            "source": source,
            "subject": subject or event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.published_events.append(event)
        
        if self.event_bus:
            await self.event_bus.publish(
                subject=subject or event_type,
                event_type=event_type,
                source=source,
                data=data
            )
    
    def get_published_events(self) -> List[Dict[str, Any]]:
        """Get all published events."""
        return self.published_events.copy()
    
    def clear_events(self):
        """Clear published events."""
        self.published_events.clear()