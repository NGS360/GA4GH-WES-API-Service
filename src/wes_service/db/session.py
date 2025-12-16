"""Database session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.wes_service.config import get_settings

settings = get_settings()

# Determine if we're using SQLite
is_sqlite = settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite")

# Create engine with appropriate parameters
engine_kwargs = {
    "echo": settings.log_level == "DEBUG",
}

# Only add pooling parameters for non-SQLite databases
if not is_sqlite:
    engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
    })

# Create async engine
engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    **engine_kwargs,
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
    """Initialize database tables."""
    from src.wes_service.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
