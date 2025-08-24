"""
Security and Authorization Module

A.4–A.6 Implementation: OIDC authentication, tenant isolation, and RBAC
for capsule registry operations.
"""

import uuid
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from anumate_oidc import OIDCValidator, TokenPayload
from anumate_tenancy import TenantContext, extract_tenant_id
from anumate_errors import AuthenticationError, AuthorizationError
from .models import CapsuleRole
from .settings import RegistrySettings


class SecurityContext:
    """Security context for a request."""
    
    def __init__(self, actor: str, tenant_id: uuid.UUID, roles: List[CapsuleRole]):
        self.actor = actor  # OIDC subject
        self.tenant_id = tenant_id
        self.roles = roles
    
    def has_role(self, required_role: CapsuleRole) -> bool:
        """Check if context has required role."""
        role_hierarchy = {
            CapsuleRole.ADMIN: 3,
            CapsuleRole.EDITOR: 2, 
            CapsuleRole.VIEWER: 1
        }
        
        max_user_level = max((role_hierarchy.get(role, 0) for role in self.roles), default=0)
        required_level = role_hierarchy.get(required_role, 0)
        
        return max_user_level >= required_level
    
    def can_read(self) -> bool:
        """Check if can read capsules."""
        return self.has_role(CapsuleRole.VIEWER)
    
    def can_write(self) -> bool:
        """Check if can create/modify capsules."""
        return self.has_role(CapsuleRole.EDITOR)
    
    def can_delete(self) -> bool:
        """Check if can delete capsules.""" 
        return self.has_role(CapsuleRole.ADMIN)


class RegistryAuthenticator:
    """OIDC authentication for registry service."""
    
    def __init__(self, settings: RegistrySettings):
        self.settings = settings
        self.oidc_validator = OIDCValidator(
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            jwks_url=settings.computed_jwks_url
        )
        self.bearer_scheme = HTTPBearer()
    
    async def authenticate(self, authorization: HTTPAuthorizationCredentials) -> TokenPayload:
        """Authenticate OIDC bearer token."""
        try:
            if not authorization or authorization.scheme.lower() != "bearer":
                raise AuthenticationError("Bearer token required")
            
            token = authorization.credentials
            payload = await self.oidc_validator.validate_token(token)
            
            return payload
            
        except Exception as e:
            raise AuthenticationError(f"Token validation failed: {e}")
    
    async def extract_tenant_context(self, token_payload: TokenPayload, 
                                   tenant_header: Optional[str] = None) -> TenantContext:
        """Extract tenant context from token and headers."""
        try:
            # Try header first, then token claim
            tenant_id = None
            
            if tenant_header:
                tenant_id = uuid.UUID(tenant_header)
            elif "tenant_id" in token_payload.claims:
                tenant_id = uuid.UUID(token_payload.claims["tenant_id"])
            elif self.settings.default_tenant_id:
                tenant_id = uuid.UUID(self.settings.default_tenant_id)
            else:
                raise AuthenticationError("Tenant ID required but not provided")
            
            return TenantContext(
                tenant_id=tenant_id,
                actor=token_payload.subject,
                claims=token_payload.claims
            )
            
        except ValueError as e:
            raise AuthenticationError(f"Invalid tenant ID format: {e}")


class RegistryAuthorizer:
    """RBAC authorization for registry operations."""
    
    def __init__(self, settings: RegistrySettings):
        self.settings = settings
    
    def extract_roles(self, token_payload: TokenPayload) -> List[CapsuleRole]:
        """Extract roles from token claims."""
        # Check for registry-specific roles
        roles = []
        claims = token_payload.claims
        
        # Look for roles in various claim formats
        role_claims = []
        
        if "anumate_roles" in claims:
            role_claims.extend(claims["anumate_roles"])
        if "roles" in claims:
            role_claims.extend(claims["roles"])
        if "groups" in claims:
            role_claims.extend(claims["groups"])
        
        # Map claim values to registry roles
        for role_claim in role_claims:
            if isinstance(role_claim, str):
                if "registry:admin" in role_claim or "admin" in role_claim.lower():
                    roles.append(CapsuleRole.ADMIN)
                elif "registry:editor" in role_claim or "editor" in role_claim.lower():
                    roles.append(CapsuleRole.EDITOR)
                elif "registry:viewer" in role_claim or "viewer" in role_claim.lower():
                    roles.append(CapsuleRole.VIEWER)
        
        # Default to viewer if no specific roles found
        if not roles:
            roles = [CapsuleRole.VIEWER]
        
        return roles
    
    def check_permission(self, security_ctx: SecurityContext, 
                        operation: str, resource: Optional[str] = None) -> None:
        """Check if security context has permission for operation."""
        
        permission_map = {
            "list_capsules": CapsuleRole.VIEWER,
            "read_capsule": CapsuleRole.VIEWER,
            "read_version": CapsuleRole.VIEWER,
            "create_capsule": CapsuleRole.EDITOR,
            "create_version": CapsuleRole.EDITOR,
            "lint_capsule": CapsuleRole.EDITOR,
            "update_capsule": CapsuleRole.EDITOR,
            "delete_capsule": CapsuleRole.ADMIN,
            "hard_delete": CapsuleRole.ADMIN
        }
        
        required_role = permission_map.get(operation)
        if not required_role:
            raise AuthorizationError(f"Unknown operation: {operation}")
        
        if not security_ctx.has_role(required_role):
            raise AuthorizationError(
                f"Insufficient permissions: {operation} requires {required_role.value}"
            )
    
    def check_resource_access(self, security_ctx: SecurityContext, 
                            resource_owner: str, resource_visibility: str = "private") -> None:
        """Check if context can access a specific resource."""
        
        # Admin can access everything
        if security_ctx.has_role(CapsuleRole.ADMIN):
            return
        
        # Owner can access their own resources
        if security_ctx.actor == resource_owner:
            return
        
        # Public resources are readable by viewers
        if resource_visibility == "public" and security_ctx.can_read():
            return
        
        # Internal resources are readable by editors in same tenant
        if resource_visibility == "internal" and security_ctx.has_role(CapsuleRole.EDITOR):
            return
        
        # Otherwise, access denied
        raise AuthorizationError("Insufficient permissions to access this resource")


class SecurityManager:
    """Integrated security management for registry."""
    
    def __init__(self, settings: RegistrySettings):
        self.settings = settings
        self.authenticator = RegistryAuthenticator(settings)
        self.authorizer = RegistryAuthorizer(settings)
    
    async def create_security_context(
        self,
        authorization: HTTPAuthorizationCredentials,
        tenant_header: Optional[str] = None
    ) -> SecurityContext:
        """Create security context from request authentication."""
        
        # Authenticate token
        token_payload = await self.authenticator.authenticate(authorization)
        
        # Extract tenant context
        tenant_ctx = await self.authenticator.extract_tenant_context(
            token_payload, tenant_header
        )
        
        # Extract roles
        roles = self.authorizer.extract_roles(token_payload)
        
        return SecurityContext(
            actor=token_payload.subject,
            tenant_id=tenant_ctx.tenant_id,
            roles=roles
        )
    
    def require_permission(self, security_ctx: SecurityContext, 
                          operation: str, resource: Optional[str] = None) -> None:
        """Require permission for operation (raises on failure)."""
        self.authorizer.check_permission(security_ctx, operation, resource)
    
    def require_resource_access(self, security_ctx: SecurityContext,
                              resource_owner: str, resource_visibility: str = "private") -> None:
        """Require access to specific resource (raises on failure)."""
        self.authorizer.check_resource_access(security_ctx, resource_owner, resource_visibility)


def create_security_manager(settings: RegistrySettings) -> SecurityManager:
    """Factory function to create configured security manager."""
    return SecurityManager(settings)


def security_error_handler(exc: Exception) -> HTTPException:
    """Convert security exceptions to HTTP errors."""
    if isinstance(exc, AuthenticationError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "type": "urn:ietf:rfc:7807:authentication-required",
                "title": "Authentication Required", 
                "status": 401,
                "detail": str(exc)
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    elif isinstance(exc, AuthorizationError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "type": "urn:ietf:rfc:7807:insufficient-permissions",
                "title": "Insufficient Permissions",
                "status": 403, 
                "detail": str(exc)
            }
        )
    else:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "urn:ietf:rfc:7807:internal-server-error",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "An unexpected security error occurred"
            }
        )
