-- Create the main Anumate database and roles
-- This script runs during PostgreSQL initialization

-- Create application roles
CREATE ROLE anumate_app WITH LOGIN PASSWORD 'app_password';
CREATE ROLE anumate_readonly WITH LOGIN PASSWORD 'readonly_password';
CREATE ROLE anumate_migration WITH LOGIN PASSWORD 'migration_password';

-- Grant necessary privileges
GRANT CONNECT ON DATABASE anumate TO anumate_app;
GRANT CONNECT ON DATABASE anumate TO anumate_readonly;
GRANT CONNECT ON DATABASE anumate TO anumate_migration;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS public;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS events;

-- Grant schema usage
GRANT USAGE ON SCHEMA public TO anumate_app, anumate_readonly;
GRANT USAGE ON SCHEMA audit TO anumate_app, anumate_readonly;
GRANT USAGE ON SCHEMA events TO anumate_app, anumate_readonly;

-- Grant creation privileges to migration role
GRANT CREATE ON SCHEMA public TO anumate_migration;
GRANT CREATE ON SCHEMA audit TO anumate_migration;
GRANT CREATE ON SCHEMA events TO anumate_migration;

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create tenant context function for RLS
CREATE OR REPLACE FUNCTION get_current_tenant_id()
RETURNS UUID AS $$
BEGIN
    RETURN COALESCE(
        current_setting('app.current_tenant_id', true)::UUID,
        '00000000-0000-0000-0000-000000000000'::UUID
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;