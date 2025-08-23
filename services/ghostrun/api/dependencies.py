"""FastAPI dependencies for GhostRun service."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Header
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.service import ghostrun_service


async def get_ghostrun_service():
    """Get GhostRun service instance."""
    return ghostrun_service


async def get_tenant_id(x_tenant_id: Optional[str] = Header(None)) -> UUID:
    """Extract tenant ID from request headers."""
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
    
    try:
        return UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant ID format")


async def get_current_user_id(x_user_id: Optional[str] = Header(None)) -> Optional[UUID]:
    """Extract user ID from request headers."""
    if not x_user_id:
        return None
    
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")