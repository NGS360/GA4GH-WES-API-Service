"""Authentication for internal callback endpoints."""

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from wes_service.config import get_settings

logger = logging.getLogger(__name__)


async def verify_callback_api_key(
    x_internal_api_key: Annotated[str, Header()],
) -> str:
    """
    Verify the internal API key for callback endpoints.

    Args:
        x_internal_api_key: API key from X-Internal-API-Key header

    Returns:
        The API key if valid

    Raises:
        HTTPException: If API key is invalid or missing
    """
    settings = get_settings()

    # Check if callback endpoint is enabled
    if not getattr(settings, 'enable_callback_endpoint', False):
        logger.warning("Callback endpoint accessed but feature is disabled")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Callback endpoint is currently disabled",
        )

    # Get expected API key from settings/secrets
    expected_key = getattr(settings, 'INTERNAL_CALLBACK_API_KEY', None)

    if not expected_key:
        logger.error("Internal callback API key not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Callback endpoint not properly configured",
        )

    # Verify the key
    if x_internal_api_key != expected_key:
        logger.warning(
            "Invalid callback API key attempted",
            extra={"provided_key_prefix": x_internal_api_key[:8] if x_internal_api_key else None}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key",
        )

    return x_internal_api_key


async def verify_callback_or_service_key(
    x_internal_api_key: Annotated[str | None, Header()] = None,
    x_internal_service_key: Annotated[str | None, Header()] = None,
) -> str:
    """
    Accept either the callback key or the internal service key.

    Two different callers report executor state on the same endpoint, and they
    hold different secrets: the Lambda that relays EventBridge events holds
    INTERNAL_CALLBACK_API_KEY, while NGS360 APIServer -- which submits launcher
    jobs and so is the only thing that knows a job's ID or that SubmitJob failed
    -- holds INTERNAL_SERVICE_API_KEY. Splitting them across two endpoints would
    duplicate the handler to no benefit; sharing one key would couple the
    rotation of a Lambda's secret to a service's.

    Args:
        x_internal_api_key: Callback key from the X-Internal-API-Key header
        x_internal_service_key: Service key from the X-Internal-Service-Key header

    Returns:
        The name of the credential that was accepted, for logging.

    Raises:
        HTTPException: 503 if callbacks are disabled, 500 if neither key is
            configured, 403 if neither key presented matches.
    """
    settings = get_settings()

    if not getattr(settings, 'enable_callback_endpoint', False):
        logger.warning("Callback endpoint accessed but feature is disabled")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Callback endpoint is currently disabled",
        )

    callback_key = getattr(settings, 'INTERNAL_CALLBACK_API_KEY', None)
    service_key = (
        getattr(settings, 'INTERNAL_SERVICE_API_KEY', None)
        if getattr(settings, 'enable_service_auth', False)
        else None
    )

    if not callback_key and not service_key:
        logger.error("Neither callback nor internal service API key is configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Callback endpoint not properly configured",
        )

    if callback_key and x_internal_api_key == callback_key:
        return "callback_key"
    if service_key and x_internal_service_key == service_key:
        return "service_key"

    logger.warning(
        "Invalid credentials on executor callback",
        extra={
            "callback_key_presented": bool(x_internal_api_key),
            "service_key_presented": bool(x_internal_service_key),
        },
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid internal API key",
    )


# Type aliases for dependency injection
CallbackAuth = Annotated[str, Depends(verify_callback_api_key)]
CallbackOrServiceAuth = Annotated[str, Depends(verify_callback_or_service_key)]
