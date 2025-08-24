"""Shared test fixtures and utilities for Capsule Registry tests."""

import pytest
import asyncio
from typing import AsyncGenerator, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event

from anumate_core_config import Settings

from ..models import Base, Capsule, CapsuleVersion, CapsuleBlob, CapsuleAudit
from ..models import CapsuleStatus, CapsuleVisibility
from ..settings import CapsuleRegistrySettings
from ..repo import CapsuleRepository
from ..validation import CapsuleValidator
from ..signing import CapsuleSigningProvider
from ..worm_store import WormStorageProvider
from ..service import CapsuleRegistryService
from ..events import NoOpEventPublisher
from ..security import SecurityContext, AnumateRole


# Test database URL (SQLite in-memory)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Sample Ed25519 keys for testing
TEST_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIKjV9Q9v1RqfOB8V6ZV5C2YeW3L4Q5R6M8NzS4Pw7A1t
-----END PRIVATE KEY-----"""

TEST_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAqNX1D2/VGp84HxXplXkLZh5bcvhDlHozw3NLg/DsDW0=
-----END PUBLIC KEY-----"""

# Sample Capsule YAML
SAMPLE_CAPSULE_YAML = """
apiVersion: anumate.io/v1alpha1
kind: Capsule
metadata:
  name: hello-world
  description: Simple hello world Capsule
  tags: [example, hello]
spec:
  tools:
  - name: echo
    namespace: builtin
    image: alpine:latest
  steps:
  - name: greet
    tool: echo
    arguments:
      message: "Hello, World!"
"""


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture
def test_settings() -> CapsuleRegistrySettings:
    """Create test settings."""
    return CapsuleRegistrySettings(
        database_url=TEST_DATABASE_URL,
        signing_private_key=TEST_PRIVATE_KEY,
        signing_public_key=TEST_PUBLIC_KEY,
        worm_storage_path="/tmp/test_worm_storage",
        oidc_enabled=False,
        events_enabled=False,
        debug=True
    )


@pytest.fixture
def tenant_id() -> UUID:
    """Test tenant ID."""
    return uuid4()


@pytest.fixture
def user_id() -> str:
    """Test user ID."""
    return "test-user@example.com"


@pytest.fixture
def security_context(tenant_id: UUID, user_id: str) -> SecurityContext:
    """Create test security context."""
    return SecurityContext(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=[AnumateRole.EDITOR],
        token_claims={"sub": user_id, "tenant": str(tenant_id)}
    )


@pytest.fixture
def repository() -> CapsuleRepository:
    """Create repository instance."""
    return CapsuleRepository()


@pytest.fixture
def validator() -> CapsuleValidator:
    """Create validator instance."""
    return CapsuleValidator()


@pytest.fixture
def signing_provider() -> CapsuleSigningProvider:
    """Create signing provider with test keys."""
    return CapsuleSigningProvider(
        private_key_pem=TEST_PRIVATE_KEY,
        public_key_pem=TEST_PUBLIC_KEY
    )


@pytest.fixture
def worm_storage(tmp_path) -> WormStorageProvider:
    """Create WORM storage provider with temporary directory."""
    storage_path = tmp_path / "worm_storage"
    storage_path.mkdir(parents=True, exist_ok=True)
    return WormStorageProvider(str(storage_path))


@pytest.fixture
def service(
    repository: CapsuleRepository,
    validator: CapsuleValidator, 
    signing_provider: CapsuleSigningProvider,
    worm_storage: WormStorageProvider
) -> CapsuleRegistryService:
    """Create service instance with test dependencies."""
    return CapsuleRegistryService(
        repository=repository,
        validator=validator,
        signing_provider=signing_provider,
        worm_storage=worm_storage,
        event_publisher=NoOpEventPublisher(),
        max_capsule_size=1024 * 1024,
        max_versions_per_capsule=1000
    )


@pytest.fixture
async def sample_capsule(
    db_session: AsyncSession,
    tenant_id: UUID,
    security_context: SecurityContext
) -> Capsule:
    """Create sample Capsule for testing."""
    capsule = Capsule(
        id=uuid4(),
        tenant_id=tenant_id,
        name="test-capsule",
        description="Test Capsule",
        tags=["test", "example"],
        owner=security_context.user_id,
        visibility=CapsuleVisibility.ORG,
        status=CapsuleStatus.ACTIVE,
        latest_version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        etag="test-etag"
    )
    
    db_session.add(capsule)
    await db_session.commit()
    await db_session.refresh(capsule)
    
    return capsule


@pytest.fixture
async def sample_version(
    db_session: AsyncSession,
    sample_capsule: Capsule,
    security_context: SecurityContext,
    signing_provider: CapsuleSigningProvider
) -> CapsuleVersion:
    """Create sample CapsuleVersion for testing."""
    content_hash = "test-content-hash"
    signature = signing_provider.sign_content(content_hash)
    
    version = CapsuleVersion(
        id=uuid4(),
        tenant_id=sample_capsule.tenant_id,
        capsule_id=sample_capsule.id,
        version=1,
        content_hash=content_hash,
        signature=signature,
        pubkey_id=signing_provider.public_key_id,
        uri=f"worm://tenant/{sample_capsule.tenant_id}/content/{content_hash}",
        message="Initial version",
        created_at=datetime.now(timezone.utc),
        created_by=security_context.user_id
    )
    
    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(version)
    
    return version


@pytest.fixture
async def sample_blob(
    db_session: AsyncSession,
    sample_capsule: Capsule
) -> CapsuleBlob:
    """Create sample CapsuleBlob for testing."""
    blob = CapsuleBlob(
        content_hash="test-content-hash",
        tenant_id=sample_capsule.tenant_id,
        yaml_text=SAMPLE_CAPSULE_YAML,
        size_bytes=len(SAMPLE_CAPSULE_YAML.encode('utf-8')),
        created_at=datetime.now(timezone.utc),
        ref_count=1
    )
    
    db_session.add(blob)
    await db_session.commit()
    await db_session.refresh(blob)
    
    return blob


def create_test_capsule_data(
    tenant_id: UUID,
    owner: str,
    name: str = "test-capsule",
    visibility: CapsuleVisibility = CapsuleVisibility.ORG
) -> Dict[str, Any]:
    """Helper to create test Capsule data."""
    return {
        "name": name,
        "description": f"Test Capsule: {name}",
        "tags": ["test", "example"],
        "owner": owner,
        "visibility": visibility,
        "yaml": SAMPLE_CAPSULE_YAML
    }


def assert_capsule_response(response: Dict[str, Any], expected_name: str):
    """Helper to assert Capsule response structure."""
    assert "capsule_id" in response
    assert "version" in response
    assert "content_hash" in response
    assert "signature" in response
    assert "uri" in response
    assert "created_at" in response
    
    # Validate types
    assert isinstance(response["capsule_id"], UUID)
    assert isinstance(response["version"], int)
    assert isinstance(response["content_hash"], str)
    assert isinstance(response["signature"], str)
    assert isinstance(response["uri"], str)
    assert isinstance(response["created_at"], datetime)


def assert_validation_error(error: Dict[str, Any], expected_code: str):
    """Helper to assert validation error structure."""
    assert "type" in error
    assert "title" in error
    assert "status" in error
    assert "detail" in error
    
    assert error["status"] == 400
    assert expected_code in error["detail"] or expected_code in error["type"]
