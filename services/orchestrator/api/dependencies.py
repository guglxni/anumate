"""FastAPI dependencies for orchestrator service."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Header, status
# Simplified for demo - would use real TenantContext in production
class TenantContext:
    def __init__(self):
        self._tenant_id = None
    
    def set_tenant_id(self, tenant_id):
        self._tenant_id = tenant_id
    
    def get_tenant_id(self):
        return self._tenant_id

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.service import OrchestratorService


async def get_tenant_id(
    x_tenant_id: Annotated[str, Header(description="Tenant ID")]
) -> UUID:
    """Extract tenant ID from headers.
    
    Args:
        x_tenant_id: Tenant ID from header
        
    Returns:
        Parsed tenant UUID
        
    Raises:
        HTTPException: If tenant ID is invalid
    """
    try:
        return UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID format"
        )


async def get_orchestrator_service() -> OrchestratorService:
    """Get orchestrator service instance.
    
    Returns:
        Orchestrator service instance
    """
    # In production, this would be injected with proper dependencies
    return OrchestratorService()


async def get_tenant_context_dep() -> TenantContext:
    """Get tenant context dependency.
    
    Returns:
        Tenant context
    """
    return TenantContext()