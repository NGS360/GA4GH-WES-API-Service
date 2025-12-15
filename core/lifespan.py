from contextlib import asynccontextmanager
from fastapi import FastAPI
from typing import AsyncGenerator

from core.config import get_settings
from core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    settings = get_settings()
    logger.info(f"Starting {settings.service_name}...")

    # Initialize database (create tables if they don't exist)
    #try:
    #    await init_db()
    #    logger.info("Database initialized successfully")
    #except Exception as e:
    #    logger.error(f"Failed to initialize database: {e}")
    #    raise

    logger.info(f"Service started on {settings.host}:{settings.port}")
    logger.info(f"API available at {settings.api_prefix}")

    yield

    logger.info("Shutting down service...")
