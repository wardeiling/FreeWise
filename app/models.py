from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship


class User(SQLModel, table=True):
    """User model for single-user or multi-user setup."""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    email_send_time: Optional[str] = None  # "HH:MM" local time
    
    def __repr__(self) -> str:
        return f"User(id={self.id}, email={self.email})"


class Highlight(SQLModel, table=True):
    """Highlight model for storing text excerpts with review scheduling."""
    id: Optional[int] = Field(default=None, primary_key=True)
    text: str = Field(index=True)
    source: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="active")  # active | discarded
    favorite: bool = Field(default=False, index=True)
    next_review: Optional[datetime] = Field(default=None, index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    
    def __repr__(self) -> str:
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"Highlight(id={self.id}, text='{preview}')"


class Tag(SQLModel, table=True):
    """Tag model for organizing highlights."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    
    def __repr__(self) -> str:
        return f"Tag(id={self.id}, name={self.name})"


class HighlightTag(SQLModel, table=True):
    """Many-to-many relationship between highlights and tags."""
    highlight_id: int = Field(foreign_key="highlight.id", primary_key=True)
    tag_id: int = Field(foreign_key="tag.id", primary_key=True)
