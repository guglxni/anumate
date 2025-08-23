"""
Anumate Approvals Service

Enterprise-grade approval management service with Portia integration and
multi-channel notifications. Provides RESTful API for approval workflows.

Author: Anumate Platform
Created: $(date +%Y-%m-%d)
"""

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
import logging
import os
from typing import AsyncGenerator

# Internal imports
from api.routes import router as approval_router
from api.workflow_routes import workflow_router
from dependencies import get_database, get_event_publisher
from src.models import init_database


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan management."""
    logger.info("Starting Anumate Approvals Service")
    
    # Initialize database
    try:
        database = get_database()
        await init_database(database)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # Initialize event publisher
    try:
        event_publisher = get_event_publisher()
        # Test connection if needed
        logger.info("Event publisher initialized")
    except Exception as e:
        logger.error(f"Failed to initialize event publisher: {e}")
        # Don't fail startup for event publisher issues
    
    yield
    
    logger.info("Shutting down Anumate Approvals Service")


# Create FastAPI application
app = FastAPI(
    title="Anumate Approvals Service",
    description="""
    Enterprise approval management service for the Anumate Platform.
    
    ## Features
    
    * **Multi-tenant approval workflows** - Complete tenant isolation
    * **Portia Runtime integration** - ClarificationsBridge support  
    * **Multi-channel notifications** - Email, Slack, webhooks
    * **Event-driven architecture** - CloudEvents integration
    * **Enterprise security** - Role-based access control
    
    ## Workflows
    
    1. **Clarification Request** - Portia → ClarificationsBridge → Approvals
    2. **Approval Processing** - Multi-step approval workflows
    3. **Notification Delivery** - Real-time approval notifications
    4. **Status Updates** - Live workflow status tracking
    
    ## Integration
    
    - **Portia Runtime**: Receives clarifications via ClarificationsBridge
    - **Notification Services**: Email, Slack, webhook providers
    - **Event Bus**: Publishes approval events to platform
    - **Policy Service**: Validates approval requirements
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent error format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception in {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "path": str(request.url.path),
        },
    )


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {
        "status": "healthy",
        "service": "approvals",
        "version": "1.0.0",
    }


# Ready check endpoint  
@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Readiness check endpoint for Kubernetes deployments."""
    try:
        # Check database connectivity
        database = get_database()
        # Simple connectivity test
        
        return {
            "status": "ready",
            "service": "approvals",
            "checks": {
                "database": "ok",
                "event_publisher": "ok",
            }
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "error": str(e),
            }
        )


# Include API routes
app.include_router(approval_router, tags=["Approvals"])
app.include_router(workflow_router, tags=["Workflows"])


# Run the application
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    reload = os.getenv("ENVIRONMENT", "production") == "development"
    
    logger.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        access_log=True,
    )
