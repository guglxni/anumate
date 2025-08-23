#!/usr/bin/env python3
"""
Create Receipt Service Database Tables - Direct SQL
===================================================

Direct database script to create Receipt service tables without importing the full application.
"""

import asyncpg
import asyncio

async def create_receipt_tables():
    """Create Receipt service tables directly with SQL."""
    
    # Connect to database
    conn = await asyncpg.connect(
        host='127.0.0.1',
        port=5432,
        user='anumate_admin',
        password='dev_password',
        database='anumate'
    )
    
    try:
        print("🔗 Connected to database")
        
        # Create receipts table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            receipt_type VARCHAR(100) NOT NULL,
            subject VARCHAR(255) NOT NULL,
            reference_id UUID,
            receipt_data JSONB NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            signature TEXT NOT NULL,
            signing_key_id VARCHAR(100) NOT NULL,
            worm_storage_path VARCHAR(500),
            worm_written_at TIMESTAMPTZ,
            worm_verified_at TIMESTAMPTZ,
            retention_until TIMESTAMPTZ,
            compliance_tags JSONB,
            is_verified BOOLEAN NOT NULL DEFAULT TRUE,
            verification_failures INTEGER NOT NULL DEFAULT 0,
            last_verified_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        ''')
        print("📊 Created receipts table")
        
        # Create receipt audit logs table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS receipt_audit_logs (
            audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            receipt_id UUID,
            tenant_id UUID NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            event_source VARCHAR(100) NOT NULL,
            user_id VARCHAR(255),
            client_ip VARCHAR(45),
            user_agent TEXT,
            request_id VARCHAR(100),
            event_data JSONB,
            success BOOLEAN NOT NULL DEFAULT TRUE,
            error_message TEXT,
            processing_time_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (receipt_id) REFERENCES receipts(receipt_id)
        )
        ''')
        print("📊 Created receipt_audit_logs table")
        
        # Create retention policies table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS retention_policies (
            policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            policy_name VARCHAR(100) NOT NULL,
            receipt_types JSONB NOT NULL,
            retention_days INTEGER NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            priority INTEGER NOT NULL DEFAULT 100,
            description TEXT,
            compliance_requirements JSONB,
            auto_delete BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        ''')
        print("📊 Created retention_policies table")
        
        # Create WORM storage records table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS worm_storage_records (
            worm_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            receipt_id UUID NOT NULL,
            tenant_id UUID NOT NULL,
            storage_provider VARCHAR(50) NOT NULL,
            storage_path VARCHAR(500) NOT NULL,
            storage_checksum VARCHAR(64) NOT NULL,
            written_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            written_by VARCHAR(255),
            write_transaction_id VARCHAR(100),
            last_verified_at TIMESTAMPTZ,
            verification_count INTEGER NOT NULL DEFAULT 0,
            verification_failures INTEGER NOT NULL DEFAULT 0,
            is_accessible BOOLEAN NOT NULL DEFAULT TRUE,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (receipt_id) REFERENCES receipts(receipt_id)
        )
        ''')
        print("📊 Created worm_storage_records table")
        
        # Create indexes
        indexes = [
            # Receipts indexes
            "CREATE INDEX IF NOT EXISTS idx_receipts_tenant ON receipts(tenant_id)",
            "CREATE INDEX IF NOT EXISTS idx_receipts_type ON receipts(receipt_type)",
            "CREATE INDEX IF NOT EXISTS idx_receipts_subject ON receipts(subject)",
            "CREATE INDEX IF NOT EXISTS idx_receipts_reference ON receipts(reference_id)",
            "CREATE INDEX IF NOT EXISTS idx_receipts_hash ON receipts(content_hash)",
            "CREATE INDEX IF NOT EXISTS idx_receipts_created ON receipts(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_receipts_retention ON receipts(retention_until)",
            "CREATE INDEX IF NOT EXISTS idx_receipts_verification ON receipts(is_verified, last_verified_at)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_receipts_tenant_hash ON receipts(tenant_id, content_hash)",
            
            # Audit logs indexes
            "CREATE INDEX IF NOT EXISTS idx_receipt_audit_tenant ON receipt_audit_logs(tenant_id)",
            "CREATE INDEX IF NOT EXISTS idx_receipt_audit_receipt ON receipt_audit_logs(receipt_id)",
            "CREATE INDEX IF NOT EXISTS idx_receipt_audit_event ON receipt_audit_logs(event_type)",
            "CREATE INDEX IF NOT EXISTS idx_receipt_audit_created ON receipt_audit_logs(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_receipt_audit_user ON receipt_audit_logs(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_receipt_audit_source ON receipt_audit_logs(event_source)",
            "CREATE INDEX IF NOT EXISTS idx_receipt_audit_success ON receipt_audit_logs(success)",
            
            # Retention policies indexes
            "CREATE INDEX IF NOT EXISTS idx_retention_policies_tenant ON retention_policies(tenant_id)",
            "CREATE INDEX IF NOT EXISTS idx_retention_policies_active ON retention_policies(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_retention_policies_priority ON retention_policies(priority)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_retention_policies_tenant_name ON retention_policies(tenant_id, policy_name)",
            
            # WORM storage indexes
            "CREATE INDEX IF NOT EXISTS idx_worm_storage_tenant ON worm_storage_records(tenant_id)",
            "CREATE INDEX IF NOT EXISTS idx_worm_storage_receipt ON worm_storage_records(receipt_id)",
            "CREATE INDEX IF NOT EXISTS idx_worm_storage_provider ON worm_storage_records(storage_provider)",
            "CREATE INDEX IF NOT EXISTS idx_worm_storage_written ON worm_storage_records(written_at)",
            "CREATE INDEX IF NOT EXISTS idx_worm_storage_verified ON worm_storage_records(last_verified_at)",
            "CREATE INDEX IF NOT EXISTS idx_worm_storage_accessible ON worm_storage_records(is_accessible)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_worm_storage_provider_path ON worm_storage_records(storage_provider, storage_path)"
        ]
        
        for index_sql in indexes:
            await conn.execute(index_sql)
        print(f"📊 Created {len(indexes)} indexes")
        
        print("✅ Receipt service database setup complete!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(create_receipt_tables())
