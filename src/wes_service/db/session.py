"""Database session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.wes_service.config import get_settings

settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database sessions.

    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables using Alembic migrations."""
    import logging
    from pathlib import Path
    from alembic.config import Config
    from alembic import command

    logger = logging.getLogger(__name__)

    # Get the project root directory
    project_root = Path(__file__).parent.parent.parent.parent
    alembic_ini_path = project_root / "alembic.ini"

    # Create Alembic config
    alembic_cfg = Config(str(alembic_ini_path))

    # Run migrations to latest version (synchronous call)
    logger.info("Running Alembic migrations...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Database initialized successfully with Alembic migrations")
