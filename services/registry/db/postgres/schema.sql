-- Capsule Registry PostgreSQL Schema with Row Level Security
-- A.4–A.6 Implementation: Multi-tenant capsule storage with RBAC

-- Create custom types
CREATE TYPE capsule_status AS ENUM ('active', 'deleted');
CREATE TYPE capsule_visibility AS ENUM ('private', 'organization', 'public');

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Main capsules table with tenant isolation
CREATE TABLE capsules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    owner VARCHAR(255) NOT NULL,
    status capsule_status NOT NULL DEFAULT 'active',
    visibility capsule_visibility NOT NULL DEFAULT 'private',
    latest_version INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255) NOT NULL,
    updated_by VARCHAR(255) NOT NULL,
    etag VARCHAR(64) NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
    
    CONSTRAINT uq_capsules_tenant_name UNIQUE (tenant_id, name)
);

-- Capsule versions for immutable versioning
CREATE TABLE capsule_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    capsule_id UUID NOT NULL REFERENCES capsules(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    signature VARCHAR(256),
    pubkey_id VARCHAR(64),
    uri VARCHAR(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255) NOT NULL,
    
    CONSTRAINT uq_versions_capsule_version UNIQUE (capsule_id, version)
);

-- Immutable content blobs (WORM)
CREATE TABLE capsule_blobs (
    content_hash VARCHAR(64) PRIMARY KEY,
    yaml_text TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit trail for all operations
CREATE TABLE capsule_audit (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    capsule_id UUID REFERENCES capsules(id) ON DELETE SET NULL,
    version_id UUID REFERENCES capsule_versions(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    actor VARCHAR(255) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trace_id VARCHAR(64)
);

-- Idempotency tracking
CREATE TABLE idempotency_keys (
    key VARCHAR(255) PRIMARY KEY,
    tenant_id UUID NOT NULL,
    endpoint VARCHAR(100) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    response_data JSONB NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Indexes for performance
CREATE INDEX idx_capsules_tenant_id ON capsules(tenant_id);
CREATE INDEX idx_capsules_status ON capsules(status);
CREATE INDEX idx_capsules_updated_at ON capsules(updated_at);
CREATE INDEX idx_capsules_tags ON capsules USING GIN(tags);

CREATE INDEX idx_versions_capsule_id ON capsule_versions(capsule_id);
CREATE INDEX idx_versions_content_hash ON capsule_versions(content_hash);
CREATE INDEX idx_versions_created_at ON capsule_versions(created_at);

CREATE INDEX idx_audit_tenant_id ON capsule_audit(tenant_id);
CREATE INDEX idx_audit_capsule_id ON capsule_audit(capsule_id);
CREATE INDEX idx_audit_timestamp ON capsule_audit(timestamp);
CREATE INDEX idx_audit_action ON capsule_audit(action);

CREATE INDEX idx_idempotency_tenant_endpoint ON idempotency_keys(tenant_id, endpoint);
CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);

-- Row Level Security Policies
ALTER TABLE capsules ENABLE ROW LEVEL SECURITY;
ALTER TABLE capsule_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE capsule_blobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE capsule_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY;

-- Tenant isolation for capsules
CREATE POLICY tenant_isolation_capsules ON capsules
    FOR ALL
    USING (tenant_id = current_setting('anumate.tenant_id')::uuid);

-- Visibility-based access for public/organization capsules
CREATE POLICY visibility_access_capsules ON capsules
    FOR SELECT
    USING (
        tenant_id = current_setting('anumate.tenant_id')::uuid
        OR (visibility = 'public' AND status = 'active')
        OR (
            visibility = 'organization' 
            AND status = 'active'
            AND current_setting('anumate.org_id', true) IS NOT NULL
        )
    );

-- Versions inherit capsule access
CREATE POLICY tenant_isolation_versions ON capsule_versions
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM capsules c 
            WHERE c.id = capsule_versions.capsule_id 
            AND c.tenant_id = current_setting('anumate.tenant_id')::uuid
        )
    );

-- Blobs accessible if user has access to any version using them
CREATE POLICY blob_access ON capsule_blobs
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM capsule_versions cv
            JOIN capsules c ON c.id = cv.capsule_id
            WHERE cv.content_hash = capsule_blobs.content_hash
            AND c.tenant_id = current_setting('anumate.tenant_id')::uuid
        )
    );

-- Audit log tenant isolation
CREATE POLICY tenant_isolation_audit ON capsule_audit
    FOR ALL
    USING (tenant_id = current_setting('anumate.tenant_id')::uuid);

-- Idempotency tenant isolation
CREATE POLICY tenant_isolation_idempotency ON idempotency_keys
    FOR ALL
    USING (tenant_id = current_setting('anumate.tenant_id')::uuid);

-- Update triggers for etag and updated_at
CREATE OR REPLACE FUNCTION update_capsule_metadata()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.etag = encode(gen_random_bytes(32), 'hex');
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER tr_update_capsule_metadata
    BEFORE UPDATE ON capsules
    FOR EACH ROW
    EXECUTE FUNCTION update_capsule_metadata();

-- Function to set tenant context
CREATE OR REPLACE FUNCTION set_tenant_context(p_tenant_id UUID, p_org_id UUID DEFAULT NULL)
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('anumate.tenant_id', p_tenant_id::TEXT, true);
    IF p_org_id IS NOT NULL THEN
        PERFORM set_config('anumate.org_id', p_org_id::TEXT, true);
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Cleanup function for expired idempotency keys
CREATE OR REPLACE FUNCTION cleanup_expired_idempotency_keys()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM idempotency_keys WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
