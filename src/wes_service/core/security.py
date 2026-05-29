"""Security utilities for authentication and authorization."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext

from src.wes_service.config import get_settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Basic Auth
security = HTTPBasic()


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


async def get_current_user(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> str:
    """
    Validate HTTP Basic Authentication credentials.

    Args:
        credentials: HTTP Basic auth credentials

    Returns:
        Username if authentication successful

    Raises:
        HTTPException: If authentication fails
    """
    settings = get_settings()

    # Skip auth if method is 'none'
    if settings.auth_method == "none":
        return "anonymous"

    # For OAuth2, this would validate bearer tokens
    if settings.auth_method == "oauth2":
        # TODO: Implement OAuth2 token validation
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OAuth2 not yet implemented",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Basic authentication
    users = parse_basic_auth_users()

    if not users:
        # No users configured, allow access (development mode)
        return credentials.username

    username = credentials.username
    if username not in users:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Verify password
    if not verify_password(credentials.password, users[username]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return username


async def get_optional_user(
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> str | None:
    """
    Get current user or None if no authentication provided.

    This is useful for endpoints that support optional authentication.

    Args:
        credentials: Optional HTTP Basic auth credentials

    Returns:
        Username if authenticated, None otherwise
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
