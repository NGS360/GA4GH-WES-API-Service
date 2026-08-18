"""
Shared OpenAPI error-response declarations.

Every error this API returns is an ErrorResponse (see the HTTPException handler in
api.middleware.error_handler), so these declarations describe the real wire
format rather than an aspiration. Declared centrally because the alternative --
repeating the same dict on nine routes -- is how a spec drifts from the code one
route at a time.

Used as ``responses=ERRORS | {404: NOT_FOUND}`` so each route states the statuses
it can actually produce.
"""

from typing import Any

from wes_schemas.common import ErrorResponse

# The statuses any authenticated route can return.
ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication failed or was not provided"},
    403: {"model": ErrorResponse, "description": "The credentials do not permit this request"},
    500: {"model": ErrorResponse, "description": "The service failed while handling the request"},
}

NOT_FOUND: dict[str, Any] = {
    "model": ErrorResponse,
    "description": "The requested resource does not exist",
}

BAD_REQUEST: dict[str, Any] = {
    "model": ErrorResponse,
    "description": "The request was rejected as malformed",
}

DISABLED: dict[str, Any] = {
    "model": ErrorResponse,
    "description": "This endpoint is disabled in this deployment",
}
