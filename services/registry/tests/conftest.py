"""
Test Configuration and Fixtures

Common test setup for Capsule Registry tests.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi.testclient import TestClient

# Test imports
from unittest.mock import Mock, AsyncMock

# Service imports
from ..main import create_app
from ..models import Base
from ..settings import RegistrySettings
from ..security import SecurityContext
from anumate_tenancy import TenantContext


# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", 
    "postgresql+asyncpg://test:test@localhost:5432/test_anumate_registry"
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create test database engine."""
    test_engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True
    )
    
    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield test_engine
    
    # Cleanup
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_settings():
    """Create test registry settings."""
    return RegistrySettings(
        database={"url": TEST_DATABASE_URL, "echo": False},
        worm={"backend": "file", "file_root": "/tmp/test_worm"},
        signing={"private_key_pem": "test-key-data"},
        oidc={"issuer": "https://test.oidc.local"},
        events={"enabled": False}  # Disable events in tests
    )


@pytest.fixture
def test_tenant_context():
    """Create test tenant context."""
    return TenantContext(
        tenant_id=uuid.uuid4(),
        name="Test Tenant",
        status="ACTIVE"
    )


@pytest.fixture
def test_security_context(test_tenant_context):
    """Create test security context."""
    return SecurityContext(
        tenant_id=test_tenant_context.tenant_id,
        actor="test@example.com",
        roles=["anumate_editor"],
        permissions=["capsule:read", "capsule:write"],
        auth_time=datetime.now(timezone.utc),
        exp_time=datetime.now(timezone.utc).timestamp() + 3600
    )


@pytest.fixture
def admin_security_context(test_tenant_context):
    """Create admin security context."""
    return SecurityContext(
        tenant_id=test_tenant_context.tenant_id,
        actor="admin@example.com",
        roles=["anumate_admin"],
        permissions=["capsule:read", "capsule:write", "capsule:delete"],
        auth_time=datetime.now(timezone.utc),
        exp_time=datetime.now(timezone.utc).timestamp() + 3600
    )


@pytest.fixture
def mock_oidc_handler():
    """Create mock OIDC handler."""
    handler = Mock()
    handler.validate_token = AsyncMock()
    handler.get_user_info = AsyncMock()
    return handler


@pytest.fixture
def mock_worm_store():
    """Create mock WORM store."""
    store = AsyncMock()
    store.store_content = AsyncMock(return_value="test://content/hash123")
    store.get_content = AsyncMock(return_value="test yaml content")
    store.health_check = AsyncMock(return_value={"status": "healthy"})
    return store


@pytest.fixture
def mock_event_publisher():
    """Create mock event publisher."""
    publisher = AsyncMock()
    return publisher


@pytest.fixture
def test_app(test_settings, db_session, mock_oidc_handler, 
            mock_worm_store, mock_event_publisher):
    """Create test FastAPI application."""
    app = create_app()
    
    # Override dependencies for testing
    async def override_db_session():
        yield db_session
    
    async def override_security_context():
        return test_security_context
    
    app.dependency_overrides = {
        # Add dependency overrides here
    }
    
    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


# Test data fixtures
@pytest.fixture
def valid_capsule_yaml():
    """Valid test capsule YAML content."""
    return """
apiVersion: v1
kind: Capsule
metadata:
  name: test-capsule
  version: "1.0.0"
spec:
  runtime: python
  entrypoint: main.py
  dependencies:
    - requests==2.28.1
  environment:
    - name: ENV_VAR
      value: test_value
"""


@pytest.fixture
def invalid_capsule_yaml():
    """Invalid test capsule YAML content."""
    return """
apiVersion: v1
kind: InvalidKind
metadata:
  name: test-capsule
spec:
  invalid_field: value
"""


@pytest.fixture
def capsule_create_request():
    """Test capsule creation request."""
    return {
        "name": "test-capsule",
        "description": "Test capsule for unit tests",
        "tags": ["test", "example"],
        "visibility": "PRIVATE"
    }


@pytest.fixture
def version_create_request(valid_capsule_yaml):
    """Test version creation request."""
    return {
        "yaml_content": valid_capsule_yaml,
        "lint_only": False
    }


# Helper functions
def assert_uuid(value):
    """Assert that value is a valid UUID string."""
    uuid.UUID(value)  # Will raise ValueError if invalid


def assert_datetime_iso(value):
    """Assert that value is a valid ISO datetime string."""
    datetime.fromisoformat(value.replace('Z', '+00:00'))


def assert_error_response(response, status_code, error_type=None):
    """Assert that response is a proper error response."""
    assert response.status_code == status_code
    data = response.json()
    assert "type" in data
    assert "title" in data
    assert "detail" in data
    assert "status" in data
    assert data["status"] == status_code
    
    if error_type:
        assert error_type in data["type"]
