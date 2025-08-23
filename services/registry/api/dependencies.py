"""FastAPI dependencies for Capsule Registry."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from anumate_infrastructure.database import DatabaseManager
from anumate_infrastructure.tenant_context import get_current_tenant_id, get_current_user_id

from src.service import CapsuleRegistryService


def get_database_manager(request: Request) -> DatabaseManager:
    """Get database manager from application state."""
    return request.app.state.db_manager


def get_capsule_service(
    db_manager: Annotated[DatabaseManager, Depends(get_database_manager)]
) -> CapsuleRegistryService:
    """Get Capsule Registry Service instance."""
    return CapsuleRegistryService(db_manager)


def get_current_tenant() -> UUID:
    """Get current tenant ID from context."""
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        raise HTTPException(
            status_code=401,
            detail="No tenant context found. Please authenticate."
        )
    return tenant_id


def get_current_user() -> UUID:
    """Get current user ID from context."""
    user_id = get_current_user_id()
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="No user context found. Please authenticate."
        )
    return user_id


def get_optional_signing_key():
    """Get signing key for capsule signing (placeholder for now)."""
    # TODO: Implement proper key management integration
    # This would typically come from HashiCorp Vault or similar
    return None