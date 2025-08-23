"""
Anumate Receipt Service - Production FastAPI Application
=======================================================

Production-grade tamper-evident receipt service with Ed25519 signatures,
WORM storage integration, and comprehensive audit logging.

Key Features:
- Tamper-evident receipts with cryptographic hashing
- Ed25519 digital signatures for integrity verification  
- WORM storage integration for compliance
- Multi-tenant isolation with RLS
- Comprehensive audit logging with SIEM export
- OpenTelemetry integration for observability

API Endpoints:
- POST /v1/receipts - Create tamper-evident receipt
- GET /v1/receipts/{receipt_id} - Get receipt details
- POST /v1/receipts/{receipt_id}/verify - Verify receipt integrity
- GET /v1/receipts/audit - Export audit logs to SIEM
- POST /v1/retention-policies - Create retention policy
- GET /v1/retention-policies - List retention policies

Version: 1.0.0
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Header, Query, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func

from anumate_errors import ValidationError, ExecutionError, ErrorCode
from anumate_core_config import settings

from .database import (
    init_database,
    create_tables,
    close_database,
    get_async_session,
    check_database_health,
    setup_row_level_security,
    set_tenant_context
)
from .models import Receipt, ReceiptAuditLog, RetentionPolicy, WormStorageRecord
from .schemas import (
    ReceiptCreateRequest,
    ReceiptResponse,
    ReceiptVerifyRequest,
    ReceiptVerifyResponse,
    AuditLogEntry,
    AuditExportRequest,
    AuditExportResponse,
    RetentionPolicyRequest,
    RetentionPolicyResponse,
    WormStorageRequest,
    WormStorageResponse,
    HealthResponse,
    ErrorResponse
)
from .receipt_service import ReceiptService, WormStorageService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Anumate Receipt Service",
        description="Production-grade tamper-evident receipt system with digital signatures and WORM storage",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize services
    receipt_service = ReceiptService()
    worm_service = WormStorageService()
    
    # Startup and shutdown events
    @app.on_event("startup")
    async def startup_event():
        """Initialize database and services on startup."""
        try:
            # Get database configuration
            database_url = os.getenv(
                "DATABASE_URL",
                "postgresql+asyncpg://anumate_admin:dev_password@localhost:5432/anumate"
            )
            
            # Initialize database
            await init_database(database_url)
            await create_tables()
            await setup_row_level_security()
            
            # Set startup time
            app.state.startup_time = datetime.utcnow()
            app.state.receipt_service = receipt_service
            app.state.worm_service = worm_service
            
            logger.info("Receipt service started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Receipt service: {e}")
            raise
    
    @app.on_event("shutdown")  
    async def shutdown_event():
        """Cleanup resources on shutdown."""
        await close_database()
        logger.info("Receipt service shutdown complete")
    
    # Dependency for tenant ID validation
    async def get_tenant_id(x_tenant_id: str = Header(..., description="Tenant identifier")):
        """Extract and validate tenant ID from headers."""
        try:
            return UUID(x_tenant_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={"error": ErrorCode.VALIDATION_ERROR, "message": "Invalid tenant ID format"}
            )
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint for service monitoring."""
        db_health = await check_database_health()
        current_time = datetime.utcnow()
        
        health_data = {
            "status": "healthy" if db_health["connected"] else "unhealthy",
            "timestamp": current_time.isoformat(),
            "version": "1.0.0",
            "database_status": db_health["status"],
            "worm_storage_status": "operational",  # TODO: Implement WORM health check
            "checks": {
                "database": db_health,
                "startup_time": app.state.startup_time.isoformat(),
                "uptime_seconds": (current_time - app.state.startup_time).total_seconds()
            }
        }
        
        if health_data["status"] != "healthy":
            return JSONResponse(
                status_code=503,
                content=health_data
            )
        
        return health_data
    
    # Root endpoint with service information
    @app.get("/")
    async def root():
        """Root endpoint with service information."""
        return {
            "service": "Anumate Receipt Service",
            "version": "1.0.0",
            "status": "operational",
            "description": "Tamper-evident receipt system with Ed25519 signatures and WORM storage",
            "documentation": "/docs",
            "health": "/health",
            "api_endpoints": {
                "create_receipt": "POST /v1/receipts",
                "get_receipt": "GET /v1/receipts/{receipt_id}",
                "verify_receipt": "POST /v1/receipts/{receipt_id}/verify",
                "audit_logs": "GET /v1/receipts/audit",
                "retention_policies": "GET /v1/retention-policies"
            },
            "features": [
                "Ed25519 digital signatures",
                "Tamper-evident receipts",
                "Multi-tenant isolation", 
                "WORM storage integration",
                "Comprehensive audit logging",
                "SIEM export capabilities"
            ]
        }
    
    # Receipt management endpoints
    @app.post("/v1/receipts", response_model=ReceiptResponse)
    async def create_receipt(
        request: ReceiptCreateRequest,
        tenant_id: UUID = Depends(get_tenant_id),
        session: AsyncSession = Depends(get_async_session)
    ):
        """Create a new tamper-evident receipt with cryptographic signature."""
        try:
            await set_tenant_context(session, str(tenant_id))
            
            receipt = await app.state.receipt_service.create_receipt(
                session, tenant_id, request
            )
            
            return ReceiptResponse.model_validate(receipt)
            
        except ValidationError as e:
            raise HTTPException(
                status_code=400,
                detail={"error": ErrorCode.VALIDATION_ERROR, "message": str(e)}
            )
        except Exception as e:
            logger.error(f"Failed to create receipt: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": ErrorCode.EXECUTION_ERROR, "message": "Failed to create receipt"}
            )
    
    # Audit logging endpoints - must come before {receipt_id} route
    @app.get("/v1/receipts/audit", response_model=List[AuditLogEntry])
    async def get_audit_logs(
        tenant_id: UUID = Depends(get_tenant_id),
        receipt_id: Optional[UUID] = Query(None, description="Filter by receipt ID"),
        event_type: Optional[str] = Query(None, description="Filter by event type"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
        offset: int = Query(0, ge=0, description="Number of results to skip"),
        session: AsyncSession = Depends(get_async_session)
    ):
        """Get audit logs for receipts."""
        try:
            await set_tenant_context(session, str(tenant_id))
            
            query = select(ReceiptAuditLog).where(ReceiptAuditLog.tenant_id == tenant_id)
            
            if receipt_id:
                query = query.where(ReceiptAuditLog.receipt_id == receipt_id)
            if event_type:
                query = query.where(ReceiptAuditLog.event_type == event_type)
            
            query = query.order_by(desc(ReceiptAuditLog.created_at)).limit(limit).offset(offset)
            
            result = await session.execute(query)
            audit_logs = result.scalars().all()
            
            return [AuditLogEntry.model_validate(log) for log in audit_logs]
            
        except Exception as e:
            logger.error(f"Failed to get audit logs: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": ErrorCode.EXECUTION_ERROR, "message": "Failed to retrieve audit logs"}
            )
    
    @app.get("/v1/receipts/{receipt_id}", response_model=ReceiptResponse)
    async def get_receipt(
        receipt_id: UUID,
        tenant_id: UUID = Depends(get_tenant_id),
        session: AsyncSession = Depends(get_async_session)
    ):
        """Get receipt details by ID."""
        try:
            await set_tenant_context(session, str(tenant_id))
            
            result = await session.execute(
                select(Receipt).where(
                    and_(Receipt.receipt_id == receipt_id, Receipt.tenant_id == tenant_id)
                )
            )
            receipt = result.scalar_one_or_none()
            
            if not receipt:
                raise HTTPException(
                    status_code=404,
                    detail={"error": ErrorCode.VALIDATION_ERROR, "message": "Receipt not found"}
                )
            
            # Log access
            await app.state.receipt_service._log_audit_event(
                session, receipt_id, tenant_id, "accessed", "receipt-service"
            )
            
            return ReceiptResponse.model_validate(receipt)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get receipt: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": ErrorCode.EXECUTION_ERROR, "message": "Failed to retrieve receipt"}
            )
    
    @app.post("/v1/receipts/{receipt_id}/verify", response_model=ReceiptVerifyResponse)
    async def verify_receipt(
        receipt_id: UUID,
        verify_request: ReceiptVerifyRequest,
        tenant_id: UUID = Depends(get_tenant_id),
        session: AsyncSession = Depends(get_async_session)
    ):
        """Verify receipt integrity and signature."""
        try:
            await set_tenant_context(session, str(tenant_id))
            
            result = await app.state.receipt_service.verify_receipt(
                session, 
                tenant_id, 
                receipt_id,
                verify_signature=verify_request.verify_signature,
                update_timestamp=verify_request.update_verification_timestamp
            )
            
            return result
            
        except ValidationError as e:
            raise HTTPException(
                status_code=400,
                detail={"error": ErrorCode.VALIDATION_ERROR, "message": str(e)}
            )
        except Exception as e:
            logger.error(f"Failed to verify receipt: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": ErrorCode.EXECUTION_ERROR, "message": "Failed to verify receipt"}
            )
    
    @app.get("/v1/receipts", response_model=List[ReceiptResponse])
    async def list_receipts(
        tenant_id: UUID = Depends(get_tenant_id),
        receipt_type: Optional[str] = Query(None, description="Filter by receipt type"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
        offset: int = Query(0, ge=0, description="Number of results to skip"),
        session: AsyncSession = Depends(get_async_session)
    ):
        """List receipts for a tenant with optional filtering."""
        try:
            await set_tenant_context(session, str(tenant_id))
            
            query = select(Receipt).where(Receipt.tenant_id == tenant_id)
            
            if receipt_type:
                query = query.where(Receipt.receipt_type == receipt_type)
            
            query = query.order_by(desc(Receipt.created_at)).limit(limit).offset(offset)
            
            result = await session.execute(query)
            receipts = result.scalars().all()
            
            return [ReceiptResponse.model_validate(receipt) for receipt in receipts]
            
        except Exception as e:
            logger.error(f"Failed to list receipts: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": ErrorCode.EXECUTION_ERROR, "message": "Failed to list receipts"}
            )
    
    # Retention policy endpoints
    @app.post("/v1/retention-policies", response_model=RetentionPolicyResponse)
    async def create_retention_policy(
        request: RetentionPolicyRequest,
        tenant_id: UUID = Depends(get_tenant_id),
        session: AsyncSession = Depends(get_async_session)
    ):
        """Create a new retention policy."""
        try:
            await set_tenant_context(session, str(tenant_id))
            
            policy = RetentionPolicy(
                tenant_id=tenant_id,
                policy_name=request.policy_name,
                receipt_types=request.receipt_types,
                retention_days=request.retention_days,
                description=request.description,
                compliance_requirements=request.compliance_requirements,
                auto_delete=request.auto_delete,
                priority=request.priority
            )
            
            session.add(policy)
            await session.flush()
            
            return RetentionPolicyResponse.model_validate(policy)
            
        except Exception as e:
            logger.error(f"Failed to create retention policy: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": ErrorCode.EXECUTION_ERROR, "message": "Failed to create retention policy"}
            )
    
    @app.get("/v1/retention-policies", response_model=List[RetentionPolicyResponse])
    async def list_retention_policies(
        tenant_id: UUID = Depends(get_tenant_id),
        session: AsyncSession = Depends(get_async_session)
    ):
        """List retention policies for a tenant."""
        try:
            await set_tenant_context(session, str(tenant_id))
            
            result = await session.execute(
                select(RetentionPolicy)
                .where(RetentionPolicy.tenant_id == tenant_id)
                .order_by(RetentionPolicy.priority.asc(), RetentionPolicy.created_at.desc())
            )
            policies = result.scalars().all()
            
            return [RetentionPolicyResponse.model_validate(policy) for policy in policies]
            
        except Exception as e:
            logger.error(f"Failed to list retention policies: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": ErrorCode.EXECUTION_ERROR, "message": "Failed to list retention policies"}
            )
    
    # WORM storage endpoints
    @app.post("/v1/receipts/{receipt_id}/worm", response_model=WormStorageResponse)
    async def write_to_worm_storage(
        receipt_id: UUID,
        worm_request: WormStorageRequest,
        tenant_id: UUID = Depends(get_tenant_id),
        session: AsyncSession = Depends(get_async_session)
    ):
        """Write receipt to WORM storage."""
        try:
            await set_tenant_context(session, str(tenant_id))
            
            # Get receipt
            result = await session.execute(
                select(Receipt).where(
                    and_(Receipt.receipt_id == receipt_id, Receipt.tenant_id == tenant_id)
                )
            )
            receipt = result.scalar_one_or_none()
            
            if not receipt:
                raise HTTPException(
                    status_code=404,
                    detail={"error": ErrorCode.VALIDATION_ERROR, "message": "Receipt not found"}
                )
            
            # Write to WORM storage
            storage_path = await app.state.worm_service.write_to_worm_storage(
                session, receipt, worm_request.storage_provider
            )
            
            # Create WORM storage record
            worm_record = WormStorageRecord(
                receipt_id=receipt_id,
                tenant_id=tenant_id,
                storage_provider=worm_request.storage_provider,
                storage_path=storage_path,
                storage_checksum=receipt.content_hash,  # Use receipt hash as storage checksum
                written_by="receipt-service",
                is_accessible=True
            )
            
            session.add(worm_record)
            await session.flush()
            
            return WormStorageResponse.model_validate(worm_record)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to write to WORM storage: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error": ErrorCode.EXECUTION_ERROR, "message": "Failed to write to WORM storage"}
            )
    
    return app


# For running with uvicorn directly
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
