"""
Capability Tokens Service API

A.22 Implementation: FastAPI service for Ed25519/JWT capability tokens
Provides REST endpoints for token management and verification.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
import asyncio

from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator

# Database imports - optional for development
try:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    async_sessionmaker = None
    AsyncSession = None

from cryptography.hazmat.primitives.asymmetric import ed25519

# Import Anumate packages
try:
    from anumate_logging import get_logger
    from anumate_errors import AnumateError, ErrorCode
except ImportError as e:
    # Fallback to standard logging if packages aren't available
    import logging
    get_logger = logging.getLogger
    
    class AnumateError(Exception):
        pass
        
    class ErrorCode:
        INVALID_INPUT = "INVALID_INPUT"
        UNAUTHORIZED = "UNAUTHORIZED"
        INTERNAL_ERROR = "INTERNAL_ERROR"
        NOT_FOUND = "NOT_FOUND"

# Import Anumate capability tokens
try:
    from anumate_capability_tokens import (
        issue_capability_token,
        verify_capability_token, 
        check_capability,
        CapabilityToken,
        InMemoryReplayGuard
    )
    CAPABILITY_TOKENS_AVAILABLE = True
except ImportError:
    CAPABILITY_TOKENS_AVAILABLE = False
    InMemoryReplayGuard = None

# Import token service - optional for development  
try:
    from token_service import TokenService, TokenRecord, TokenUsageAudit, Base, TokenCleanupService
    TOKEN_SERVICE_AVAILABLE = True
except ImportError:
    TOKEN_SERVICE_AVAILABLE = False
    TokenService = None
    Base = None

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer()

# Global service instance
token_service: Optional[TokenService] = None
cleanup_service = None  # TokenCleanupService when database available
db_sessionmaker: Optional[async_sessionmaker] = None


class TokenIssueRequest(BaseModel):
    """Request to issue a new capability token."""
    subject: str = Field(..., description="Subject (user/service) identifier")
    capabilities: List[str] = Field(..., description="List of capability strings", min_items=1)
    ttl_seconds: int = Field(default=300, description="TTL in seconds (max 300)", le=300, ge=1)
    
    @validator('capabilities')
    def validate_capabilities(cls, v):
        if not v:
            raise ValueError("At least one capability must be specified")
        return v


class TokenIssueResponse(BaseModel):
    """Response from token issuance."""
    token: str = Field(..., description="JWT capability token")
    token_id: str = Field(..., description="Unique token identifier")
    subject: str = Field(..., description="Token subject")
    capabilities: List[str] = Field(..., description="Token capabilities")
    expires_at: str = Field(..., description="Token expiration time (ISO 8601)")
    

class TokenVerifyRequest(BaseModel):
    """Request to verify a token."""
    token: str = Field(..., description="JWT token to verify")


class CapabilityCheckRequest(BaseModel):
    """Request to check token capability."""
    token: str = Field(..., description="JWT token to check")
    capability: str = Field(..., description="Required capability")


class TokenVerifyResponse(BaseModel):
    """Response from token verification."""
    valid: bool = Field(..., description="Whether token is valid")
    payload: Optional[Dict[str, Any]] = Field(None, description="Token payload if valid")
    error: Optional[str] = Field(None, description="Error message if invalid")


class CapabilityCheckResponse(BaseModel):
    """Response from capability check."""
    has_capability: bool = Field(..., description="Whether token has the capability")
    payload: Optional[Dict[str, Any]] = Field(None, description="Token payload if valid")


class TokenRevokeRequest(BaseModel):
    """Request to revoke a token."""
    token_id: str = Field(..., description="Token ID to revoke")


class TokenRefreshRequest(BaseModel):
    """Request to refresh a token."""
    token: str = Field(..., description="JWT token to refresh")
    extend_ttl: Optional[int] = Field(None, description="Extended TTL in seconds (max 300)", le=300, ge=1)


class TokenRefreshResponse(BaseModel):
    """Response from token refresh."""
    token: str = Field(..., description="New JWT capability token")
    token_id: str = Field(..., description="New token identifier")
    old_token_id: str = Field(..., description="Previous token identifier")
    subject: str = Field(..., description="Token subject")
    capabilities: List[str] = Field(..., description="Token capabilities")
    expires_at: str = Field(..., description="Token expiration time (ISO 8601)")


class AuditResponse(BaseModel):
    """Audit trail response."""
    records: List[Dict[str, Any]] = Field(..., description="Audit records")
    total: int = Field(..., description="Total number of records")


# Database dependency
async def get_db_session() -> AsyncSession:
    """Get database session."""
    if not db_sessionmaker:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    async with db_sessionmaker() as session:
        try:
            yield session
        finally:
            await session.close()


# Tenant extraction from headers
async def get_tenant_id(request: Request) -> str:
    """Extract tenant ID from request headers."""
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    return tenant_id


# Service dependency  
async def get_token_service(db_session: AsyncSession = Depends(get_db_session)) -> TokenService:
    """Get token service instance."""
    global token_service
    if not token_service:
        raise HTTPException(status_code=500, detail="Token service not initialized")
    
    # Create new service instance with this session
    return TokenService(
        private_key=token_service.private_key,
        public_key=token_service.public_key,
        db_session=db_session,
        replay_guard=token_service.replay_guard
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global token_service, cleanup_service, db_sessionmaker
    
    # Startup
    logger.info("Starting Capability Tokens Service")
    
    # Initialize database
    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/anumate")
    engine = create_async_engine(database_url, echo=bool(os.getenv("SQL_DEBUG")))
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    db_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    
    # Load Ed25519 keys
    private_key_pem = os.getenv("ED25519_PRIVATE_KEY")
    public_key_pem = os.getenv("ED25519_PUBLIC_KEY")
    
    if not private_key_pem or not public_key_pem:
        # Generate new keys for development
        logger.warning("No Ed25519 keys provided, generating new keys for development")
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        
        # Export keys for logging
        from cryptography.hazmat.primitives import serialization
        private_key_pem_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_key_pem_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        logger.info("Generated Ed25519 keys - store these securely for production:")
        logger.info(f"Private Key:\n{private_key_pem_bytes.decode()}")
        logger.info(f"Public Key:\n{public_key_pem_bytes.decode()}")
    else:
        from cryptography.hazmat.primitives import serialization
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None
        )
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode()
        )
    
    # Initialize token service
    async with db_sessionmaker() as session:
        token_service = TokenService(
            private_key=private_key,
            public_key=public_key,
            db_session=session
        )
    
    # Start cleanup service
    cleanup_service = TokenCleanupService(token_service)
    cleanup_task = asyncio.create_task(cleanup_service.start())
    
    logger.info("Capability Tokens Service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Capability Tokens Service")
    
    if cleanup_service:
        cleanup_service.stop()
    
    await engine.dispose()
    logger.info("Capability Tokens Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Anumate Capability Tokens Service",
    description="A.22 Implementation: Ed25519/JWT capability tokens with ≤5min expiry",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "captokens", "version": "1.0.0"}


@app.post("/v1/captokens", response_model=TokenIssueResponse)
async def issue_token(
    request: TokenIssueRequest,
    tenant_id: str = Depends(get_tenant_id),
    service: TokenService = Depends(get_token_service)
) -> TokenIssueResponse:
    """
    Issue a new capability token.
    
    A.22 Implementation: Creates Ed25519/JWT capability tokens with ≤5min expiry.
    """
    try:
        capability_token = await service.issue_token(
            tenant_id=tenant_id,
            subject=request.subject,
            capabilities=request.capabilities,
            ttl_seconds=request.ttl_seconds,
            created_by="api"  # Could be extracted from auth context
        )
        
        return TokenIssueResponse(
            token=capability_token.token,
            token_id=capability_token.token_id,
            subject=capability_token.subject,
            capabilities=capability_token.capabilities,
            expires_at=capability_token.expires_at.isoformat()
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error issuing token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/v1/captokens/verify", response_model=TokenVerifyResponse)
async def verify_token(
    request: TokenVerifyRequest,
    client_request: Request,
    tenant_id: str = Depends(get_tenant_id),
    service: TokenService = Depends(get_token_service)
) -> TokenVerifyResponse:
    """
    Verify a capability token.
    
    A.22 Implementation: Validates Ed25519 signature and checks expiry/revocation.
    """
    try:
        client_ip = client_request.client.host
        user_agent = client_request.headers.get("user-agent")
        
        payload = await service.verify_token(
            token=request.token,
            client_ip=client_ip,
            user_agent=user_agent
        )
        
        return TokenVerifyResponse(
            valid=True,
            payload=payload
        )
        
    except ValueError as e:
        return TokenVerifyResponse(
            valid=False,
            error=str(e)
        )
    except Exception as e:
        logger.error(f"Error verifying token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/v1/captokens/check", response_model=CapabilityCheckResponse)
async def check_capability(
    request: CapabilityCheckRequest,
    client_request: Request,
    tenant_id: str = Depends(get_tenant_id),
    service: TokenService = Depends(get_token_service)
) -> CapabilityCheckResponse:
    """
    Check if token has a specific capability.
    
    A.22 Implementation: Capability-based access control validation.
    """
    try:
        client_ip = client_request.client.host
        user_agent = client_request.headers.get("user-agent")
        
        has_capability, payload = await service.check_capability(
            token=request.token,
            required_capability=request.capability,
            client_ip=client_ip,
            user_agent=user_agent
        )
        
        return CapabilityCheckResponse(
            has_capability=has_capability,
            payload=payload
        )
        
    except Exception as e:
        logger.error(f"Error checking capability: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/v1/captokens/revoke")
async def revoke_token(
    request: TokenRevokeRequest,
    tenant_id: str = Depends(get_tenant_id),
    service: TokenService = Depends(get_token_service)
):
    """
    Revoke a capability token.
    
    Marks the token as revoked in the database for immediate invalidation.
    """
    try:
        await service.revoke_token(
            token_id=request.token_id,
            tenant_id=tenant_id,
            revoked_by="api"  # Could be extracted from auth context
        )
        
        return {"message": "Token revoked successfully", "token_id": request.token_id}
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error revoking token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/v1/captokens/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    request: TokenRefreshRequest,
    tenant_id: str = Depends(get_tenant_id),
    service: TokenService = Depends(get_token_service)
) -> TokenRefreshResponse:
    """
    Refresh a capability token before expiry.
    
    A.23 Implementation: Extends token lifetime while maintaining same capabilities.
    """
    try:
        # Extract old token ID for response
        import jwt
        old_payload = jwt.decode(request.token, options={"verify_signature": False})
        old_token_id = old_payload.get("jti", "unknown")
        
        # Refresh the token
        new_token = await service.refresh_token(
            token=request.token,
            tenant_id=tenant_id,
            extend_ttl=request.extend_ttl,
            refreshed_by="api"  # Could be extracted from auth context
        )
        
        return TokenRefreshResponse(
            token=new_token.token,
            token_id=new_token.token_id,
            old_token_id=old_token_id,
            subject=new_token.subject,
            capabilities=new_token.capabilities,
            expires_at=new_token.expires_at.isoformat()
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/v1/captokens/audit", response_model=AuditResponse)
async def get_audit_trail(
    tenant_id: str = Depends(get_tenant_id),
    token_id: Optional[str] = None,
    limit: int = 100,
    service: TokenService = Depends(get_token_service)
) -> AuditResponse:
    """
    Get token usage audit trail.
    
    Provides audit trail for compliance and security monitoring.
    """
    try:
        if limit > 1000:
            limit = 1000  # Max limit for performance
            
        records = await service.get_token_audit_trail(
            tenant_id=tenant_id,
            token_id=token_id,
            limit=limit
        )
        
        return AuditResponse(
            records=records,
            total=len(records)
        )
        
    except Exception as e:
        logger.error(f"Error fetching audit trail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/v1/captokens/stats")
async def get_token_stats(
    tenant_id: str = Depends(get_tenant_id),
    service: TokenService = Depends(get_token_service)
):
    """
    Get token statistics for monitoring.
    """
    try:
        # This would be implemented with proper database queries
        # For now, return basic stats
        return {
            "tenant_id": tenant_id,
            "active_tokens": 0,  # Would query database
            "expired_tokens": 0,  # Would query database
            "revoked_tokens": 0,  # Would query database
            "total_issued": 0     # Would query database
        }
        
    except Exception as e:
        logger.error(f"Error fetching token stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8083"))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=os.getenv("DEVELOPMENT", "false").lower() == "true",
        log_level="info"
    )
