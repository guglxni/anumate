"""FastAPI dependencies for Policy Service."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from anumate_infrastructure.database import DatabaseManager
from anumate_infrastructure.tenant_context import get_current_tenant_id, get_current_user_id

from src.policy_service import PolicyService


async def get_database_manager(request: Request) -> DatabaseManager:
    """Get database manager from application state."""
    return request.app.state.db_manager


async def get_policy_service(
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> PolicyService:
    """Get Policy service instance."""
    return PolicyService(db_manager)


async def get_current_tenant() -> UUID:
    """Get current tenant ID from context."""
    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required"
        )
    return tenant_id


async def get_current_user() -> UUID:
    """Get current user ID from context."""
    user_id = get_current_user_id()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User authentication required"
        )
    return user_id


async def get_optional_user() -> Optional[UUID]:
    """Get current user ID from context (optional)."""
    return get_current_user_id()