#!/usr/bin/env python3
"""
Production FastAPI Service - Hackathon MVP
==========================================

Simplified production-grade service for hackathon MVP.
Bypasses complex async database pooling in favor of reliable direct connections.
"""

import sys
import os
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

# Setup project paths
project_root = Path(__file__).parent.parent.parent
packages_dir = project_root / "packages"

# Add package paths to Python path
sys.path.insert(0, str(packages_dir / "anumate-capability-tokens"))
sys.path.insert(0, str(packages_dir / "anumate-logging"))  
sys.path.insert(0, str(packages_dir / "anumate-errors"))

from anumate_capability_tokens import (
    issue_capability_token, 
    verify_capability_token, 
    check_capability,
    InMemoryReplayGuard,
    CapabilityToken
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global service state
service_keys = None
replay_guard = InMemoryReplayGuard()


def execute_db_query(query: str, params: Optional[List] = None) -> Dict[str, Any]:
    """Execute database query via docker exec for simplicity and reliability."""
    try:
        # Build command
        if params:
            # For parameterized queries, we'll use a simple approach
            formatted_query = query
            for i, param in enumerate(params):
                formatted_query = formatted_query.replace(f"${i+1}", f"'{param}'")
        else:
            formatted_query = query
            
        cmd = [
            'docker', 'exec', '-i', 'anumate-postgres',
            'psql', '-U', 'anumate_admin', '-d', 'anumate',
            '-t', '-c', formatted_query
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            logger.error(f"Database query failed: {result.stderr}")
            raise Exception(f"Database error: {result.stderr}")
            
        return {"success": True, "output": result.stdout.strip()}
        
    except Exception as e:
        logger.error(f"Database query error: {e}")
        return {"success": False, "error": str(e)}


def store_token_in_db(capability_token: CapabilityToken, tenant_id: str, created_by: str = "api"):
    """Store issued token in database for audit trail."""
    try:
        # Calculate token hash for security
        import hashlib
        token_hash = hashlib.sha256(capability_token.token.encode()).hexdigest()
        
        query = f"""
        INSERT INTO capability_tokens (
            token_id, tenant_id, token_hash, subject, capabilities,
            expires_at, active, usage_count, token_metadata, created_by,
            created_at, updated_at
        ) VALUES (
            '{capability_token.token_id}',
            '{tenant_id}',
            '{token_hash}',
            '{capability_token.subject}',
            '{json.dumps(capability_token.capabilities)}',
            '{capability_token.expires_at.isoformat()}',
            true,
            0,
            '{{}}',
            '{created_by}',
            NOW(),
            NOW()
        );
        """
        
        result = execute_db_query(query)
        if result["success"]:
            logger.info(f"✅ Token stored in database: {capability_token.token_id}")
        else:
            logger.error(f"❌ Failed to store token: {result.get('error')}")
            
    except Exception as e:
        logger.error(f"❌ Token storage error: {e}")


def audit_token_usage(token_id: str, operation: str, status: str, details: Dict = None):
    """Log token usage to audit trail."""
    try:
        audit_id = str(uuid.uuid4())
        details_json = json.dumps(details or {})
        
        query = f"""
        INSERT INTO token_audit_logs (
            audit_id, tenant_id, token_id, operation, status,
            request_data, response_data, created_at, updated_at
        ) VALUES (
            '{audit_id}',
            'default',
            '{token_id}',
            '{operation}',
            '{status}',
            '{details_json}',
            '{details_json}',
            NOW(),
            NOW()
        );
        """
        
        result = execute_db_query(query)
        if result["success"]:
            logger.info(f"✅ Audit logged: {operation} - {status}")
            
    except Exception as e:
        logger.error(f"❌ Audit logging error: {e}")


class TokenIssueRequest(BaseModel):
    """Request to issue a new capability token."""
    subject: str = Field(..., description="Subject (user/service) identifier")
    capabilities: List[str] = Field(..., description="List of capability strings", min_items=1)
    ttl_seconds: int = Field(default=300, description="TTL in seconds (max 300)", le=300, ge=1)


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


class TokenVerifyResponse(BaseModel):
    """Response from token verification."""
    valid: bool = Field(..., description="Whether token is valid")
    payload: Optional[Dict[str, Any]] = Field(None, description="Token payload if valid")
    error: Optional[str] = Field(None, description="Error message if invalid")


class CapabilityCheckRequest(BaseModel):
    """Request to check token capability."""
    token: str = Field(..., description="JWT token to check")
    capability: str = Field(..., description="Required capability")


class CapabilityCheckResponse(BaseModel):
    """Response from capability check."""
    has_capability: bool = Field(..., description="Whether token has the capability")
    payload: Optional[Dict[str, Any]] = Field(None, description="Token payload if valid")


# Create FastAPI app
app = FastAPI(
    title="Anumate CapTokens Service - Hackathon MVP",
    description="A.22 Implementation: Production-grade Ed25519/JWT capability tokens for hackathon MVP",
    version="1.0.0-mvp"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    global service_keys
    
    logger.info("🚀 Starting CapTokens Service - Hackathon MVP")
    
    # Initialize Ed25519 keys
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    service_keys = {
        "private_key": private_key,
        "public_key": public_key
    }
    
    # Log keys for development
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    logger.info("🔑 Generated Ed25519 keys for development:")
    logger.info(f"Private Key:\n{private_pem.decode()}")
    logger.info(f"Public Key:\n{public_pem.decode()}")
    
    # Test database connection
    db_result = execute_db_query("SELECT COUNT(*) FROM capability_tokens;")
    if db_result["success"]:
        logger.info("✅ Database connection verified")
    else:
        logger.error("❌ Database connection failed")
    
    logger.info("✅ CapTokens Service startup complete - Ready for hackathon MVP!")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    db_result = execute_db_query("SELECT 1;")
    return {
        "status": "healthy" if db_result["success"] else "unhealthy",
        "service": "captokens-mvp",
        "version": "1.0.0-mvp",
        "database": "connected" if db_result["success"] else "disconnected"
    }


@app.post("/v1/captokens", response_model=TokenIssueResponse)
async def issue_token(
    request: TokenIssueRequest,
    background_tasks: BackgroundTasks,
    x_tenant_id: str = Header(..., description="Tenant ID")
) -> TokenIssueResponse:
    """
    Issue a new capability token.
    
    A.22 Implementation: Creates Ed25519/JWT capability tokens with ≤5min expiry.
    """
    if not service_keys:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        # Issue capability token
        capability_token = issue_capability_token(
            private_key=service_keys["private_key"],
            sub=request.subject,
            capabilities=request.capabilities,
            ttl_secs=request.ttl_seconds,
            tenant_id=x_tenant_id
        )
        
        # Store in database (background task)
        background_tasks.add_task(
            store_token_in_db, capability_token, x_tenant_id, "api"
        )
        
        # Log audit trail (background task)
        background_tasks.add_task(
            audit_token_usage,
            capability_token.token_id,
            "issue",
            "success",
            {
                "subject": request.subject,
                "capabilities": request.capabilities,
                "ttl": request.ttl_seconds
            }
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
        logger.error(f"Token issuance error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/v1/captokens/verify", response_model=TokenVerifyResponse)
async def verify_token(
    request: TokenVerifyRequest,
    background_tasks: BackgroundTasks,
    x_tenant_id: str = Header(..., description="Tenant ID")
) -> TokenVerifyResponse:
    """
    Verify a capability token.
    
    A.22 Implementation: Validates Ed25519 signature and checks expiry/replay.
    """
    if not service_keys:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        payload = verify_capability_token(
            public_key=service_keys["public_key"],
            token=request.token,
            replay_guard=replay_guard
        )
        
        # Extract token ID for audit
        token_id = payload.get("jti", "unknown")
        
        # Log audit trail (background task)
        background_tasks.add_task(
            audit_token_usage,
            token_id,
            "verify",
            "success",
            {"valid": True}
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
        logger.error(f"Token verification error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/v1/captokens/check", response_model=CapabilityCheckResponse)
async def check_capability_endpoint(
    request: CapabilityCheckRequest,
    background_tasks: BackgroundTasks,
    x_tenant_id: str = Header(..., description="Tenant ID")
) -> CapabilityCheckResponse:
    """
    Check if token has a specific capability.
    
    A.22 Implementation: Capability-based access control validation.
    """
    if not service_keys:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        has_capability = check_capability(
            public_key=service_keys["public_key"],
            token=request.token,
            required_capability=request.capability,
            replay_guard=replay_guard
        )
        
        # If capability check succeeded, also get payload for response
        payload = None
        if has_capability:
            try:
                payload = verify_capability_token(
                    public_key=service_keys["public_key"],
                    token=request.token,
                    replay_guard=InMemoryReplayGuard()  # Separate guard to avoid double-checking
                )
            except:
                pass  # Ignore payload extraction errors
        
        # Extract token ID for audit
        token_id = payload.get("jti", "unknown") if payload else "unknown"
        
        # Log audit trail (background task)
        background_tasks.add_task(
            audit_token_usage,
            token_id,
            "check_capability",
            "success",
            {
                "capability": request.capability,
                "has_capability": has_capability
            }
        )
        
        return CapabilityCheckResponse(
            has_capability=has_capability,
            payload=payload
        )
        
    except Exception as e:
        logger.error(f"Capability check error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/v1/captokens/stats")
async def get_token_stats(x_tenant_id: str = Header(..., description="Tenant ID")):
    """Get token statistics for monitoring."""
    try:
        # Get basic stats from database
        active_result = execute_db_query(
            f"SELECT COUNT(*) FROM capability_tokens WHERE tenant_id = '{x_tenant_id}' AND active = true;"
        )
        total_result = execute_db_query(
            f"SELECT COUNT(*) FROM capability_tokens WHERE tenant_id = '{x_tenant_id}';"
        )
        
        active_count = 0
        total_count = 0
        
        if active_result["success"]:
            active_count = int(active_result["output"].strip())
        if total_result["success"]:
            total_count = int(total_result["output"].strip())
        
        return {
            "tenant_id": x_tenant_id,
            "active_tokens": active_count,
            "total_tokens": total_count,
            "expired_tokens": total_count - active_count,
            "service_status": "production-ready-mvp"
        }
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8001"))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"🌐 Starting production server on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,  # Production mode
        log_level="info",
        access_log=True
    )
