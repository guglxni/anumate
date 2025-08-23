from __future__ import annotations

import time
from typing import Any, Dict, Optional, List, Callable, Awaitable
from uuid import UUID
import logging

import jwt
import requests
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

try:
    from anumate_crypto import Ed25519
except ImportError:
    Ed25519 = None

logger = logging.getLogger(__name__)


class OIDCVerifier:
    def __init__(
        self,
        issuer: str,
        audience: str,
        dev_mode: bool = False,
        dev_key: Optional[Ed25519.Ed25519PublicKey] = None,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.dev_mode = dev_mode
        self.dev_key = dev_key
        self.jwks_cache: Dict[str, Any] = {}

    def verify_token(self, token: str) -> Dict[str, Any]:
        if self.dev_mode:
            if self.dev_key is None:
                raise ValueError("Dev key not configured")
            return jwt.decode(token, self.dev_key, algorithms=["EdDSA"])

        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if kid is None:
            raise ValueError("kid not found in token header")

        public_key = self._get_public_key(kid)
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=self.audience,
            issuer=self.issuer,
        )

    def _get_public_key(self, kid: str) -> Any:
        if kid in self.jwks_cache and self.jwks_cache[kid]["expires_at"] > time.time():
            return self.jwks_cache[kid]["key"]

        jwks_uri = f"{self.issuer}/.well-known/jwks.json"
        response = requests.get(jwks_uri)
        response.raise_for_status()
        jwks = response.json()

        for key in jwks["keys"]:
            if key["kid"] == kid:
                public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                self.jwks_cache[kid] = {
                    "key": public_key,
                    "expires_at": time.time() + 3600,  # Cache for 1 hour
                }
                return public_key

        raise ValueError(f"Public key with kid {kid} not found in JWKS")


class AuthenticationError(Exception):
    """Authentication related errors."""
    pass


class AuthorizationError(Exception):
    """Authorization related errors."""
    pass


class User:
    """Represents an authenticated user."""
    
    def __init__(self, user_id: str, tenant_id: UUID, email: str, roles: List[str], claims: Dict[str, Any]):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.email = email
        self.roles = roles
        self.claims = claims
    
    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles
    
    def has_any_role(self, roles: List[str]) -> bool:
        """Check if user has any of the specified roles."""
        return any(role in self.roles for role in roles)
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission (simplified)."""
        # This would typically check against a more complex permission system
        return permission in self.claims.get("permissions", [])


class AuthService:
    """Authentication and authorization service."""
    
    def __init__(self, oidc_verifier: OIDCVerifier):
        self.oidc_verifier = oidc_verifier
        self.security = HTTPBearer()
    
    async def get_current_user(self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> User:
        """Extract and validate user from JWT token."""
        try:
            token = credentials.credentials
            claims = self.oidc_verifier.verify_token(token)
            
            # Extract user information from claims
            user_id = claims.get("sub")
            tenant_id_str = claims.get("tenant_id")
            email = claims.get("email")
            roles = claims.get("roles", [])
            
            if not user_id:
                raise AuthenticationError("Missing user ID in token")
            
            if not tenant_id_str:
                raise AuthenticationError("Missing tenant ID in token")
            
            try:
                tenant_id = UUID(tenant_id_str)
            except ValueError:
                raise AuthenticationError("Invalid tenant ID format")
            
            return User(
                user_id=user_id,
                tenant_id=tenant_id,
                email=email or "",
                roles=roles,
                claims=claims
            )
            
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        except AuthenticationError as e:
            logger.warning(f"Authentication error: {e}")
            raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected authentication error: {e}")
            raise HTTPException(status_code=500, detail="Authentication service error")
    
    def require_roles(self, required_roles: List[str]) -> Callable:
        """Decorator to require specific roles."""
        def decorator(func: Callable) -> Callable:
            async def wrapper(*args, **kwargs):
                # Get user from kwargs (assumes get_current_user is a dependency)
                user = None
                for arg in args:
                    if isinstance(arg, User):
                        user = arg
                        break
                
                if not user:
                    for value in kwargs.values():
                        if isinstance(value, User):
                            user = value
                            break
                
                if not user:
                    raise HTTPException(status_code=401, detail="Authentication required")
                
                if not user.has_any_role(required_roles):
                    logger.warning(f"User {user.user_id} lacks required roles: {required_roles}")
                    raise HTTPException(status_code=403, detail="Insufficient permissions")
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def require_permission(self, permission: str) -> Callable:
        """Decorator to require specific permission."""
        def decorator(func: Callable) -> Callable:
            async def wrapper(*args, **kwargs):
                # Get user from kwargs (assumes get_current_user is a dependency)
                user = None
                for arg in args:
                    if isinstance(arg, User):
                        user = arg
                        break
                
                if not user:
                    for value in kwargs.values():
                        if isinstance(value, User):
                            user = value
                            break
                
                if not user:
                    raise HTTPException(status_code=401, detail="Authentication required")
                
                if not user.has_permission(permission):
                    logger.warning(f"User {user.user_id} lacks permission: {permission}")
                    raise HTTPException(status_code=403, detail="Insufficient permissions")
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator


class AuthMiddleware:
    """FastAPI middleware for authentication."""
    
    def __init__(self, app: Callable[[Request], Awaitable], auth_service: AuthService, excluded_paths: Optional[List[str]] = None):
        self.app = app
        self.auth_service = auth_service
        self.excluded_paths = excluded_paths or ["/health", "/metrics", "/docs", "/openapi.json"]
    
    async def __call__(self, request: Request) -> Any:
        """Process request with authentication."""
        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            return await self.app(request)
        
        # Extract and validate token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        
        try:
            from fastapi.security import HTTPAuthorizationCredentials
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=auth_header.split(" ", 1)[1]
            )
            
            user = await self.auth_service.get_current_user(credentials)
            
            # Set user in request state for downstream use
            request.state.user = user
            
            # Set tenant context
            try:
                from anumate_infrastructure import set_current_tenant_id
                set_current_tenant_id(user.tenant_id)
            except ImportError:
                logger.warning("Could not set tenant context - anumate_infrastructure not available")
            
            return await self.app(request)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication middleware error: {e}")
            raise HTTPException(status_code=500, detail="Authentication service error")
