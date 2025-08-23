"""
Simple Database Migration for CapTokens Service
===============================================

Creates the database tables directly using the infrastructure database.
"""

import asyncio
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sqlalchemy.ext.asyncio import create_async_engine

# Database URL for production setup
DATABASE_URL = "postgresql+asyncpg://anumate_user:anumate_password@localhost:5432/anumate_db"


async def create_captokens_tables():
    """Create CapTokens service tables in the existing database."""
    try:
        print("🗄️  Starting CapTokens database setup...")
        print(f"Database URL: {DATABASE_URL}")
        
        # Create engine
        engine = create_async_engine(DATABASE_URL, echo=False)
        
        # Create CapTokens specific tables
        async with engine.begin() as conn:
            print("Creating CapTokens service tables...")
            
            # Create capability_tokens table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS capability_tokens (
                    token_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    tenant_id UUID NOT NULL,
                    token_hash VARCHAR(255) NOT NULL UNIQUE,
                    subject VARCHAR(255) NOT NULL,
                    capabilities JSONB NOT NULL,
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    last_used_at TIMESTAMP WITH TIME ZONE,
                    revoked_at TIMESTAMP WITH TIME ZONE,
                    revoked_by UUID,
                    revocation_reason TEXT,
                    active BOOLEAN NOT NULL DEFAULT true,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    metadata JSONB NOT NULL DEFAULT '{}',
                    created_by UUID NOT NULL,
                    client_ip VARCHAR(45),
                    user_agent TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Create indexes for performance
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_capability_tokens_tenant_id ON capability_tokens(tenant_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_capability_tokens_hash ON capability_tokens(token_hash);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_capability_tokens_expires_at ON capability_tokens(expires_at);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_capability_tokens_active ON capability_tokens(tenant_id, active);
            """)
            
            # Create token_audit_logs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS token_audit_logs (
                    audit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    tenant_id UUID NOT NULL,
                    token_id UUID NOT NULL,
                    operation VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    endpoint VARCHAR(255),
                    http_method VARCHAR(10),
                    client_ip VARCHAR(45),
                    user_agent TEXT,
                    authenticated_subject VARCHAR(255),
                    authentication_method VARCHAR(50),
                    request_data JSONB NOT NULL DEFAULT '{}',
                    response_data JSONB NOT NULL DEFAULT '{}',
                    error_details JSONB,
                    duration_ms INTEGER,
                    correlation_id UUID,
                    trace_id VARCHAR(32),
                    span_id VARCHAR(16),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Create audit log indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_token_audit_logs_tenant_id ON token_audit_logs(tenant_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_token_audit_logs_token_id ON token_audit_logs(token_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_token_audit_logs_created_at ON token_audit_logs(created_at);
            """)
            
            # Create replay_protection table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS replay_protection (
                    nonce_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    token_jti VARCHAR(255) NOT NULL UNIQUE,
                    token_hash VARCHAR(255) NOT NULL,
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    first_seen_ip VARCHAR(45),
                    first_seen_user_agent TEXT,
                    usage_count INTEGER NOT NULL DEFAULT 1,
                    last_used_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Create replay protection indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_replay_protection_token_jti ON replay_protection(token_jti);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_replay_protection_expires_at ON replay_protection(expires_at);
            """)
            
            # Create cleanup jobs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS token_cleanup_jobs (
                    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    job_type VARCHAR(50) NOT NULL DEFAULT 'expired_tokens',
                    status VARCHAR(20) NOT NULL DEFAULT 'running',
                    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMP WITH TIME ZONE,
                    duration_seconds INTEGER,
                    tokens_processed INTEGER NOT NULL DEFAULT 0,
                    tokens_cleaned INTEGER NOT NULL DEFAULT 0,
                    errors_encountered INTEGER NOT NULL DEFAULT 0,
                    cleanup_config JSONB NOT NULL DEFAULT '{}',
                    error_details JSONB,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    next_retry_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            print("✅ CapTokens database tables created successfully!")
        
        await engine.dispose()
        print("✅ Database migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Database migration failed: {e}")
        raise


async def main():
    """Main migration entry point."""
    await create_captokens_tables()


if __name__ == "__main__":
    asyncio.run(main())
