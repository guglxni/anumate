"""
Capability Middleware
===================

Middleware for enforcing capability-based access control on API endpoints.
Integrates with the capability checker and violation logger for comprehensive security.
"""

import logging
import time
import uuid
from typing import Dict, Any, Optional, List, Callable
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from anumate_capability_tokens import verify_capability_token
from .capability_checker import CapabilityChecker, CapabilityCheckRequest
from .violation_logger import ViolationLogger, ViolationContext, ViolationType
from .usage_tracker import UsageTracker, UsageContext

logger = logging.getLogger(__name__)

# Security scheme for bearer tokens
security = HTTPBearer(auto_error=False)


class CapabilityMiddleware:
    """
    Middleware for capability-based access control.
    
    Features:
    - Token validation and verification
    - Capability checking against tool allow-lists
    - Violation logging and alerting
    - Usage tracking and analytics
    - Performance monitoring
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.capability_checker = CapabilityChecker(db)
        self.violation_logger = ViolationLogger(db)
        self.usage_tracker = UsageTracker(db)
    
    async def enforce_capability(
        self,
        request: Request,
        required_capabilities: List[str],
        tool: str,
        action: Optional[str] = None,
        tenant_id: Optional[str] = None,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
    ) -> Dict[str, Any]:
        """
        Enforce capability requirements for an endpoint.
        
        Args:
            request: FastAPI request object
            required_capabilities: List of required capabilities
            tool: Tool being accessed
            action: Specific action being performed
            tenant_id: Tenant ID (if not in token)
            credentials: Bearer token credentials
            
        Returns:
            Token payload and validation info
            
        Raises:
            HTTPException: If access is denied
        """
        start_time = time.time()
        
        try:
            # Extract token from authorization header
            if not credentials or not credentials.credentials:
                await self._log_violation(
                    tenant_id or "unknown",
                    ViolationType.INVALID_TOKEN,
                    f"Access to {tool}",
                    request,
                    "No authorization token provided"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authorization token required"
                )
            
            token = credentials.credentials
            
            # Extract tenant ID from headers if not provided
            if not tenant_id:
                tenant_id = request.headers.get("X-Tenant-Id")
                if not tenant_id:
                    await self._log_violation(
                        "unknown",
                        ViolationType.MALFORMED_REQUEST,
                        f"Access to {tool}",
                        request,
                        "No tenant ID provided"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="X-Tenant-Id header required"
                    )
            
            # Verify token
            verification_result = verify_capability_token(token, tenant_id)
            
            if not verification_result.get("valid", False):
                await self._log_violation(
                    tenant_id,
                    ViolationType.INVALID_TOKEN,
                    f"Access to {tool}",
                    request,
                    verification_result.get("error", "Token verification failed")
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token"
                )
            
            token_payload = verification_result["payload"]
            token_capabilities = token_payload.get("capabilities", [])
            token_id = token_payload.get("jti")
            subject = token_payload.get("sub")
            
            # Check if any required capability is present in token
            has_required_capability = False
            for required_cap in required_capabilities:
                if required_cap in token_capabilities:
                    has_required_capability = True
                    break
            
            if not has_required_capability:
                await self._log_violation(
                    tenant_id,
                    ViolationType.INSUFFICIENT_CAPABILITY,
                    f"Access to {tool}",
                    request,
                    f"Required capabilities: {required_capabilities}, provided: {token_capabilities}",
                    token_id,
                    subject
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient capabilities. Required: {required_capabilities}"
                )
            
            # Check tool allow-list
            capability_request = CapabilityCheckRequest(
                capabilities=token_capabilities,
                tool=tool,
                action=action,
                tenant_id=tenant_id,
                metadata={
                    "endpoint": str(request.url.path),
                    "method": request.method,
                    "token_id": token_id
                }
            )
            
            check_result = await self.capability_checker.check_capability(capability_request)
            
            if not check_result.allowed:
                await self._log_violation(
                    tenant_id,
                    ViolationType.TOOL_BLOCKED,
                    f"Access to {tool}" + (f".{action}" if action else ""),
                    request,
                    check_result.violation_reason,
                    token_id,
                    subject
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access to tool '{tool}' denied by capability rules"
                )
            
            # Track successful usage
            response_time_ms = int((time.time() - start_time) * 1000)
            
            await self.usage_tracker.track_token_usage(
                tenant_id=tenant_id,
                token_id=token_id,
                action_performed=f"{tool}" + (f".{action}" if action else ""),
                capabilities_used=token_capabilities,
                success=True,
                context=UsageContext(
                    endpoint=str(request.url.path),
                    http_method=request.method,
                    client_ip=self._get_client_ip(request),
                    user_agent=request.headers.get("User-Agent"),
                    response_time_ms=response_time_ms,
                    metadata={
                        "matched_rules": len(check_result.matched_rules),
                        "required_capabilities": required_capabilities
                    }
                )
            )
            
            logger.info(
                f"Capability check passed: {tool}",
                extra={
                    "tenant_id": tenant_id,
                    "token_id": token_id,
                    "subject": subject,
                    "tool": tool,
                    "action": action,
                    "capabilities": token_capabilities,
                    "response_time_ms": response_time_ms
                }
            )
            
            return {
                "token_payload": token_payload,
                "token_id": token_id,
                "subject": subject,
                "tenant_id": tenant_id,
                "capabilities": token_capabilities,
                "matched_rules": check_result.matched_rules
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Capability enforcement failed: {e}", exc_info=True)
            
            await self._log_violation(
                tenant_id or "unknown",
                ViolationType.MALFORMED_REQUEST,
                f"Access to {tool}",
                request,
                f"Internal error: {str(e)}"
            )
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal error during capability check"
            )
    
    async def _log_violation(
        self,
        tenant_id: str,
        violation_type: str,
        attempted_action: str,
        request: Request,
        reason: str,
        token_id: Optional[str] = None,
        subject: Optional[str] = None
    ) -> None:
        """Log a capability violation."""
        try:
            context = ViolationContext(
                endpoint=str(request.url.path),
                http_method=request.method,
                client_ip=self._get_client_ip(request),
                user_agent=request.headers.get("User-Agent"),
                token_id=token_id,
                subject=subject,
                metadata={
                    "reason": reason,
                    "query_params": dict(request.query_params),
                    "path_params": getattr(request, "path_params", {})
                }
            )
            
            await self.violation_logger.log_capability_violation(
                tenant_id=tenant_id,
                violation_type=violation_type,
                attempted_action=attempted_action,
                context=context
            )
            
        except Exception as e:
            logger.error(f"Failed to log violation: {e}")
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to client host
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"


def require_capabilities(
    capabilities: List[str],
    tool: str,
    action: Optional[str] = None
) -> Callable:
    """
    Decorator for endpoints that require specific capabilities.
    
    Args:
        capabilities: List of required capabilities
        tool: Tool being accessed
        action: Specific action being performed
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request, db, and credentials from function parameters
            request = None
            db = None
            credentials = None
            
            # Find required parameters
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                elif isinstance(arg, AsyncSession):
                    db = arg
            
            for key, value in kwargs.items():
                if key == "request" and isinstance(value, Request):
                    request = value
                elif key == "db" and isinstance(value, AsyncSession):
                    db = value
                elif key == "credentials" and isinstance(value, HTTPAuthorizationCredentials):
                    credentials = value
            
            if not request or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Missing required parameters for capability check"
                )
            
            # Create middleware and enforce capabilities
            middleware = CapabilityMiddleware(db)
            
            capability_info = await middleware.enforce_capability(
                request=request,
                required_capabilities=capabilities,
                tool=tool,
                action=action,
                credentials=credentials
            )
            
            # Add capability info to kwargs
            kwargs["capability_info"] = capability_info
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def create_capability_dependency(
    capabilities: List[str],
    tool: str,
    action: Optional[str] = None
) -> Callable:
    """
    Create a FastAPI dependency for capability checking.
    
    Args:
        capabilities: List of required capabilities
        tool: Tool being accessed
        action: Specific action being performed
        
    Returns:
        FastAPI dependency function
    """
    async def capability_dependency(
        request: Request,
        db: AsyncSession = Depends(lambda: None),  # This should be replaced with actual DB dependency
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
    ) -> Dict[str, Any]:
        """Dependency function for capability checking."""
        middleware = CapabilityMiddleware(db)
        
        return await middleware.enforce_capability(
            request=request,
            required_capabilities=capabilities,
            tool=tool,
            action=action,
            credentials=credentials
        )
    
    return capability_dependency
