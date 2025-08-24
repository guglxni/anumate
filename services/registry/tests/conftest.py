"""
Test Configuration and Fixtures

Common test setup for Capsule Registry tests with isolated imports.
"""

import asyncio
import os
import uuid
import tempfile
import sqlite3
from datetime import datetime, timezone
from typing import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import create_engine
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Test imports
from unittest.mock import Mock, AsyncMock, MagicMock

# Ensure clean Python path
import sys
current_dir = Path(__file__).parent.parent.parent.parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Now import safely
try:
    from services.registry.models import Base, Capsule, CapsuleVersion
    from services.registry.settings import RegistrySettings
except ImportError as e:
    pytest.skip(f"Cannot import registry modules: {e}", allow_module_level=True)


# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
SYNC_TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings():
    """Test configuration settings."""
    return RegistrySettings(
        database_url=TEST_DATABASE_URL,
        worm_bucket="file:///tmp/test_worm",
        oidc_issuer="https://test.auth.local",
        oidc_audience="test-audience",
        environment="test"
    )


@pytest.fixture
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    """Create test database session."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture
def sync_test_engine():
    """Synchronous test database engine for migrations."""
    engine = create_engine(SYNC_TEST_DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def mock_tenant_context():
    """Mock tenant context for testing."""
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    context = Mock()
    context.tenant_id = tenant_id
    context.user_id = user_id
    context.permissions = ["capsule:read", "capsule:write", "version:read", "version:write"]
    context.roles = ["editor"]
    
    return context


@pytest.fixture
def mock_oidc_user(mock_tenant_context):
    """Mock OIDC user for testing."""
    user = Mock()
    user.subject = mock_tenant_context.user_id
    user.email = "test@example.com"
    user.tenant_id = mock_tenant_context.tenant_id
    user.permissions = mock_tenant_context.permissions
    user.roles = mock_tenant_context.roles
    
    return user


@pytest.fixture
def mock_security_context(mock_oidc_user, mock_tenant_context):
    """Mock security context."""
    context = Mock()
    context.user = mock_oidc_user
    context.tenant = mock_tenant_context
    context.is_authenticated = True
    context.has_permission = Mock(return_value=True)
    context.require_permission = Mock()
    
    return context


@pytest.fixture
def test_capsule_data():
    """Sample capsule data for testing."""
    return {
        "name": "test-capsule",
        "description": "Test capsule for unit tests",
        "content": {
            "terraform": {
                "main.tf": """
resource "null_resource" "test" {
  provisioner "local-exec" {
    command = "echo 'Hello, World!'"
  }
}
""".strip()
            },
            "metadata": {
                "version": "1.0.0",
                "author": "test-user",
                "tags": ["test", "sample"]
            }
        },
        "variables": {
            "region": {
                "type": "string", 
                "description": "AWS region",
                "default": "us-east-1"
            }
        },
        "outputs": {
            "result": {
                "description": "Execution result",
                "value": "${null_resource.test.id}"
            }
        }
    }


@pytest.fixture
def mock_worm_store():
    """Mock WORM store for testing."""
    store = Mock()
    store.store = AsyncMock(return_value="file://test/content/hash123.yaml")
    store.exists = AsyncMock(return_value=False)
    store.get_uri = Mock(return_value="file://test/content/hash123.yaml")
    
    return store


@pytest.fixture
def mock_event_publisher():
    """Mock event publisher for testing."""
    publisher = Mock()
    publisher.publish = AsyncMock()
    publisher.publish_capsule_created = AsyncMock()
    publisher.publish_version_published = AsyncMock()
    publisher.publish_capsule_deleted = AsyncMock()
    
    return publisher


@pytest.fixture
def mock_signer():
    """Mock content signer for testing."""
    signer = Mock()
    signer.sign_content = Mock(return_value="signature123")
    signer.verify_signature = Mock(return_value=True)
    signer.get_content_hash = Mock(return_value="hash123")
    signer.get_public_key_id = Mock(return_value="pubkey123")
    
    return signer


@pytest.fixture
def test_app(
    test_settings, 
    mock_security_context,
    mock_worm_store, 
    mock_event_publisher,
    mock_signer
):
    """Create test FastAPI app with mocked dependencies."""
    from fastapi import FastAPI
    
    app = FastAPI(
        title="Test Capsule Registry",
        version="0.1.0-test"
    )
    
    # Add basic health endpoint for testing
    @app.get("/healthz")
    async def health():
        return {"status": "healthy"}
    
    @app.get("/readyz") 
    async def ready():
        return {"status": "ready"}
    
    return app


@pytest.fixture
def test_client(test_app):
    """Create test client."""
    return TestClient(test_app)


@pytest.fixture
def auth_headers(mock_tenant_context):
    """Authentication headers for API testing."""
    return {
        "Authorization": "Bearer test-jwt-token",
        "X-Tenant-Id": mock_tenant_context.tenant_id,
        "Content-Type": "application/json"
    }


@pytest.fixture
def idempotency_headers(auth_headers):
    """Headers with idempotency key."""
    headers = auth_headers.copy()
    headers["Idempotency-Key"] = str(uuid.uuid4())
    return headers


# Sample test data
@pytest.fixture
def sample_capsule():
    """Create a sample capsule for testing."""
    return Capsule(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="test-capsule",
        description="Test capsule",
        owner="test-user",
        status="active",
        visibility="private",
        latest_version=1,
        etag="etag123",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )


@pytest.fixture  
def sample_version(sample_capsule):
    """Create a sample capsule version for testing."""
    return CapsuleVersion(
        id=uuid.uuid4(),
        tenant_id=sample_capsule.tenant_id,
        capsule_id=sample_capsule.id,
        version=1,
        content_hash="hash123",
        signature="signature123", 
        pubkey_id="pubkey123",
        uri="file://test/content/hash123.yaml",
        created_by="test-user",
        created_at=datetime.now(timezone.utc)
    )
