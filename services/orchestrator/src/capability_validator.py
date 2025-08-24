"""Capability token validation for execution hooks."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx

try:
    from anumate_core_config import settings
except ImportError:
    # Fallback settings for development
    class MockSettings:
        ANUMATE_ENV = "development"
    settings = MockSettings()

# Import from src.models to avoid conflict with api.models
import sys
import os
src_path = os.path.dirname(__file__)
sys.path.insert(0, src_path)
from models import CapabilityValidation

logger = logging.getLogger(__name__)


class CapabilityValidationError(Exception):
    """Capability validation error."""
    pass


class CapabilityValidator:
    """Validates capability tokens for plan execution."""
    
    def __init__(self, captokens_base_url: Optional[str] = None):
        """Initialize capability validator.
        
        Args:
            captokens_base_url: CapTokens service base URL
        """
        # For now, we'll use a placeholder URL since CapTokens service isn't implemented yet
        self.captokens_base_url = captokens_base_url or "http://localhost:8003"
        self.timeout = 10.0
    
    async def validate_execution_capabilities(
        self,
        tenant_id: UUID,
        required_capabilities: List[str],
        token: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> CapabilityValidation:
        """Validate capabilities for plan execution.
        
        Args:
            tenant_id: Tenant ID
            required_capabilities: List of required capabilities
            token: Capability token to validate
            user_id: User ID for capability lookup
            
        Returns:
            Capability validation result
        """
        if not required_capabilities:
            # No capabilities required, validation passes
            return CapabilityValidation(
                valid=True,
                capabilities=[]
            )
        
        try:
            # For now, implement a mock validation since CapTokens service isn't ready
            return await self._mock_validate_capabilities(
                tenant_id=tenant_id,
                required_capabilities=required_capabilities,
                token=token,
                user_id=user_id,
            )
            
        except Exception as e:
            logger.error(f"Capability validation failed: {e}")
            return CapabilityValidation(
                valid=False,
                error_message=f"Capability validation error: {e}"
            )
    
    async def _mock_validate_capabilities(
        self,
        tenant_id: UUID,
        required_capabilities: List[str],
        token: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> CapabilityValidation:
        """Mock capability validation for development.
        
        This will be replaced with actual CapTokens service integration.
        """
        # Mock validation logic - in development, allow all capabilities
        if settings.ANUMATE_ENV == "development":
            logger.info(f"Mock validation: allowing all capabilities for tenant {tenant_id}")
            return CapabilityValidation(
                valid=True,
                token_id=f"mock-token-{tenant_id}",
                capabilities=required_capabilities,
                expires_at=datetime.now(timezone.utc).replace(hour=23, minute=59, second=59),
            )
        
        # In production, be more strict
        # For now, validate against a basic allow-list
        allowed_capabilities = {
            "execute_plan",
            "read_data",
            "write_data",
            "send_notification",
            "call_webhook",
        }
        
        valid_capabilities = []
        invalid_capabilities = []
        
        for capability in required_capabilities:
            if capability in allowed_capabilities:
                valid_capabilities.append(capability)
            else:
                invalid_capabilities.append(capability)
        
        if invalid_capabilities:
            return CapabilityValidation(
                valid=False,
                error_message=f"Invalid capabilities: {', '.join(invalid_capabilities)}"
            )
        
        return CapabilityValidation(
            valid=True,
            token_id=f"mock-token-{tenant_id}",
            capabilities=valid_capabilities,
            expires_at=datetime.now(timezone.utc).replace(hour=23, minute=59, second=59),
        )
    
    async def validate_tool_allowlist(
        self,
        tenant_id: UUID,
        allowed_tools: List[str],
        requested_tool: str,
    ) -> bool:
        """Validate that a tool is in the allowed tools list.
        
        Args:
            tenant_id: Tenant ID
            allowed_tools: List of allowed tools from security context
            requested_tool: Tool being requested for execution
            
        Returns:
            True if tool is allowed, False otherwise
        """
        if not allowed_tools:
            # No restrictions, allow all tools
            logger.warning(f"No tool allowlist defined for tenant {tenant_id}")
            return True
        
        is_allowed = requested_tool in allowed_tools
        
        if not is_allowed:
            logger.warning(
                f"Tool '{requested_tool}' not in allowlist for tenant {tenant_id}. "
                f"Allowed tools: {allowed_tools}"
            )
        
        return is_allowed
    
    async def check_capability_expiry(
        self,
        validation: CapabilityValidation,
        buffer_minutes: int = 5,
    ) -> bool:
        """Check if capability token is close to expiry.
        
        Args:
            validation: Capability validation result
            buffer_minutes: Minutes before expiry to consider expired
            
        Returns:
            True if token is expired or close to expiry
        """
        if not validation.expires_at:
            # No expiry time, assume valid
            return False
        
        now = datetime.now(timezone.utc)
        buffer_time = now.replace(minute=now.minute + buffer_minutes)
        
        return validation.expires_at <= buffer_time