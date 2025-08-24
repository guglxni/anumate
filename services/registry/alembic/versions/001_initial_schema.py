"""Initial schema for capsule registry

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial capsule registry schema."""
    
    # Create capsules table
    op.create_table('capsules',
        sa.Column('id', sa.UUID(), nullable=False, default=uuid.uuid4),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('owner', sa.String(length=255), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'DELETED', name='capsulestatus'), nullable=False),
        sa.Column('visibility', sa.Enum('PRIVATE', 'ORGANIZATION', 'PUBLIC', name='capsulevisibility'), nullable=False),
        sa.Column('latest_version', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('updated_by', sa.String(length=255), nullable=False),
        sa.Column('etag', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_capsules_tenant_name')
    )
    
    # Create indexes for capsules
    op.create_index('ix_capsules_tenant_id', 'capsules', ['tenant_id'])
    op.create_index('ix_capsules_status', 'capsules', ['status'])
    op.create_index('ix_capsules_updated_at', 'capsules', ['updated_at'])
    op.create_index('ix_capsules_tags', 'capsules', ['tags'], postgresql_using='gin')
    
    # Create capsule_versions table
    op.create_table('capsule_versions',
        sa.Column('id', sa.UUID(), nullable=False, default=uuid.uuid4),
        sa.Column('capsule_id', sa.UUID(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('signature', sa.String(length=128), nullable=False),
        sa.Column('pubkey_id', sa.String(length=64), nullable=False),
        sa.Column('uri', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['capsule_id'], ['capsules.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('capsule_id', 'version', name='uq_versions_capsule_version')
    )
    
    # Create indexes for capsule_versions
    op.create_index('ix_versions_capsule_id', 'capsule_versions', ['capsule_id'])
    op.create_index('ix_versions_content_hash', 'capsule_versions', ['content_hash'])
    op.create_index('ix_versions_created_at', 'capsule_versions', ['created_at'])
    
    # Create capsule_blobs table
    op.create_table('capsule_blobs',
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('yaml_text', sa.Text(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('content_hash')
    )
    
    # Create capsule_audit_log table
    op.create_table('capsule_audit_log',
        sa.Column('id', sa.UUID(), nullable=False, default=uuid.uuid4),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('capsule_id', sa.UUID(), nullable=True),
        sa.Column('version_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('actor', sa.String(length=255), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['capsule_id'], ['capsules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['version_id'], ['capsule_versions.id'], ondelete='SET NULL')
    )
    
    # Create indexes for audit log
    op.create_index('ix_audit_tenant_id', 'capsule_audit_log', ['tenant_id'])
    op.create_index('ix_audit_capsule_id', 'capsule_audit_log', ['capsule_id'])
    op.create_index('ix_audit_timestamp', 'capsule_audit_log', ['timestamp'])
    op.create_index('ix_audit_action', 'capsule_audit_log', ['action'])


def downgrade() -> None:
    """Drop all capsule registry tables."""
    
    # Drop tables in reverse dependency order
    op.drop_table('capsule_audit_log')
    op.drop_table('capsule_blobs')
    op.drop_table('capsule_versions')
    op.drop_table('capsules')
    
    # Drop custom enums
    op.execute("DROP TYPE IF EXISTS capsulestatus")
    op.execute("DROP TYPE IF EXISTS capsulevisibility")
