"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.wes_service.config import Settings, get_settings
from src.wes_service.core.storage import StorageBackend
from src.wes_service.db.base import Base
from src.wes_service.db.session import get_db
from src.wes_service.main import create_app


# Test database URL (SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        SQLALCHEMY_DATABASE_URI=TEST_DATABASE_URL,
        storage_backend="local",
        local_storage_path="/tmp/wes_test",
        auth_method="none",
        service_name="Test WES Service",
        service_organization_name="Test Org",
        service_environment="test",
        log_level="DEBUG",
    )


@pytest.fixture
async def test_engine() -> AsyncGenerator[Any, None]:
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def test_db(test_engine: Any) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest.fixture
def mock_storage() -> MagicMock:
    """Create mock storage backend."""
    storage = MagicMock(spec=StorageBackend)
    storage.upload_file.return_value = "test/path/file.txt"
    storage.get_url.return_value = "file:///tmp/test/path/file.txt"
    storage.file_exists.return_value = True
    return storage


@pytest.fixture
def app(test_settings: Settings, test_db: AsyncSession, mock_storage: MagicMock):
    """Create test FastAPI application."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_db

    def override_get_settings() -> Settings:
        return test_settings

    def override_get_storage() -> StorageBackend:
        return mock_storage

    def override_get_current_user() -> str:
        """Override authentication for tests - return test user."""
        return "test_user"

    app = create_app()

    # Override dependencies
    from src.wes_service.core.storage import get_storage_backend
    from src.wes_service.core.security import get_current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings
    app.dependency_overrides[get_storage_backend] = override_get_storage
    app.dependency_overrides[get_current_user] = override_get_current_user

    return app


@pytest.fixture
def client(app: Any) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
async def async_client(app: Any) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Create basic auth headers."""
    import base64

    credentials = base64.b64encode(b"testuser:testpass").decode("ascii")
    return {"Authorization": f"Basic {credentials}"}
