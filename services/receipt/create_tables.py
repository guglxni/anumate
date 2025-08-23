#!/usr/bin/env python3
"""
Create Receipt Service Database Tables
=====================================

Simple script to create the Receipt service database tables.
"""

import asyncio
import sys
import os

# Add packages to path
sys.path.insert(0, '/Users/aaryanguglani/anumate/packages/anumate-crypto')
sys.path.insert(0, '/Users/aaryanguglani/anumate/packages/anumate-receipt') 
sys.path.insert(0, '/Users/aaryanguglani/anumate/packages/anumate-errors')
sys.path.insert(0, '/Users/aaryanguglani/anumate/packages/anumate-core-config')
sys.path.insert(0, '/Users/aaryanguglani/anumate/services/receipt/src')

async def create_tables():
    """Create the Receipt service database tables."""
    from anumate_receipt_service.database import init_database, create_tables
    
    try:
        # Database URL
        database_url = "postgresql+asyncpg://anumate_admin:dev_password@localhost:5432/anumate"
        
        print("🔗 Initializing database connection...")
        await init_database(database_url)
        
        print("📊 Creating Receipt service tables...")
        await create_tables()
        
        print("✅ Receipt service database setup complete!")
        
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(create_tables())
