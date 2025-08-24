#!/usr/bin/env python3
"""
Production launcher script for the orchestrator service.
PRODUCTION GRADE - NO MOCKING, REAL MCP INTEGRATION
"""
import sys
import os
import logging

# Setup production logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the orchestrator directory to Python path
orchestrator_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, orchestrator_dir)

# Import and run the main app
try:
    from api.main import app
    logger.info("✅ Successfully imported FastAPI app")
except ImportError as e:
    logger.error(f"❌ Failed to import app: {e}")
    sys.exit(1)

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 PRODUCTION ORCHESTRATOR API - Starting with REAL Razorpay MCP")
    logger.info(f"📁 Working directory: {orchestrator_dir}")
    logger.info(f"🔧 Python path: {sys.path[0]}")
    logger.info("🎯 MODE: Production-grade hackathon MVP - NO MOCKING")
    
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8090,
            reload=False,  # Production mode - no reload
            log_level="info",
            access_log=True,
        )
    except Exception as e:
        logger.error(f"❌ Failed to start service: {e}")
        sys.exit(1)
