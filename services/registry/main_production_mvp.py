#!/usr/bin/env python3
"""
Production-Grade Hackathon MVP: Registry Service
Real functionality with minimal viable dependencies
"""

import os
import sys
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

# Set up logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add local paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, 'api'))
sys.path.insert(0, os.path.join(current_dir, 'src'))

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Import our routes - this is the REAL functionality
try:
    from api.routes.capsules import router as capsules_router
    logger.info("✅ Successfully imported capsules router - REAL routes available!")
    ROUTES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ Could not import routes: {e}")
    ROUTES_AVAILABLE = False

# Create the FastAPI app
app = FastAPI(
    title="Capsule Registry Service",
    description="A.4–A.6 Implementation: Production-Grade Hackathon MVP",
    version="1.0.0"
)

# Production-Grade Hackathon MVP: Real but minimal database setup
import sqlite3
import asyncio
import contextlib
from pathlib import Path

class MinimalProductionDatabaseManager:
    """
    Production-Grade Hackathon MVP: Real SQLite database manager
    - REAL database operations (not mocks)
    - Minimal setup (SQLite, not full PostgreSQL cluster)
    - Production patterns (transactions, async, error handling)
    - File-based persistence (data survives restarts)
    """
    
    def __init__(self, db_path: str = "./registry_mvp.db"):
        self.db_path = Path(db_path)
        self.connected = False
        self._init_database()
    
    def _init_database(self):
        """Initialize database with minimal schema for MVP"""
        try:
            # Create minimal tables for MVP functionality
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS capsules (
                        id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        owner TEXT NOT NULL,
                        status TEXT DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE TABLE IF NOT EXISTS capsule_versions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        capsule_id TEXT NOT NULL,
                        version INTEGER NOT NULL,
                        yaml_content TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (capsule_id) REFERENCES capsules(id)
                    );
                    
                    CREATE TABLE IF NOT EXISTS idempotency_keys (
                        key TEXT PRIMARY KEY,
                        capsule_id TEXT NOT NULL,
                        response_data TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                self.connected = True
                logger.info("✅ Production-grade database initialized with real persistence")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    @contextlib.asynccontextmanager
    async def transaction(self):
        """Real transaction context manager - production pattern"""
        conn = None
        try:
            # In production this would be async PostgreSQL
            # For MVP: SQLite with proper transaction handling
            conn = sqlite3.connect(self.db_path)
            conn.execute("BEGIN")
            yield DatabaseTransaction(conn)
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database transaction failed: {e}")
            raise
        finally:
            if conn:
                conn.close()

class DatabaseTransaction:
    """Real database transaction wrapper for MVP"""
    
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
    
    def execute(self, query: str, params: tuple = ()):
        """Execute SQL with real error handling"""
        try:
            cursor = self.conn.execute(query, params)
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"SQL execution failed: {e}")
            raise

# Set up application state with REAL database for production-grade MVP
app.state.db_manager = MinimalProductionDatabaseManager()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health endpoints
@app.get("/health")
async def health():
    return {
        "status": "healthy", 
        "service": "capsule-registry",
        "version": "1.0.0",
        "routes_available": ROUTES_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/readyz")
async def readiness():
    return {
        "status": "ready",
        "routes": ROUTES_AVAILABLE,
        "dependencies": {
            "database": "mock",  # MVP: would be real in production
            "events": "mock"     # MVP: would be real in production
        }
    }

# Include the REAL routes if available
if ROUTES_AVAILABLE:
    logger.info("🚀 Including REAL capsules router with all A.4-A.6 endpoints")
    app.include_router(capsules_router, prefix="/v1")
else:
    # Minimal fallback - but this wouldn't satisfy production-grade requirements
    logger.warning("⚠️ Using fallback routes - not production-grade!")
    
    @app.get("/v1/capsules")
    async def list_capsules_fallback():
        return {"error": "Routes not available", "status": "degraded"}

# Production-grade error handling
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting Production-Grade Hackathon MVP Registry Service...")
    logger.info(f"Routes available: {ROUTES_AVAILABLE}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8082, 
        log_level="info"
    )
