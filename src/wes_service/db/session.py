"""Database session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.wes_service.config import get_settings

settings = get_settings()

# Create async engine — SQLite doesn't support connection pooling options
_engine_kwargs: dict = {
    "echo": settings.log_level == "DEBUG",
}
if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
    from sqlalchemy.pool import StaticPool
    _engine_kwargs["poolclass"] = StaticPool
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20

engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    **_engine_kwargs,
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
    import asyncio
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

    # Run migrations in a thread executor to avoid event loop conflicts
    logger.info("Running Alembic migrations...")

    def run_migrations():
        """Run Alembic migrations synchronously."""
        command.upgrade(alembic_cfg, "head")

    # Execute in thread pool to avoid blocking the async event loop
    await asyncio.to_thread(run_migrations)

    logger.info("Database initialized successfully with Alembic migrations")
