"""
Synchronous Database Setup for CapTokens Service
================================================

Creates the database tables using synchronous connections.
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def create_captokens_tables():
    """Create CapTokens service tables using synchronous connection."""
    try:
        print("🗄️  Starting CapTokens database setup...")
        
        # Connection parameters
        conn_params = {
            'host': 'localhost',
            'port': 5432,
            'database': 'anumate',
            'user': 'anumate_app',
            'password': 'app_password'
        }
        
        print(f"Connecting to PostgreSQL at {conn_params['host']}:{conn_params['port']}")
        
        # Connect to database
        conn = psycopg2.connect(**conn_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        print("Creating CapTokens service tables...")
        
        # Create capability_tokens table
        cur.execute("""
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_capability_tokens_tenant_id ON capability_tokens(tenant_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_capability_tokens_hash ON capability_tokens(token_hash);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_capability_tokens_expires_at ON capability_tokens(expires_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_capability_tokens_active ON capability_tokens(tenant_id, active);")
        
        # Create token_audit_logs table
        cur.execute("""
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_token_audit_logs_tenant_id ON token_audit_logs(tenant_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_token_audit_logs_token_id ON token_audit_logs(token_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_token_audit_logs_created_at ON token_audit_logs(created_at);")
        
        # Create replay_protection table
        cur.execute("""
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_replay_protection_token_jti ON replay_protection(token_jti);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_replay_protection_expires_at ON replay_protection(expires_at);")
        
        # Create cleanup jobs table
        cur.execute("""
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
        
        cur.close()
        conn.close()
        
        print("✅ CapTokens database tables created successfully!")
        print("✅ Database setup completed!")
        
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        raise


if __name__ == "__main__":
    create_captokens_tables()
