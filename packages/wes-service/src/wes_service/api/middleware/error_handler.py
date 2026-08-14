"""Global error handling middleware."""

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from wes_schemas.common import ErrorResponse

logger = logging.getLogger(__name__)


def add_error_handlers(app: FastAPI) -> None:
    """Add global error handlers to the FastAPI application."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        """
        Render HTTPException as ErrorResponse, like every other error.

        Without this the API has two error shapes: ``{"msg", "status_code"}`` from
        the handlers below, and FastAPI's ``{"detail"}`` from the 23 HTTPException
        raises in the service layer. Two shapes mean every client needs two code
        paths, and it makes the OpenAPI document unable to state truthfully what an
        error looks like -- so the error models could not be declared on routes at
        all.

        Response headers are preserved because some carry required semantics:
        a 401 without its WWW-Authenticate header is a protocol violation.
        """
        error = ErrorResponse(msg=exc.detail, status_code=exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=error.model_dump(),
            headers=exc.headers,
        )

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
