"""Authentication for internal callback endpoints."""

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from src.wes_service.config import get_settings

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


# Type alias for dependency injection
CallbackAuth = Annotated[str, Depends(verify_callback_api_key)]
