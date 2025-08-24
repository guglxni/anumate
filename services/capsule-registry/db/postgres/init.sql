-- PostgreSQL initialization script for Capsule Registry
-- Sets up database users, permissions, and initial configuration

-- Create service user if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'capsule_registry') THEN
        CREATE ROLE capsule_registry WITH LOGIN PASSWORD 'capsule_registry_dev_password';
    END IF;
END
$$;

-- Create database if it doesn't exist  
SELECT 'CREATE DATABASE capsule_registry OWNER capsule_registry'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'capsule_registry')\gexec

-- Connect to the capsule_registry database
\c capsule_registry

-- Grant necessary permissions
GRANT CONNECT ON DATABASE capsule_registry TO capsule_registry;
GRANT USAGE ON SCHEMA public TO capsule_registry;
GRANT CREATE ON SCHEMA public TO capsule_registry;

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create function to set tenant context for RLS
CREATE OR REPLACE FUNCTION set_tenant_context(tenant_uuid UUID)
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('anumate.tenant_id', tenant_uuid::text, true);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant execute permission on the function
GRANT EXECUTE ON FUNCTION set_tenant_context(UUID) TO capsule_registry;

-- Create function to get current tenant context
CREATE OR REPLACE FUNCTION get_tenant_context()
RETURNS UUID AS $$
BEGIN
    RETURN current_setting('anumate.tenant_id', true)::uuid;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant execute permission on the function
GRANT EXECUTE ON FUNCTION get_tenant_context() TO capsule_registry;

-- Ensure capsule_registry user owns all objects in public schema
ALTER SCHEMA public OWNER TO capsule_registry;
