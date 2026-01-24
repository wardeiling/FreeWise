from datetime import datetime, date
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


class Book(SQLModel, table=True):
    """Book model for organizing highlights by source."""
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    author: Optional[str] = Field(default=None, index=True)
    document_tags: Optional[str] = None  # comma-separated tags
    review_weight: float = Field(default=1.0, index=True)  # 0.0 (Never) to 2.0 (More)
    cover_image_url: Optional[str] = Field(default=None)
    cover_image_source: Optional[str] = Field(default=None)
    highlights: list["Highlight"] = Relationship(back_populates="book")
    
    def __repr__(self) -> str:
        author_str = f" by {self.author}" if self.author else ""
        return f"Book(id={self.id}, title='{self.title}'{author_str})"


class Highlight(SQLModel, table=True):
    """Highlight model for storing text excerpts with review scheduling."""
    id: Optional[int] = Field(default=None, primary_key=True)
    text: str = Field(index=True)
    source: Optional[str] = None  # Deprecated: use book_id instead
    note: Optional[str] = None  # Additional notes or annotations
    author: Optional[str] = None  # Deprecated: use book.author instead
    book_id: Optional[int] = Field(default=None, foreign_key="book.id", index=True)
    created_at: Optional[datetime] = Field(default=None, index=True)  # When the highlight was made (None if unknown)
    location_type: Optional[str] = Field(default=None)  # "page" or "order" from Readwise
    location: Optional[int] = Field(default=None, index=True)  # Page number or order in book
    status: str = Field(default="active")  # active | discarded
    favorite: bool = Field(default=False, index=True)
    is_favorited: bool = Field(default=False, index=True)  # Alias for favorite
    is_discarded: bool = Field(default=False, index=True)  # Derived from status
    next_review: Optional[datetime] = Field(default=None, index=True)
    last_reviewed_at: Optional[datetime] = Field(default=None, index=True)
    review_count: int = Field(default=0)
    user_id: int = Field(foreign_key="user.id", index=True)
    book: Optional["Book"] = Relationship(back_populates="highlights")
    
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


class Settings(SQLModel, table=True):
    """Application settings for customizing behavior."""
    id: Optional[int] = Field(default=None, primary_key=True)
    daily_review_count: int = Field(default=5)
    default_sort: str = Field(default="next_review")
    theme: str = Field(default="light")
    
    def __repr__(self) -> str:
        return f"Settings(id={self.id}, daily_review_count={self.daily_review_count})"


class ReviewSession(SQLModel, table=True):
    """Log of daily review sessions for tracking activity and engagement."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    session_uuid: str = Field(index=True, unique=True)  # UUID for tracking across requests
    started_at: datetime = Field(index=True)
    completed_at: Optional[datetime] = Field(default=None, index=True)
    session_date: date = Field(index=True)  # Date of session for easy querying
    target_count: int = Field(default=5)  # Number of highlights intended to review
    highlights_reviewed: int = Field(default=0)  # Highlights marked "Done"
    highlights_discarded: int = Field(default=0)  # Highlights discarded in session
    highlights_favorited: int = Field(default=0)  # Highlights favorited in session
    is_completed: bool = Field(default=False, index=True)  # Whether user finished the session
    
    def __repr__(self) -> str:
        return f"ReviewSession(id={self.id}, date={self.session_date}, reviewed={self.highlights_reviewed}/{self.target_count})"
