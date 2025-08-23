"""Main FastAPI application for orchestrator service."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
# Infrastructure imports - simplified for demo
import logging

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from routes.execution import router as execution_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.
    
    Args:
        app: FastAPI application
        
    Yields:
        None during application lifetime
    """
    # Startup
    logger.info("Starting Orchestrator API service...")
    
    # Initialize infrastructure components (simplified for demo)
    logger.info("Infrastructure components initialized (demo mode)")
    
    logger.info("Orchestrator API service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Orchestrator API service...")
    # Cleanup would go here
    logger.info("Orchestrator API service shutdown complete")


def create_app() -> FastAPI:
    """Create FastAPI application.
    
    Returns:
        Configured FastAPI application
    """
    # Setup basic logging
    logging.basicConfig(level=logging.INFO)
    
    # Create FastAPI app
    app = FastAPI(
        title="Anumate Orchestrator API",
        description="ExecutablePlan execution orchestration via Portia Runtime",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(execution_router)
    
    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "orchestrator-api"}
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler.
        
        Args:
            request: HTTP request
            exc: Exception that occurred
            
        Returns:
            JSON error response
        """
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "path": str(request.url.path),
            }
        )
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )