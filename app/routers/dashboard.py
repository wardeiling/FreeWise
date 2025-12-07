from typing import Optional
from fastapi import APIRouter, Depends, Request, Cookie
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from datetime import datetime, date

from app.db import get_engine
from app.models import Book, Highlight, Settings


router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")

# Simple in-memory storage for review tracking (per session)
# In production, this should be stored in database or Redis
review_sessions = {}


def get_session():
    """Dependency to provide database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


@router.get("/ui", response_class=HTMLResponse)
async def ui_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    reviewed: Optional[str] = None,
    session_id: Optional[str] = Cookie(None)
):
    """
    Render dashboard page with statistics overview and review CTA.
    """
    # Get settings for theme and daily review count
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    daily_review_count = settings.daily_review_count if settings else 5
    
    # Check if user has completed review today
    today = date.today().isoformat()
    reviewed_today = False
    highlights_reviewed_count = 0
    
    # Check if the 'reviewed' query parameter indicates completion
    if reviewed == "complete":
        reviewed_today = True
        highlights_reviewed_count = daily_review_count
        
        # Store in session tracking
        if session_id:
            if session_id not in review_sessions:
                review_sessions[session_id] = {}
            review_sessions[session_id][today] = highlights_reviewed_count
    
    # Check session storage
    if session_id and session_id in review_sessions:
        if today in review_sessions[session_id]:
            reviewed_today = True
            highlights_reviewed_count = review_sessions[session_id][today]
    
    # Get total books count
    books_count_stmt = select(func.count(Book.id))
    total_books = session.exec(books_count_stmt).one()
    
    # Get total highlights count
    highlights_count_stmt = select(func.count(Highlight.id))
    total_highlights = session.exec(highlights_count_stmt).one()
    
    # Get total favorited highlights
    favorited_stmt = select(func.count(Highlight.id)).where(
        (Highlight.favorite == True) | (Highlight.is_favorited == True)
    )
    total_favorited = session.exec(favorited_stmt).one()
    
    # Get total discarded highlights
    discarded_stmt = select(func.count(Highlight.id)).where(
        Highlight.is_discarded == True
    )
    total_discarded = session.exec(discarded_stmt).one()
    
    # Calculate active highlights (not discarded)
    active_highlights = total_highlights - total_discarded
    
    # Calculate percentages for visualization
    favorited_percentage = (total_favorited / total_highlights * 100) if total_highlights > 0 else 0
    discarded_percentage = (total_discarded / total_highlights * 100) if total_highlights > 0 else 0
    active_percentage = (active_highlights / total_highlights * 100) if total_highlights > 0 else 0
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "settings": settings,
        "daily_review_count": daily_review_count,
        "reviewed_today": reviewed_today,
        "highlights_reviewed_count": highlights_reviewed_count,
        "total_books": total_books,
        "total_highlights": total_highlights,
        "total_favorited": total_favorited,
        "total_discarded": total_discarded,
        "active_highlights": active_highlights,
        "favorited_percentage": favorited_percentage,
        "discarded_percentage": discarded_percentage,
        "active_percentage": active_percentage
    })
