"""
Database Migration Script for CapTokens Service
===============================================

Initializes the database with production-grade schema.
"""

import asyncio
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from anumate_captokens_service.models import Base
from anumate_captokens_service.database import DATABASE_URL
from anumate_logging import get_logger

logger = get_logger(__name__)


async def migrate_database():
    """Run database migrations."""
    try:
        logger.info("Starting database migration...")
        logger.info(f"Database URL: {DATABASE_URL}")
        
        # Create engine
        engine = create_async_engine(DATABASE_URL, echo=True)
        
        # Create all tables
        async with engine.begin() as conn:
            logger.info("Creating database tables...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
        
        await engine.dispose()
        logger.info("Database migration completed successfully")
        
    except Exception as e:
        logger.error(f"Database migration failed: {e}")
        raise


async def main():
    """Main migration entry point."""
    await migrate_database()


if __name__ == "__main__":
    asyncio.run(main())
