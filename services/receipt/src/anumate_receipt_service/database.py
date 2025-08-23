"""
Database Connection and Session Management for Receipt Service
==============================================================

Production-grade async PostgreSQL connection management with connection pooling,
health checks, and multi-tenant row-level security.
"""

import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from .models import Base

logger = logging.getLogger(__name__)

# Global database engine and session factory
engine = None
async_session_factory = None


async def init_database(database_url: str) -> None:
    """
    Initialize the async database engine and session factory.
    
    Args:
        database_url: PostgreSQL connection URL
    """
    global engine, async_session_factory
    
    # Create async engine with connection pooling
    engine = create_async_engine(
        database_url,
        echo=False,  # Set to True for SQL debugging
        poolclass=NullPool,  # Use NullPool for async operations
        pool_pre_ping=True,  # Validate connections before use
        pool_recycle=300,  # Recycle connections every 5 minutes
        connect_args={
            "command_timeout": 60,  # Command timeout in seconds
            "server_settings": {
                "jit": "off",  # Disable JIT for better performance
                "application_name": "anumate-receipt-service"
            }
        }
    )
    
    # Create session factory
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
        autocommit=False
    )
    
    logger.info("Database engine initialized successfully")


async def create_tables() -> None:
    """Create all database tables."""
    if engine is None:
        raise RuntimeError("Database engine not initialized. Call init_database() first.")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database tables created successfully")


async def close_database() -> None:
    """Close database connections and cleanup."""
    if engine:
        await engine.dispose()
        logger.info("Database connections closed")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get an async database session with proper cleanup.
    
    Yields:
        AsyncSession: Database session for async operations
    """
    if async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_session_context():
    """Context manager for database sessions."""
    async with get_async_session() as session:
        yield session


async def check_database_health() -> dict:
    """
    Check database connectivity and health.
    
    Returns:
        dict: Database health status
    """
    try:
        if engine is None:
            return {
                "status": "error",
                "message": "Database engine not initialized",
                "connected": False
            }
        
        async with engine.begin() as conn:
            # Test basic connectivity
            result = await conn.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            
            # Check if our tables exist
            tables_result = await conn.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('receipts', 'receipt_audit_logs', 'retention_policies', 'worm_storage_records')
            """))
            table_count = tables_result.scalar()
            
            # Get connection pool info
            pool_size = engine.pool.size() if hasattr(engine.pool, 'size') else 0
            checked_in = engine.pool.checkedin() if hasattr(engine.pool, 'checkedin') else 0
            
            return {
                "status": "healthy",
                "message": "Database connection successful",
                "connected": True,
                "test_query": test_value == 1,
                "tables_found": table_count,
                "expected_tables": 4,
                "pool_size": pool_size,
                "checked_in_connections": checked_in
            }
            
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "error",
            "message": f"Database connection failed: {str(e)}",
            "connected": False,
            "error": str(e)
        }


async def setup_row_level_security() -> None:
    """Set up row-level security for multi-tenant isolation."""
    if engine is None:
        raise RuntimeError("Database engine not initialized")
    
    rls_sql = """
        -- Enable RLS on all tenant tables
        ALTER TABLE receipts ENABLE ROW LEVEL SECURITY;
        ALTER TABLE receipt_audit_logs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE retention_policies ENABLE ROW LEVEL SECURITY;
        ALTER TABLE worm_storage_records ENABLE ROW LEVEL SECURITY;
        
        -- Create RLS policies for tenant isolation
        CREATE POLICY receipts_tenant_policy ON receipts
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
            
        CREATE POLICY receipt_audit_logs_tenant_policy ON receipt_audit_logs
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
            
        CREATE POLICY retention_policies_tenant_policy ON retention_policies
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
            
        CREATE POLICY worm_storage_records_tenant_policy ON worm_storage_records
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
    """
    
    try:
        async with engine.begin() as conn:
            # Execute each statement separately to handle "already exists" errors
            statements = [stmt.strip() for stmt in rls_sql.split(';') if stmt.strip()]
            for statement in statements:
                try:
                    await conn.execute(statement)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        logger.warning(f"RLS setup warning: {e}")
        
        logger.info("Row-level security configured successfully")
        
    except Exception as e:
        logger.error(f"Failed to setup RLS: {e}")
        raise


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """
    Set the tenant context for row-level security.
    
    Args:
        session: Database session
        tenant_id: UUID string of the tenant
    """
    await session.execute(text(f"SET app.current_tenant_id = '{tenant_id}'"))


# Direct asyncpg connection for raw SQL operations
async def get_raw_connection():
    """Get a raw asyncpg connection for direct SQL operations."""
    # Extract connection details from SQLAlchemy engine
    url = str(engine.url)
    # Convert SQLAlchemy URL to asyncpg format
    asyncpg_url = url.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(asyncpg_url)
