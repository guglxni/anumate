"""Database manager with multi-tenant RLS support."""

import os
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from .tenant_context import get_current_tenant_id

logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Database manager with automatic tenant context and RLS enforcement."""
    
    def __init__(self, database_url: Optional[str] = None) -> None:
        """Initialize database manager."""
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", 
            "postgresql://anumate_app:app_password@localhost:5432/anumate"
        )
        self._pool: Optional[asyncpg.Pool] = None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=5,
                max_size=20,
                command_timeout=30,
                server_settings={
                    "application_name": "anumate-app",
                    "timezone": "UTC",
                }
            )
            logger.info("Database connection pool created")
        return self._pool
    
    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Database connection pool closed")
    
    async def _execute_with_tenant_context(
        self, 
        query: str, 
        *args: Any,
        fetch_method: str = "fetch"
    ) -> Any:
        """Execute query with tenant context set."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set. Use TenantContext manager.")
        
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            # Set tenant context for RLS
            await conn.execute(
                "SET app.current_tenant_id = $1", 
                str(tenant_id)
            )
            
            # Execute the query
            if fetch_method == "fetch":
                return await conn.fetch(query, *args)
            elif fetch_method == "fetchrow":
                return await conn.fetchrow(query, *args)
            elif fetch_method == "fetchval":
                return await conn.fetchval(query, *args)
            elif fetch_method == "execute":
                return await conn.execute(query, *args)
            else:
                raise ValueError(f"Unknown fetch method: {fetch_method}")
    
    async def fetch(self, query: str, *args: Any) -> List[asyncpg.Record]:
        """Fetch multiple rows with tenant context."""
        logger.debug("Executing fetch query", query=query, args=args)
        return await self._execute_with_tenant_context(query, *args, fetch_method="fetch")
    
    async def fetchrow(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        """Fetch single row with tenant context."""
        logger.debug("Executing fetchrow query", query=query, args=args)
        return await self._execute_with_tenant_context(query, *args, fetch_method="fetchrow")
    
    async def fetchval(self, query: str, *args: Any) -> Any:
        """Fetch single value with tenant context."""
        logger.debug("Executing fetchval query", query=query, args=args)
        return await self._execute_with_tenant_context(query, *args, fetch_method="fetchval")
    
    async def execute(self, query: str, *args: Any) -> str:
        """Execute query with tenant context."""
        logger.debug("Executing query", query=query, args=args)
        return await self._execute_with_tenant_context(query, *args, fetch_method="execute")
    
    async def transaction(self):
        """Create a transaction with tenant context."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set. Use TenantContext manager.")
        
        pool = await self.get_pool()
        conn = await pool.acquire()
        
        # Set tenant context
        await conn.execute("SET app.current_tenant_id = $1", str(tenant_id))
        
        return DatabaseTransaction(conn, pool)


class DatabaseTransaction:
    """Database transaction with tenant context."""
    
    def __init__(self, conn: asyncpg.Connection, pool: asyncpg.Pool) -> None:
        """Initialize transaction."""
        self.conn = conn
        self.pool = pool
        self.transaction: Optional[asyncpg.transaction.Transaction] = None
    
    async def __aenter__(self) -> asyncpg.Connection:
        """Start transaction."""
        self.transaction = self.conn.transaction()
        await self.transaction.start()
        return self.conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """End transaction."""
        try:
            if exc_type is None:
                await self.transaction.commit()
            else:
                await self.transaction.rollback()
        finally:
            await self.pool.release(self.conn)
    
    async def commit(self) -> None:
        """Commit transaction."""
        if self.transaction:
            await self.transaction.commit()
    
    async def rollback(self) -> None:
        """Rollback transaction."""
        if self.transaction:
            await self.transaction.rollback()