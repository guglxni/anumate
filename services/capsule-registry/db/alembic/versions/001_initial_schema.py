"""Initial Capsule Registry schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2024-12-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial Capsule Registry schema."""
    
    # Create enums
    op.execute("""
        CREATE TYPE capsule_status AS ENUM ('ACTIVE', 'DELETED');
        CREATE TYPE capsule_visibility AS ENUM ('PRIVATE', 'ORG');
    """)
    
    # Capsules table
    op.create_table('capsules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.String(length=100)), nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=False),
        sa.Column('visibility', postgresql.ENUM('PRIVATE', 'ORG', name='capsule_visibility'), nullable=False),
        sa.Column('status', postgresql.ENUM('ACTIVE', 'DELETED', name='capsule_status'), nullable=False),
        sa.Column('latest_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('etag', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_capsules_tenant_name')
    )
    
    # Indexes for capsules
    op.create_index('idx_capsules_tenant_status', 'capsules', ['tenant_id', 'status'])
    op.create_index('idx_capsules_tenant_owner', 'capsules', ['tenant_id', 'owner'])
    op.create_index('idx_capsules_tenant_visibility', 'capsules', ['tenant_id', 'visibility'])
    op.create_index('idx_capsules_updated_at', 'capsules', ['updated_at'])
    op.create_index('idx_capsules_tags_gin', 'capsules', ['tags'], postgresql_using='gin')
    
    # Capsule versions table
    op.create_table('capsule_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('capsule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('signature', sa.Text(), nullable=False),
        sa.Column('pubkey_id', sa.String(length=255), nullable=False),
        sa.Column('uri', sa.String(length=500), nullable=False),
        sa.Column('message', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(['capsule_id'], ['capsules.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'capsule_id', 'version', name='uq_capsule_versions_tenant_capsule_version')
    )
    
    # Indexes for capsule_versions
    op.create_index('idx_capsule_versions_tenant_capsule', 'capsule_versions', ['tenant_id', 'capsule_id'])
    op.create_index('idx_capsule_versions_content_hash', 'capsule_versions', ['content_hash'])
    op.create_index('idx_capsule_versions_created_at', 'capsule_versions', ['created_at'])
    
    # Capsule blobs table (for YAML content storage)
    op.create_table('capsule_blobs',
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('yaml_text', sa.Text(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ref_count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('content_hash', 'tenant_id'),
    )
    
    # Indexes for capsule_blobs
    op.create_index('idx_capsule_blobs_tenant', 'capsule_blobs', ['tenant_id'])
    op.create_index('idx_capsule_blobs_created_at', 'capsule_blobs', ['created_at'])
    
    # Capsule audit table
    op.create_table('capsule_audit',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('capsule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('actor', sa.String(length=255), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['capsule_id'], ['capsules.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indexes for capsule_audit
    op.create_index('idx_capsule_audit_tenant_capsule', 'capsule_audit', ['tenant_id', 'capsule_id'])
    op.create_index('idx_capsule_audit_created_at', 'capsule_audit', ['created_at'])
    op.create_index('idx_capsule_audit_actor', 'capsule_audit', ['actor'])
    op.create_index('idx_capsule_audit_action', 'capsule_audit', ['action'])
    
    # Row Level Security (RLS) policies
    op.execute("""
        -- Enable RLS on all tables
        ALTER TABLE capsules ENABLE ROW LEVEL SECURITY;
        ALTER TABLE capsule_versions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE capsule_blobs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE capsule_audit ENABLE ROW LEVEL SECURITY;
        
        -- RLS policies for capsules
        CREATE POLICY capsules_tenant_policy ON capsules 
            FOR ALL TO PUBLIC 
            USING (tenant_id = current_setting('anumate.tenant_id')::uuid);
        
        -- RLS policies for capsule_versions
        CREATE POLICY capsule_versions_tenant_policy ON capsule_versions 
            FOR ALL TO PUBLIC 
            USING (tenant_id = current_setting('anumate.tenant_id')::uuid);
        
        -- RLS policies for capsule_blobs
        CREATE POLICY capsule_blobs_tenant_policy ON capsule_blobs 
            FOR ALL TO PUBLIC 
            USING (tenant_id = current_setting('anumate.tenant_id')::uuid);
        
        -- RLS policies for capsule_audit
        CREATE POLICY capsule_audit_tenant_policy ON capsule_audit 
            FOR ALL TO PUBLIC 
            USING (tenant_id = current_setting('anumate.tenant_id')::uuid);
    """)


def downgrade() -> None:
    """Drop Capsule Registry schema."""
    
    # Drop tables in reverse order
    op.drop_table('capsule_audit')
    op.drop_table('capsule_blobs')
    op.drop_table('capsule_versions')
    op.drop_table('capsules')
    
    # Drop enums
    op.execute("DROP TYPE IF EXISTS capsule_status CASCADE;")
    op.execute("DROP TYPE IF EXISTS capsule_visibility CASCADE;")
