"""Security utilities for authentication and authorization."""

from typing import Annotated
import threading

import httpx
from cachetools import TTLCache
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
    HTTPAuthorizationCredentials
)
from passlib.context import CryptContext

from src.wes_service.config import get_settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Basic Auth
security_basic = HTTPBasic(auto_error=False)
security_bearer = HTTPBearer(auto_error=False)

# Token cache initialization
# Note: Cache is initialized with default values and can be reconfigured via settings
_token_cache: TTLCache | None = None
_cache_lock = threading.Lock()


def _get_token_cache() -> TTLCache:
    """
    Get or initialize the token cache based on settings.
    
    Returns:
        TTLCache instance configured with settings
    """
    global _token_cache
    
    if _token_cache is None:
        settings = get_settings()
        _token_cache = TTLCache(
            maxsize=settings.token_cache_max_size,
            ttl=settings.token_cache_ttl_seconds
        )
    
    return _token_cache


def clear_token_cache() -> None:
    """Clear the token cache (useful for testing or manual invalidation)."""
    with _cache_lock:
        cache = _get_token_cache()
        cache.clear()


def invalidate_token(token: str) -> None:
    """
    Invalidate a specific token from cache.
    
    Args:
        token: The token to invalidate
    """
    with _cache_lock:
        cache = _get_token_cache()
        cache.pop(token, None)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def parse_basic_auth_users() -> dict[str, str]:
    """
    Parse basic auth users from configuration.

    Returns:
        Dictionary mapping username to hashed password
    """
    settings = get_settings()
    users = {}
    if settings.basic_auth_users:
        for user_entry in settings.basic_auth_users.split(","):
            user_entry = user_entry.strip()
            if ":" in user_entry:
                username, hashed_pwd = user_entry.split(":", 1)
                users[username.strip()] = hashed_pwd.strip()
    return users


async def validate_api_token(token: str, use_cache: bool = True) -> str:
    """
    Validate an API token against the NGS360 auth endpoint with caching.

    Args:
        token: Bearer token to validate
        use_cache: Whether to use cached results (default: True)

    Returns:
        Username from the auth endpoint

    Raises:
        HTTPException: If token is invalid or auth endpoint is unreachable
    """
    settings = get_settings()
    
    # Check cache first if enabled
    if use_cache and settings.enable_token_cache:
        with _cache_lock:
            cache = _get_token_cache()
            cached_result = cache.get(token)
        
        if cached_result is not None:
            return cached_result
    
    # Cache miss or cache disabled - validate with NGS360 API
    url = f"{settings.ngs360_api_url}/api/v1/auth/me"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Client-Application": "ngs360-ga4gh",
                    "User-Agent": "ngs360-ga4gh/1.0",
                },
                timeout=10.0,
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Authentication service unavailable: {exc}",
            ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    data = response.json()
    username = data.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not determine username from token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Cache the successful validation if enabled
    if use_cache and settings.enable_token_cache:
        with _cache_lock:
            cache = _get_token_cache()
            cache[token] = username

    return username


async def get_current_user(
    basic_credentials: Annotated[HTTPBasicCredentials | None, Depends(security_basic)] = None,
    bearer_credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security_bearer)] = None,
) -> str:
    """
    Validate authentication credentials (Basic or Bearer token).

    Args:
        basic_credentials: HTTP Basic auth credentials (if provided)
        bearer_credentials: HTTP Bearer token credentials (if provided)

    Returns:
        Username if authentication successful

    Raises:
        HTTPException: If authentication fails
    """
    settings = get_settings()

    # Skip auth if method is 'none'
    if settings.auth_method == "none":
        return "anonymous"

    # Bearer token authentication (API token)
    if bearer_credentials is not None and settings.auth_method == "api_token":
        return await validate_api_token(bearer_credentials.credentials)

    # Basic authentication
    if basic_credentials is not None and settings.auth_method == "basic":
        users = parse_basic_auth_users()

        if not users:
            # No users configured, allow access (development mode)
            return basic_credentials.username

        username = basic_credentials.username
        if username not in users:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )

        # Verify password
        if not verify_password(basic_credentials.password, users[username]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return username

    # No credentials provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

# async def get_optional_user(
#     credentials: HTTPBasicCredentials | None = Depends(security),
# ) -> str | None:
#     """
#     Get current user or None if no authentication provided.

#     This is useful for endpoints that support optional authentication.

#     Args:
#         credentials: Optional HTTP Basic auth credentials

#     Returns:
#         Username if authenticated, None otherwise
#     """
#     if credentials is None:
#         return None

#     try:
#         return await get_current_user(credentials)
#     except HTTPException:
#         return None
