-- A.27 Audit Service Database Initialization
-- PostgreSQL initialization script for production deployment

-- Create audit database (if using superuser)
-- CREATE DATABASE audit_db OWNER audit;

-- Connect to the audit database
\c audit_db;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create audit user with limited privileges (if not exists)
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'audit') THEN
      CREATE ROLE audit LOGIN PASSWORD 'audit_pass';
   END IF;
END
$$;

-- Grant necessary permissions
GRANT CREATE, CONNECT ON DATABASE audit_db TO audit;
GRANT USAGE, CREATE ON SCHEMA public TO audit;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO audit;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO audit;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO audit;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO audit;

-- Create read-only user for reporting
CREATE ROLE audit_reader LOGIN PASSWORD 'reader_pass';
GRANT CONNECT ON DATABASE audit_db TO audit_reader;
GRANT USAGE ON SCHEMA public TO audit_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO audit_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO audit_reader;

-- Performance optimizations
-- Increase work_mem for better query performance
ALTER DATABASE audit_db SET work_mem = '64MB';

-- Configure for audit logging workload
ALTER DATABASE audit_db SET random_page_cost = 1.1;
ALTER DATABASE audit_db SET effective_cache_size = '2GB';

-- Create tablespaces for better I/O distribution (optional)
-- CREATE TABLESPACE audit_events LOCATION '/var/lib/postgresql/tablespaces/audit_events';
-- CREATE TABLESPACE audit_indexes LOCATION '/var/lib/postgresql/tablespaces/audit_indexes';

COMMIT;
