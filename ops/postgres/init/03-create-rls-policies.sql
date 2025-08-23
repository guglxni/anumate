-- Enable Row Level Security (RLS) policies for multi-tenant isolation
-- This script creates RLS policies for all tenant-aware tables

-- Enable RLS on all tenant-aware tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE capsules ENABLE ROW LEVEL SECURITY;
ALTER TABLE capsule_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE capability_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE connectors ENABLE ROW LEVEL SECURITY;
ALTER TABLE policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE events.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit.receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for tenant isolation

-- Users table policies
CREATE POLICY tenant_isolation_users ON users
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_users ON users
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Teams table policies
CREATE POLICY tenant_isolation_teams ON teams
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_teams ON teams
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Roles table policies
CREATE POLICY tenant_isolation_roles ON roles
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_roles ON roles
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- User roles table policies (inherits tenant_id from users/roles)
CREATE POLICY tenant_isolation_user_roles ON user_roles
    FOR ALL TO anumate_app
    USING (
        user_id IN (SELECT user_id FROM users WHERE tenant_id = get_current_tenant_id())
        AND role_id IN (SELECT role_id FROM roles WHERE tenant_id = get_current_tenant_id())
    );

CREATE POLICY readonly_user_roles ON user_roles
    FOR SELECT TO anumate_readonly
    USING (
        user_id IN (SELECT user_id FROM users WHERE tenant_id = get_current_tenant_id())
        AND role_id IN (SELECT role_id FROM roles WHERE tenant_id = get_current_tenant_id())
    );

-- Capsules table policies
CREATE POLICY tenant_isolation_capsules ON capsules
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_capsules ON capsules
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Capsule approvals table policies
CREATE POLICY tenant_isolation_capsule_approvals ON capsule_approvals
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_capsule_approvals ON capsule_approvals
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Plans table policies
CREATE POLICY tenant_isolation_plans ON plans
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_plans ON plans
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Runs table policies
CREATE POLICY tenant_isolation_runs ON runs
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_runs ON runs
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Approvals table policies
CREATE POLICY tenant_isolation_approvals ON approvals
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_approvals ON approvals
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Capability tokens table policies
CREATE POLICY tenant_isolation_capability_tokens ON capability_tokens
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_capability_tokens ON capability_tokens
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Connectors table policies
CREATE POLICY tenant_isolation_connectors ON connectors
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_connectors ON connectors
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Policies table policies
CREATE POLICY tenant_isolation_policies ON policies
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_policies ON policies
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Events table policies
CREATE POLICY tenant_isolation_events ON events.events
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_events ON events.events
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Receipts table policies (audit schema)
CREATE POLICY tenant_isolation_receipts ON audit.receipts
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_receipts ON audit.receipts
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Usage table policies
CREATE POLICY tenant_isolation_usage ON usage
    FOR ALL TO anumate_app
    USING (tenant_id = get_current_tenant_id());

CREATE POLICY readonly_usage ON usage
    FOR SELECT TO anumate_readonly
    USING (tenant_id = get_current_tenant_id());

-- Grant table permissions to application roles
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anumate_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA events TO anumate_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA audit TO anumate_app;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO anumate_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA events TO anumate_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA audit TO anumate_readonly;

-- Grant sequence permissions
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anumate_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA events TO anumate_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA audit TO anumate_app;