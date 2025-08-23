"""
Database Configuration and Session Management
============================================

Production-grade database setup with connection pooling, health checks, and async support.
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from .models import Base

# Import logging with fallback
try:
    from anumate_logging import get_logger
except ImportError:
    import logging
    def get_logger(name: str):
        return logging.getLogger(name)

logger = get_logger(__name__)

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://anumate_admin:dev_password@127.0.0.1:5432/anumate"
)

# Create async engine with development-friendly settings
engine = create_async_engine(
    DATABASE_URL,
    # Simpler connection settings for development
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,  # 5 minutes
    # Echo SQL queries in development
    echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
    autocommit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session with proper cleanup.
    
    Yields:
        AsyncSession: Database session
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_database() -> None:
    """
    Initialize database tables and perform health checks.
    
    Should be called during application startup.
    """
    try:
        logger.info("Initializing database connection...")
        
        # Test connection
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            
            logger.info("Database tables created/verified successfully")
        
        # Test session creation using the session factory directly
        async with async_session_factory() as session:
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1 as health_check"))
            health_result = result.scalar()
            
            if health_result != 1:
                raise Exception("Database health check failed")
            
            logger.info("Database health check passed")
        
        logger.info("Database initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


async def close_database() -> None:
    """
    Close database connections and cleanup.
    
    Should be called during application shutdown.
    """
    try:
        logger.info("Closing database connections...")
        await engine.dispose()
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")


async def check_database_health() -> dict:
    """
    Check database health and return status information.
    
    Returns:
        dict: Health status information
    """
    try:
        async with async_session_factory() as session:
            # Import text function
            from sqlalchemy import text
            
            # Test basic connectivity
            result = await session.execute(text("SELECT 1 as health_check"))
            health_result = result.scalar()
            
            if health_result != 1:
                return {
                    "status": "unhealthy",
                    "error": "Health check query failed",
                }
            
            # Test table access
            table_check = await session.execute(
                text("SELECT COUNT(*) FROM capability_tokens LIMIT 1")
            )
            
            # Get connection pool stats
            pool = engine.pool
            pool_status = {
                "size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "invalidated": pool.invalid(),
            }
            
            return {
                "status": "healthy",
                "database_url": DATABASE_URL.split("@")[-1],  # Hide credentials
                "pool_stats": pool_status,
                "tables_accessible": True,
            }
            
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "database_url": DATABASE_URL.split("@")[-1],  # Hide credentials
        }
