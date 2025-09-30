"""API dependency injection."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.wes_service.core.security import get_current_user
from src.wes_service.core.storage import StorageBackend, get_storage_backend
from src.wes_service.db.session import get_db

# Type aliases for common dependencies
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[str, Depends(get_current_user)]
Storage = Annotated[StorageBackend, Depends(get_storage_backend)]