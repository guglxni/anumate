-- Create core tables with RLS policies
-- This script creates the multi-tenant table structure

-- Tenants table (root of tenant hierarchy)
CREATE TABLE tenants (
    tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',
    data_residency_region VARCHAR(50) DEFAULT 'us-east-1',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    active BOOLEAN DEFAULT true
);

-- Users table with tenant isolation
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    external_id VARCHAR(255),
    email VARCHAR(255) NOT NULL,
    profile JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE,
    active BOOLEAN DEFAULT true,
    UNIQUE(tenant_id, email),
    UNIQUE(tenant_id, external_id)
);

-- Teams table with hierarchical structure
CREATE TABLE teams (
    team_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    parent_team_id UUID REFERENCES teams(team_id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);

-- Roles table for RBAC
CREATE TABLE roles (
    role_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    permissions JSONB DEFAULT '{}',
    scope VARCHAR(50) DEFAULT 'tenant',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);

-- User roles junction table
CREATE TABLE user_roles (
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(team_id) ON DELETE CASCADE,
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Create unique constraint for user_roles
ALTER TABLE user_roles ADD CONSTRAINT user_roles_unique 
    EXCLUDE (user_id WITH =, role_id WITH =, COALESCE(team_id, '00000000-0000-0000-0000-000000000000'::UUID) WITH =);

-- Capsules table for automation definitions
CREATE TABLE capsules (
    capsule_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    definition JSONB NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    active BOOLEAN DEFAULT true,
    validation_status VARCHAR(50) DEFAULT 'pending',
    validation_errors JSONB DEFAULT '[]',
    UNIQUE(tenant_id, name, version)
);

-- Capsule approvals table for approval workflow
CREATE TABLE capsule_approvals (
    approval_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    capsule_id UUID NOT NULL REFERENCES capsules(capsule_id) ON DELETE CASCADE,
    requester_id UUID NOT NULL REFERENCES users(user_id),
    approver_id UUID REFERENCES users(user_id),
    status VARCHAR(50) DEFAULT 'pending',
    approval_metadata JSONB DEFAULT '{}',
    rejection_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    approved_at TIMESTAMP WITH TIME ZONE
);

-- Plans table for compiled capsules
CREATE TABLE plans (
    plan_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    capsule_id UUID NOT NULL REFERENCES capsules(capsule_id) ON DELETE CASCADE,
    version VARCHAR(50) NOT NULL,
    compiled_definition JSONB NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'compiled'
);

-- Runs table for plan executions
CREATE TABLE runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    external_run_id VARCHAR(255),
    parameters JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'pending',
    results JSONB DEFAULT '{}',
    triggered_by UUID NOT NULL REFERENCES users(user_id),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Approvals table for workflow approvals
CREATE TABLE approvals (
    approval_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    approver_id UUID NOT NULL REFERENCES users(user_id),
    status VARCHAR(50) DEFAULT 'pending',
    metadata JSONB DEFAULT '{}',
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    responded_at TIMESTAMP WITH TIME ZONE,
    response_reason TEXT
);

-- Capability tokens table
CREATE TABLE capability_tokens (
    token_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    capabilities JSONB NOT NULL,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE,
    active BOOLEAN DEFAULT true
);

-- Connectors table for external integrations
CREATE TABLE connectors (
    connector_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100) NOT NULL,
    configuration_encrypted JSONB NOT NULL,
    kms_key_id VARCHAR(255) NOT NULL,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    active BOOLEAN DEFAULT true,
    UNIQUE(tenant_id, name)
);

-- Policies table for Policy DSL definitions
CREATE TABLE policies (
    policy_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    source_code TEXT NOT NULL,
    compiled_ast JSONB,
    metadata JSONB DEFAULT '{}',
    enabled BOOLEAN DEFAULT true,
    version INTEGER DEFAULT 1,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_evaluated_at TIMESTAMP WITH TIME ZONE,
    evaluation_count INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT true,
    UNIQUE(tenant_id, name)
);

-- Events table for audit and event sourcing
CREATE TABLE events.events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    entity_id UUID,
    entity_type VARCHAR(100),
    payload JSONB NOT NULL,
    actor_id UUID,
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    correlation_id UUID
);

-- Receipts table for immutable audit records
CREATE TABLE audit.receipts (
    receipt_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    receipt_type VARCHAR(100) NOT NULL,
    content_hash JSONB NOT NULL,
    digital_signature JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    immutable_reference VARCHAR(255) NOT NULL UNIQUE
);

-- Usage table for billing and metering
CREATE TABLE usage (
    usage_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    metric_name VARCHAR(100) NOT NULL,
    value DECIMAL(15,4) NOT NULL,
    dimensions JSONB DEFAULT '{}',
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    billing_period VARCHAR(20) NOT NULL
);

-- Create indexes for performance
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_email ON users(tenant_id, email);
CREATE INDEX idx_teams_tenant_id ON teams(tenant_id);
CREATE INDEX idx_roles_tenant_id ON roles(tenant_id);
CREATE INDEX idx_capsules_tenant_id ON capsules(tenant_id);
CREATE INDEX idx_capsule_approvals_tenant_id ON capsule_approvals(tenant_id);
CREATE INDEX idx_capsule_approvals_status ON capsule_approvals(tenant_id, status);
CREATE INDEX idx_plans_tenant_id ON plans(tenant_id);
CREATE INDEX idx_runs_tenant_id ON runs(tenant_id);
CREATE INDEX idx_runs_status ON runs(tenant_id, status);
CREATE INDEX idx_approvals_tenant_id ON approvals(tenant_id);
CREATE INDEX idx_capability_tokens_tenant_id ON capability_tokens(tenant_id);
CREATE INDEX idx_connectors_tenant_id ON connectors(tenant_id);
CREATE INDEX idx_policies_tenant_id ON policies(tenant_id);
CREATE INDEX idx_policies_name ON policies(tenant_id, name);
CREATE INDEX idx_policies_enabled ON policies(tenant_id, enabled);
CREATE INDEX idx_events_tenant_id ON events.events(tenant_id);
CREATE INDEX idx_events_occurred_at ON events.events(occurred_at);
CREATE INDEX idx_receipts_tenant_id ON audit.receipts(tenant_id);
CREATE INDEX idx_usage_tenant_id ON usage(tenant_id);
CREATE INDEX idx_usage_billing_period ON usage(tenant_id, billing_period);