from collections.abc import Generator
from typing import Annotated, TypeAlias
from sqlmodel import Session
from fastapi import Depends


def get_db() -> Generator[Session, None, None]:
    """Yield a database session."""
    from core.db import get_session
    yield from get_session()


DatabaseSession: TypeAlias = Annotated[Session, Depends(get_db)]
