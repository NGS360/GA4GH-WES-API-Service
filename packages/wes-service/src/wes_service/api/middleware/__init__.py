"""API middleware."""

from wes_service.api.middleware.error_handler import add_error_handlers
from wes_service.api.middleware.response_formatter import add_response_formatter

__all__ = ["add_error_handlers", "add_response_formatter"]
