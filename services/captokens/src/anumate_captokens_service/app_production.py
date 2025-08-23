"""
Anumate CapTokens Service - Production FastAPI Application
==========================================================

Production-grade FastAPI application for Ed25519/JWT capability token management.
"""

import os
import uuid
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Depends, Header, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_async_session, init_database, close_database, check_database_health
from .database_services import (
    DatabaseTokenService, 
    AuditService, 
    CleanupService, 
    ReplayProtectionService
)
from .models import CapabilityToken, ToolAllowList, CapabilityViolation, TokenUsageTracking
from .capability_checker import CapabilityChecker
from .violation_logger import ViolationLogger
from .usage_tracker import UsageTracker
from anumate_capability_tokens import issue_capability_token, verify_capability_token, check_capability

# Import logging with fallback  
try:
    from anumate_logging import get_logger
except ImportError:
    import logging
    def get_logger(name: str):
        return logging.getLogger(name)

# Import errors with fallback
try:
    from anumate_errors import ErrorCode
except ImportError:
    class ErrorCode:
        INVALID_INPUT = "INVALID_INPUT"
        UNAUTHORIZED = "UNAUTHORIZED"
        INTERNAL_ERROR = "INTERNAL_ERROR"
        NOT_FOUND = "NOT_FOUND"

logger = get_logger(__name__)


# Pydantic Models for Request/Response
class TokenIssueRequest(BaseModel):
    """Request model for issuing new capability tokens."""
    subject: str = Field(..., description="Subject for the token", min_length=1, max_length=255)
    capabilities: List[str] = Field(..., description="List of capabilities", min_items=1)
    ttl_seconds: int = Field(default=300, description="Time to live in seconds", ge=1, le=300)


class TokenIssueResponse(BaseModel):
    """Response model for token issuance."""
    token: str = Field(..., description="The JWT token")
    token_id: str = Field(..., description="Unique token identifier")
    subject: str = Field(..., description="Token subject")
    capabilities: List[str] = Field(..., description="Token capabilities")
    expires_at: datetime = Field(..., description="Token expiration time")
    issued_at: datetime = Field(..., description="Token issuance time")


class TokenVerifyRequest(BaseModel):
    """Request model for token verification."""
    token: str = Field(..., description="JWT token to verify")


class TokenVerifyResponse(BaseModel):
    """Response model for token verification."""
    valid: bool = Field(..., description="Whether the token is valid")
    payload: Optional[Dict[str, Any]] = Field(None, description="Token payload if valid")
    error: Optional[str] = Field(None, description="Error message if invalid")


class TokenRefreshRequest(BaseModel):
    """Request model for token refresh."""
    token: str = Field(..., description="Current JWT token")
    extend_ttl: int = Field(default=300, description="Extended TTL in seconds", ge=1, le=300)


class TokenRefreshResponse(BaseModel):
    """Response model for token refresh."""
    token: str = Field(..., description="New JWT token")
    token_id: str = Field(..., description="New token identifier")
    old_token_id: str = Field(..., description="Previous token identifier")
    subject: str = Field(..., description="Token subject")
    capabilities: List[str] = Field(..., description="Token capabilities")
    expires_at: datetime = Field(..., description="New expiration time")


class CapabilityCheckRequest(BaseModel):
    """Request model for capability checking."""
    token: str = Field(..., description="JWT token to check")
    capability: str = Field(..., description="Capability to check")


class CapabilityCheckResponse(BaseModel):
    """Response model for capability checking."""
    has_capability: bool = Field(..., description="Whether the token has the capability")
    token_valid: bool = Field(..., description="Whether the token is valid")
    payload: Optional[Dict[str, Any]] = Field(None, description="Token payload if valid")


class AuditTrailResponse(BaseModel):
    """Response model for audit trail."""
    audit_records: List[Dict[str, Any]] = Field(..., description="List of audit records")
    total_count: int = Field(..., description="Total number of records")
    limit: int = Field(..., description="Limit used for pagination")
    offset: int = Field(..., description="Offset used for pagination")


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Service version")
    uptime_seconds: int = Field(..., description="Service uptime in seconds")
    database: Dict[str, Any] = Field(..., description="Database health status")


# A.24 - Capability enforcement models
class ToolAllowListRequest(BaseModel):
    """Request model for creating tool allow-list rules."""
    capability_name: str = Field(..., description="Capability name")
    tool_pattern: str = Field(..., description="Tool pattern (exact, regex, or glob)")
    action_pattern: Optional[str] = Field(None, description="Action pattern (optional)")
    rule_type: str = Field("allow", description="Rule type (allow/deny)")
    pattern_type: str = Field("exact", description="Pattern type (exact/regex/glob)")
    priority: int = Field(100, description="Rule priority (lower = higher priority)")
    description: Optional[str] = Field(None, description="Rule description")
    is_active: bool = Field(True, description="Whether rule is active")


class ToolAllowListResponse(BaseModel):
    """Response model for tool allow-list rules."""
    rule_id: str = Field(..., description="Rule ID")
    tenant_id: str = Field(..., description="Tenant ID")
    capability_name: str = Field(..., description="Capability name")
    tool_pattern: str = Field(..., description="Tool pattern")
    action_pattern: Optional[str] = Field(None, description="Action pattern")
    rule_type: str = Field(..., description="Rule type")
    pattern_type: str = Field(..., description="Pattern type")
    priority: int = Field(..., description="Rule priority")
    description: Optional[str] = Field(None, description="Rule description")
    is_active: bool = Field(..., description="Whether rule is active")
    created_at: datetime = Field(..., description="Creation timestamp")


class ViolationResponse(BaseModel):
    """Response model for capability violations."""
    violation_id: str = Field(..., description="Violation ID")
    tenant_id: str = Field(..., description="Tenant ID")
    token_id: Optional[str] = Field(None, description="Token ID")
    violation_type: str = Field(..., description="Violation type")
    attempted_action: str = Field(..., description="Attempted action")
    required_capability: Optional[str] = Field(None, description="Required capability")
    provided_capabilities: Optional[List[str]] = Field(None, description="Provided capabilities")
    endpoint: Optional[str] = Field(None, description="API endpoint")
    client_ip: Optional[str] = Field(None, description="Client IP address")
    subject: Optional[str] = Field(None, description="Subject")
    severity: str = Field(..., description="Violation severity")
    created_at: datetime = Field(..., description="Creation timestamp")


class UsageStatsResponse(BaseModel):
    """Response model for token usage statistics."""
    period_hours: int = Field(..., description="Analysis period in hours")
    total_usage: int = Field(..., description="Total usage count")
    success_rate: float = Field(..., description="Success rate percentage")
    successful_usage: int = Field(..., description="Successful usage count")
    failed_usage: int = Field(..., description="Failed usage count")
    usage_by_action: Dict[str, int] = Field(..., description="Usage count by action")
    avg_response_time_ms: Optional[float] = Field(None, description="Average response time")
    generated_at: str = Field(..., description="Report generation timestamp")


class ViolationStatsResponse(BaseModel):
    """Response model for violation statistics."""
    period_hours: int = Field(..., description="Analysis period in hours")
    total_violations: int = Field(..., description="Total violation count")
    violations_by_type: Dict[str, int] = Field(..., description="Violations by type")
    violations_by_severity: Dict[str, int] = Field(..., description="Violations by severity")
    top_violated_actions: Dict[str, int] = Field(..., description="Most violated actions")
    generated_at: str = Field(..., description="Report generation timestamp")


# Application lifecycle management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    # Startup
    logger.info("Starting CapTokens Service...")
    
    try:
        await init_database()
        logger.info("Database initialized successfully")
        
        # Store startup time
        app.state.startup_time = datetime.utcnow()
        
        logger.info("CapTokens Service started successfully")
        yield
        
    except Exception as e:
        logger.error(f"Failed to start CapTokens Service: {e}")
        raise
    finally:
        # Shutdown
        logger.info("Shutting down CapTokens Service...")
        await close_database()
        logger.info("CapTokens Service shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Anumate CapTokens Service",
        description="Production-grade Ed25519/JWT capability token management service",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    
    # CORS middleware for cross-origin requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    
    # Trusted host middleware for security
    allowed_hosts = os.getenv("ALLOWED_HOSTS", "*").split(",")
    if allowed_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    
    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with service information."""
        return {
            "service": "Anumate CapTokens API",
            "version": "1.0.0",
            "status": "operational",
            "description": "Production-grade capability token service with Ed25519/JWT tokens",
            "documentation": "/docs",
            "health": "/health",
            "api_endpoints": {
                "issue_token": "POST /v1/captokens",
                "verify_token": "POST /v1/captokens/verify",
                "refresh_token": "POST /v1/captokens/refresh",
                "audit_trail": "GET /v1/captokens/audit"
            },
            "features": [
                "Ed25519 signature verification",
                "Multi-tenant isolation",
                "Replay attack protection",
                "Comprehensive audit logging",
                "Database persistence"
            ]
        }
    
    # Health check endpoint
    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """Service health check."""
        try:
            uptime = int((datetime.utcnow() - app.state.startup_time).total_seconds())
            db_health = await check_database_health()
            
            return HealthResponse(
                status="healthy" if db_health["status"] == "healthy" else "degraded",
                version="0.1.0",
                uptime_seconds=uptime,
                database=db_health,
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise HTTPException(status_code=503, detail="Service unhealthy")
    
    # Dependency for tenant ID validation
    async def get_tenant_id(x_tenant_id: str = Header(..., description="Tenant identifier")):
        """Extract and validate tenant ID from headers."""
        try:
            return UUID(x_tenant_id)
        except ValueError:
            if not x_tenant_id or len(x_tenant_id.strip()) == 0:
                raise HTTPException(
                    status_code=400,
                    detail={"error": ErrorCode.VALIDATION_ERROR, "message": "Invalid tenant ID format"}
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail={"error": ErrorCode.VALIDATION_ERROR, "message": "Invalid tenant ID format"}
                )    # Token issuance endpoint
    @app.post("/v1/captokens", response_model=TokenIssueResponse)
    async def issue_token(
        request: TokenIssueRequest,
        tenant_id: UUID = Depends(get_tenant_id),
        db: AsyncSession = Depends(get_async_session),
        http_request: Request = None,
        background_tasks: BackgroundTasks = None,
    ):
        """Issue a new capability token."""
        start_time = datetime.utcnow()
        token_service = DatabaseTokenService(db)
        audit_service = AuditService(db)
        
        try:
            # Issue the token using A.22 implementation
            token_data = issue_capability_token(
                subject=request.subject,
                capabilities=request.capabilities,
                ttl_seconds=request.ttl_seconds,
                tenant_id=str(tenant_id),
            )
            
            # Store in database
            token_record = await token_service.store_token(
                token_id=UUID(token_data["token_id"]),
                tenant_id=tenant_id,
                token_hash=token_service._hash_token(token_data["token"]),
                subject=request.subject,
                capabilities=request.capabilities,
                expires_at=token_data["expires_at"],
                created_by=tenant_id,  # In production, this would be the authenticated user
                client_ip=http_request.client.host if http_request else None,
                user_agent=http_request.headers.get("user-agent") if http_request else None,
            )
            
            # Log audit trail
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            background_tasks.add_task(
                audit_service.log_operation,
                tenant_id=tenant_id,
                token_id=UUID(token_data["token_id"]),
                operation="issue",
                status="success",
                request_data={
                    "subject": request.subject,
                    "capabilities": request.capabilities,
                    "ttl_seconds": request.ttl_seconds,
                },
                response_data={
                    "token_id": token_data["token_id"],
                    "expires_at": token_data["expires_at"].isoformat(),
                },
                endpoint="/v1/captokens",
                http_method="POST",
                client_ip=http_request.client.host if http_request else None,
                user_agent=http_request.headers.get("user-agent") if http_request else None,
                duration_ms=duration_ms,
            )
            
            logger.info(
                "Token issued successfully",
                extra={
                    "token_id": token_data["token_id"],
                    "tenant_id": str(tenant_id),
                    "subject": request.subject,
                    "capabilities_count": len(request.capabilities),
                }
            )
            
            return TokenIssueResponse(
                token=token_data["token"],
                token_id=token_data["token_id"],
                subject=request.subject,
                capabilities=request.capabilities,
                expires_at=token_data["expires_at"],
                issued_at=token_data["issued_at"],
            )
            
        except Exception as e:
            # Log audit trail for failure
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            background_tasks.add_task(
                audit_service.log_operation,
                tenant_id=tenant_id,
                token_id=uuid.uuid4(),  # Generate placeholder ID for failed attempts
                operation="issue",
                status="failure",
                request_data={
                    "subject": request.subject,
                    "capabilities": request.capabilities,
                    "ttl_seconds": request.ttl_seconds,
                },
                error_details={"error": str(e)},
                endpoint="/v1/captokens",
                http_method="POST",
                client_ip=http_request.client.host if http_request else None,
                user_agent=http_request.headers.get("user-agent") if http_request else None,
                duration_ms=duration_ms,
            )
            
            logger.error(f"Token issuance failed: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": ErrorCode.INTERNAL_ERROR, "message": "Token issuance failed"}
            )
    
    # Token verification endpoint
    @app.post("/v1/captokens/verify", response_model=TokenVerifyResponse)
    async def verify_token(
        request: TokenVerifyRequest,
        tenant_id: UUID = Depends(get_tenant_id),
        db: AsyncSession = Depends(get_async_session),
        http_request: Request = None,
        background_tasks: BackgroundTasks = None,
    ):
        """Verify a capability token."""
        start_time = datetime.utcnow()
        audit_service = AuditService(db)
        replay_service = ReplayProtectionService(db)
        
        try:
            # Verify the token using A.22 implementation
            verification_result = verify_capability_token(request.token, str(tenant_id))
            
            if verification_result["valid"]:
                # Check for replay attacks
                token_jti = verification_result["payload"]["jti"]
                expires_at = datetime.fromtimestamp(verification_result["payload"]["exp"])
                
                replay_check = await replay_service.check_and_record_token_use(
                    token=request.token,
                    token_jti=token_jti,
                    expires_at=expires_at,
                    client_ip=http_request.client.host if http_request else None,
                    user_agent=http_request.headers.get("user-agent") if http_request else None,
                )
                
                if replay_check["is_replay"]:
                    logger.warning(
                        "Replay attack detected",
                        extra={
                            "token_jti": token_jti,
                            "usage_count": replay_check["usage_count"],
                        }
                    )
                    # Still return the verification result but log the replay
            
            # Log audit trail
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            token_id = UUID(verification_result["payload"]["jti"]) if verification_result["valid"] else uuid.uuid4()
            
            background_tasks.add_task(
                audit_service.log_operation,
                tenant_id=tenant_id,
                token_id=token_id,
                operation="verify",
                status="success" if verification_result["valid"] else "warning",
                request_data={"token_provided": bool(request.token)},
                response_data={"valid": verification_result["valid"]},
                endpoint="/v1/captokens/verify",
                http_method="POST",
                client_ip=http_request.client.host if http_request else None,
                user_agent=http_request.headers.get("user-agent") if http_request else None,
                duration_ms=duration_ms,
            )
            
            return TokenVerifyResponse(
                valid=verification_result["valid"],
                payload=verification_result["payload"],
                error=verification_result.get("error"),
            )
            
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            
            # Log audit trail for failure
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            background_tasks.add_task(
                audit_service.log_operation,
                tenant_id=tenant_id,
                token_id=uuid.uuid4(),
                operation="verify",
                status="failure",
                request_data={"token_provided": bool(request.token)},
                error_details={"error": str(e)},
                endpoint="/v1/captokens/verify",
                http_method="POST",
                client_ip=http_request.client.host if http_request else None,
                user_agent=http_request.headers.get("user-agent") if http_request else None,
                duration_ms=duration_ms,
            )
            
            raise HTTPException(
                status_code=500,
                detail={"error": ErrorCode.EXECUTION_ERROR, "message": "Token verification failed"}
            )
    
    # A.24 - Capability Enforcement Endpoints
    
    @app.post("/v1/capabilities/rules", response_model=ToolAllowListResponse)
    async def create_capability_rule(
        request: ToolAllowListRequest,
        tenant_id: UUID = Depends(get_tenant_id),
        db: AsyncSession = Depends(get_async_session),
    ):
        """Create a new capability rule for tool access control."""
        try:
            rule = ToolAllowList(
                tenant_id=tenant_id,
                capability_name=request.capability_name,
                tool_pattern=request.tool_pattern,
                action_pattern=request.action_pattern,
                rule_type=request.rule_type,
                pattern_type=request.pattern_type,
                priority=request.priority,
                description=request.description,
                is_active=request.is_active
            )
            
            db.add(rule)
            await db.commit()
            await db.refresh(rule)
            
            return ToolAllowListResponse(
                rule_id=str(rule.rule_id),
                tenant_id=str(rule.tenant_id),
                capability_name=rule.capability_name,
                tool_pattern=rule.tool_pattern,
                action_pattern=rule.action_pattern,
                rule_type=rule.rule_type,
                pattern_type=rule.pattern_type,
                priority=rule.priority,
                description=rule.description,
                is_active=rule.is_active,
                created_at=rule.created_at
            )
            
        except Exception as e:
            logger.error(f"Failed to create capability rule: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": "EXECUTION_ERROR", "message": "Failed to create capability rule"}
            )
    
    @app.get("/v1/capabilities/rules")
    async def list_capability_rules(
        tenant_id: UUID = Depends(get_tenant_id),
        db: AsyncSession = Depends(get_async_session),
        limit: int = 100,
        offset: int = 0,
        capability_name: Optional[str] = None,
        is_active: Optional[bool] = None
    ):
        """List capability rules for a tenant."""
        try:
            from sqlalchemy import select, and_
            
            query = select(ToolAllowList).where(ToolAllowList.tenant_id == tenant_id)
            
            if capability_name:
                query = query.where(ToolAllowList.capability_name == capability_name)
            
            if is_active is not None:
                query = query.where(ToolAllowList.is_active == is_active)
            
            query = query.order_by(ToolAllowList.priority, ToolAllowList.created_at).limit(limit).offset(offset)
            
            result = await db.execute(query)
            rules = result.scalars().all()
            
            return [
                ToolAllowListResponse(
                    rule_id=str(rule.rule_id),
                    tenant_id=str(rule.tenant_id),
                    capability_name=rule.capability_name,
                    tool_pattern=rule.tool_pattern,
                    action_pattern=rule.action_pattern,
                    rule_type=rule.rule_type,
                    pattern_type=rule.pattern_type,
                    priority=rule.priority,
                    description=rule.description,
                    is_active=rule.is_active,
                    created_at=rule.created_at
                )
                for rule in rules
            ]
            
        except Exception as e:
            logger.error(f"Failed to list capability rules: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": "EXECUTION_ERROR", "message": "Failed to list capability rules"}
            )
    
    @app.get("/v1/capabilities/violations")
    async def list_violations(
        tenant_id: UUID = Depends(get_tenant_id),
        db: AsyncSession = Depends(get_async_session),
        limit: int = 100,
        offset: int = 0,
        severity: Optional[str] = None,
        violation_type: Optional[str] = None
    ):
        """List capability violations for a tenant."""
        try:
            violation_logger = ViolationLogger(db)
            violations = await violation_logger.get_violations_by_tenant(
                tenant_id=str(tenant_id),
                limit=limit,
                offset=offset,
                severity=severity,
                violation_type=violation_type
            )
            
            return [
                ViolationResponse(
                    violation_id=str(violation.violation_id),
                    tenant_id=str(violation.tenant_id),
                    token_id=str(violation.token_id) if violation.token_id else None,
                    violation_type=violation.violation_type,
                    attempted_action=violation.attempted_action,
                    required_capability=violation.required_capability,
                    provided_capabilities=violation.provided_capabilities,
                    endpoint=violation.endpoint,
                    client_ip=violation.client_ip,
                    subject=violation.subject,
                    severity=violation.severity,
                    created_at=violation.created_at
                )
                for violation in violations
            ]
            
        except Exception as e:
            logger.error(f"Failed to list violations: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": "EXECUTION_ERROR", "message": "Failed to list violations"}
            )
    
    @app.get("/v1/capabilities/violations/stats", response_model=ViolationStatsResponse)
    async def get_violation_stats(
        tenant_id: UUID = Depends(get_tenant_id),
        db: AsyncSession = Depends(get_async_session),
        hours: int = 24
    ):
        """Get violation statistics for a tenant."""
        try:
            violation_logger = ViolationLogger(db)
            stats = await violation_logger.get_violation_stats(
                tenant_id=str(tenant_id),
                hours=hours
            )
            
            return ViolationStatsResponse(**stats)
            
        except Exception as e:
            logger.error(f"Failed to get violation stats: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": "EXECUTION_ERROR", "message": "Failed to get violation stats"}
            )
    
    @app.get("/v1/capabilities/usage/stats", response_model=UsageStatsResponse)
    async def get_usage_stats(
        tenant_id: UUID = Depends(get_tenant_id),
        db: AsyncSession = Depends(get_async_session),
        hours: int = 24,
        token_id: Optional[str] = None
    ):
        """Get token usage statistics."""
        try:
            usage_tracker = UsageTracker(db)
            stats = await usage_tracker.get_usage_stats(
                tenant_id=str(tenant_id),
                hours=hours,
                token_id=token_id
            )
            
            return UsageStatsResponse(**stats)
            
        except Exception as e:
            logger.error(f"Failed to get usage stats: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": "EXECUTION_ERROR", "message": "Failed to get usage stats"}
            )
    
    @app.post("/v1/capabilities/check")
    async def check_capability_access(
        request: CapabilityCheckRequest,
        tenant_id: UUID = Depends(get_tenant_id),
        db: AsyncSession = Depends(get_async_session)
    ):
        """Check if capabilities allow access to a tool/action."""
        try:
            from .capability_checker import CapabilityCheckRequest as CheckRequest
            
            capability_checker = CapabilityChecker(db)
            
            check_request = CheckRequest(
                capabilities=request.capabilities,
                tool=request.tool,
                action=request.action,
                tenant_id=str(tenant_id)
            )
            
            result = await capability_checker.check_capability(check_request)
            
            return {
                "allowed": result.allowed,
                "matched_rules": result.matched_rules,
                "violation_reason": result.violation_reason,
                "required_capabilities": result.required_capabilities
            }
            
        except Exception as e:
            logger.error(f"Failed to check capability access: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": "EXECUTION_ERROR", "message": "Failed to check capability access"}
            )
    
    @app.post("/v1/capabilities/initialize")
    async def initialize_default_rules(
        tenant_id: UUID = Depends(get_tenant_id),
        db: AsyncSession = Depends(get_async_session)
    ):
        """Initialize default capability rules for a tenant."""
        try:
            capability_checker = CapabilityChecker(db)
            await capability_checker.add_default_rules(str(tenant_id))
            
            return {"message": "Default capability rules initialized successfully"}
            
        except Exception as e:
            logger.error(f"Failed to initialize default rules: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": "EXECUTION_ERROR", "message": "Failed to initialize default rules"}
            )
    
    return app


# For running with uvicorn directly
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
