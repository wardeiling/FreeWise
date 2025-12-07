import os
from sqlmodel import create_engine, SQLModel

def get_engine():
    """Return SQLModel engine with SQLite database URL from environment."""
    db_url = os.getenv("FREEWISE_DB_URL", "sqlite:///./db/freewise.db")
    return create_engine(db_url, echo=False, connect_args={"check_same_thread": False})
