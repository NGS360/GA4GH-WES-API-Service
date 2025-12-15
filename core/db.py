from sqlmodel import create_engine, Session
from core.config import get_settings

engine = create_engine(str(get_settings().database_url), echo=False)

# Yield session
def get_session():
    with Session(engine) as session:
        yield session
