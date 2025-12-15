from collections.abc import Generator
from typing import Annotated, TypeAlias
from sqlmodel import Session
from fastapi import Depends


#from src.wes_service.core.security import get_current_user
#from src.wes_service.core.storage import StorageBackend, get_storage_backend
#from src.wes_service.db.session import get_db

def get_db() -> Generator[Session, None, None]:
    """Yield a database session."""
    from core.db import get_session
    yield from get_session()


DatabaseSession: TypeAlias = Annotated[Session, Depends(get_db)]
# CurrentUser = Annotated[str, Depends(get_current_user)]
# Storage = Annotated[StorageBackend, Depends(get_storage_backend)]
