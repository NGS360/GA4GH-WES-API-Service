"""FastAPI application factory."""

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.wes_service.api.middleware import add_error_handlers
from src.wes_service.api.routes import runs, service_info, tasks
from src.wes_service.config import get_settings
from src.wes_service.db.session import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    settings = get_settings()
    logger.info(f"Starting {settings.service_name}...")

    # Print configuration settings (mask sensitive info)
    logger.info("Configuration Settings:")

    # Helper function to log settings with sensitive value masking
    def _log_setting(key: str, value):
        """Log a setting, masking sensitive values like passwords and secrets"""
        if ("PASSWORD" in key or "SECRET" in key) and value is not None:
            logger.info("  %s: %s", key, "*****")
        else:
            logger.info("  %s: %s", key, value)

    # Log computed fields first (they don't appear in vars())
    computed_fields = {
        "SQLALCHEMY_DATABASE_URI": settings.SQLALCHEMY_DATABASE_URI
    }

    for key, value in computed_fields.items():
        _log_setting(key, value)

    # Log remaining settings
    for key, value in vars(settings).items():
        _log_setting(key, value)

    # Initialize database (create tables if they don't exist)
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    logger.info(f"Service started on {settings.host}:{settings.port}")
    logger.info(f"API available at {settings.api_prefix}")

    yield

    logger.info("Shutting down service...")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application
    """
    settings = get_settings()

    app = FastAPI(
        title="GA4GH Workflow Execution Service",
        description="Workflow Execution Service API implementation",
        version=settings.service_version,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add error handlers
    add_error_handlers(app)

    # Simple fix for newlines in responses
    @app.middleware("http")
    async def add_newline_to_responses(request: Request, call_next):
        response = await call_next(request)
        if isinstance(response, JSONResponse):
            response.headers["X-Content-Has-Newline"] = "true"

            # Get the response content
            content = await response.body()

            # Only add newline if it doesn't already have one
            if not content.endswith(b'\n'):
                # Create a new response with newline
                new_content = content + b'\n'

                # Create a completely new response to avoid mutation issues
                new_response = JSONResponse(
                    content=json.loads(content),  # Parse and re-serialize to ensure valid JSON
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )
                # Override the body directly
                new_response.body = new_content
                # Update content length
                new_response.headers["Content-Length"] = str(len(new_content))

                return new_response

        return response

    # Register routers
    app.include_router(
        service_info.router,
        prefix=settings.api_prefix,
    )
    app.include_router(
        runs.router,
        prefix=settings.api_prefix,
    )
    app.include_router(
        tasks.router,
        prefix=settings.api_prefix,
    )

    # Health check endpoint
    @app.get("/healthcheck", tags=["Health"])
    async def healthcheck() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    # Root redirect
    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {
            "service": settings.service_name,
            "version": settings.service_version,
            "docs": f"{settings.api_prefix}/docs",
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.wes_service.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
