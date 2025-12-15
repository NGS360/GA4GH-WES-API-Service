"""Global error handling middleware."""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from core.logger import logger

def add_error_handlers(app: FastAPI) -> None:
    """Add global error handlers to the FastAPI application."""

    @app.exception_handler(ValueError)
    async def value_error_handler(
        request: Request,
        exc: ValueError,
    ) -> JSONResponse:
        """Handle ValueError exceptions."""
        logger.error(f"ValueError: {exc}")
        error = ErrorResponse(
            msg=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error.model_dump(),
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(
        request: Request,
        exc: FileNotFoundError,
    ) -> JSONResponse:
        """Handle FileNotFoundError exceptions."""
        logger.error(f"FileNotFoundError: {exc}")
        error = ErrorResponse(
            msg=str(exc),
            status_code=status.HTTP_404_NOT_FOUND,
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error.model_dump(),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(
        request: Request,
        exc: SQLAlchemyError,
    ) -> JSONResponse:
        """Handle SQLAlchemy database errors."""
        logger.error(f"Database error: {exc}")
        error = ErrorResponse(
            msg="An unexpected database error occurred",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error.model_dump(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle all other exceptions."""
        logger.exception(f"Unexpected error: {exc}")
        error = ErrorResponse(
            msg="An unexpected error occurred",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error.model_dump(),
        )
