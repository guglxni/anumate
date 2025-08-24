"""PostgreSQL Row Level Security Policies

A.6 Multi-tenant Security: RLS policies for tenant isolation
and role-based access control.
"""

-- Enable RLS on all tables
ALTER TABLE capsules ENABLE ROW LEVEL SECURITY;
ALTER TABLE capsule_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE capsule_blobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE capsule_audit_log ENABLE ROW LEVEL SECURITY;

-- Create role hierarchy
DO $$
BEGIN
    -- Create roles if they don't exist
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anumate_viewer') THEN
        CREATE ROLE anumate_viewer;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anumate_editor') THEN
        CREATE ROLE anumate_editor;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anumate_admin') THEN
        CREATE ROLE anumate_admin;
    END IF;
    
    -- Set up role hierarchy
    GRANT anumate_viewer TO anumate_editor;
    GRANT anumate_editor TO anumate_admin;
END
$$;

-- Grant base permissions
GRANT SELECT ON capsules TO anumate_viewer;
GRANT SELECT ON capsule_versions TO anumate_viewer;
GRANT SELECT ON capsule_blobs TO anumate_viewer;
GRANT SELECT ON capsule_audit_log TO anumate_viewer;

GRANT INSERT, UPDATE ON capsules TO anumate_editor;
GRANT INSERT ON capsule_versions TO anumate_editor;
GRANT INSERT ON capsule_blobs TO anumate_editor;
GRANT INSERT ON capsule_audit_log TO anumate_editor;

GRANT DELETE ON capsules TO anumate_admin;
GRANT DELETE ON capsule_versions TO anumate_admin;
GRANT DELETE ON capsule_blobs TO anumate_admin;

-- Tenant isolation policies for capsules
CREATE POLICY capsules_tenant_isolation ON capsules
    FOR ALL
    TO anumate_viewer
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Visibility-based access for capsules
CREATE POLICY capsules_visibility_access ON capsules
    FOR SELECT
    TO anumate_viewer
    USING (
        tenant_id = current_setting('app.current_tenant_id')::uuid
        OR (
            visibility = 'PUBLIC'
            AND status = 'ACTIVE'
        )
        OR (
            visibility = 'ORGANIZATION'
            AND status = 'ACTIVE'
            AND current_setting('app.current_org_id', true)::uuid IS NOT NULL
        )
    );

-- Owner-based modification for capsules
CREATE POLICY capsules_owner_modify ON capsules
    FOR UPDATE
    TO anumate_editor
    USING (
        tenant_id = current_setting('app.current_tenant_id')::uuid
        AND (
            owner = current_setting('app.current_user_id')
            OR pg_has_role('anumate_admin', 'member')
        )
    );

-- Tenant isolation for versions (inherits from capsule)
CREATE POLICY versions_tenant_isolation ON capsule_versions
    FOR ALL
    TO anumate_viewer
    USING (
        EXISTS (
            SELECT 1 FROM capsules c 
            WHERE c.id = capsule_versions.capsule_id 
            AND c.tenant_id = current_setting('app.current_tenant_id')::uuid
        )
    );

-- Blob access based on version access
CREATE POLICY blobs_version_access ON capsule_blobs
    FOR SELECT
    TO anumate_viewer
    USING (
        EXISTS (
            SELECT 1 FROM capsule_versions cv
            JOIN capsules c ON c.id = cv.capsule_id
            WHERE cv.content_hash = capsule_blobs.content_hash
            AND c.tenant_id = current_setting('app.current_tenant_id')::uuid
        )
    );

-- Audit log tenant isolation
CREATE POLICY audit_tenant_isolation ON capsule_audit_log
    FOR ALL
    TO anumate_viewer
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Admin override policies (bypass tenant isolation for admins)
CREATE POLICY admin_override_capsules ON capsules
    FOR ALL
    TO anumate_admin
    USING (pg_has_role('anumate_admin', 'member'));

CREATE POLICY admin_override_versions ON capsule_versions
    FOR ALL
    TO anumate_admin
    USING (pg_has_role('anumate_admin', 'member'));

CREATE POLICY admin_override_blobs ON capsule_blobs
    FOR ALL
    TO anumate_admin
    USING (pg_has_role('anumate_admin', 'member'));

CREATE POLICY admin_override_audit ON capsule_audit_log
    FOR ALL
    TO anumate_admin
    USING (pg_has_role('anumate_admin', 'member'));

-- Function to set session context
CREATE OR REPLACE FUNCTION set_session_context(
    p_tenant_id uuid,
    p_user_id text,
    p_org_id uuid DEFAULT NULL
) RETURNS void AS $$
BEGIN
    PERFORM set_config('app.current_tenant_id', p_tenant_id::text, true);
    PERFORM set_config('app.current_user_id', p_user_id, true);
    
    IF p_org_id IS NOT NULL THEN
        PERFORM set_config('app.current_org_id', p_org_id::text, true);
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant execute permission on the context function
GRANT EXECUTE ON FUNCTION set_session_context TO anumate_viewer;
